package com.klippeye.app

import android.content.Context
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * L'HTTPS di KlippEye (app 1.7.0, KlippEye 1.93): il certificato lo crea il Raspberry e nessuna autorita' lo firma, quindi
 * Android non lo riconosce da solo. La dashboard (aperta in http) passa all'app l'impronta SHA-256 del certificato
 * (`KlippEyeApp.setCertificate`); l'app la ricorda per quel Raspberry e da li' in poi usa https accettando SOLO quel
 * certificato: un altro, anche valido per un'altra autorita', viene rifiutato.
 *
 * Qui solo Java, a parte le preferenze: le impronte e il controllo si provano da soli.
 */
object Certificati {
    private const val PREFERENZE = "klippeye"
    private const val PREFISSO = "certificato_"
    private val FORMATO = Regex("^[0-9A-F]{2}(:[0-9A-F]{2}){31}$")

    /** L'impronta come la mostrano la dashboard e i browser: "AB:CD:...", 32 coppie. */
    fun impronta(certificato: X509Certificate): String = impronta(certificato.encoded)

    fun impronta(der: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(der).joinToString(":") { "%02X".format(it) }

    /** L'impronta pulita (maiuscole, con i due punti) o null se non lo e'. */
    fun pulisci(testo: String?): String? {
        val t = testo?.trim()?.uppercase() ?: return null
        val conDuePunti = if (!t.contains(':') && t.length == 64) t.chunked(2).joinToString(":") else t
        return if (FORMATO.matches(conDuePunti)) conDuePunti else null
    }

    private fun preferenze(context: Context) = context.applicationContext.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE)

    /** L'impronta ricordata per quel Raspberry, o null (allora l'app non prova https). */
    fun leggi(context: Context, host: String): String? = pulisci(preferenze(context).getString(PREFISSO + host, null))

    /** Ricorda l'impronta per quel Raspberry; "" o null la toglie (la dashboard dice che l'HTTPS e' spento). */
    fun salva(context: Context, host: String, impronta: String?): String {
        val pulita = pulisci(impronta)
        val editor = preferenze(context).edit()
        if (pulita == null) editor.remove(PREFISSO + host) else editor.putString(PREFISSO + host, pulita)
        editor.apply()
        return if (pulita != null || impronta.isNullOrBlank()) "ok" else "impronta non valida"
    }

    /** Un controllo dei certificati che accetta solo quello con l'impronta `attesa`. */
    fun fiducia(attesa: String): X509TrustManager = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            throw CertificateException("non usato")
        }

        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            val primo = chain?.firstOrNull() ?: throw CertificateException("nessun certificato")
            if (impronta(primo) != attesa) throw CertificateException("il certificato del Raspberry è cambiato")
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }

    fun fabbrica(attesa: String): SSLSocketFactory {
        val contesto = SSLContext.getInstance("TLS")
        contesto.init(null, arrayOf<TrustManager>(fiducia(attesa)), null)
        return contesto.socketFactory
    }

    /**
     * Apre un collegamento a un indirizzo del Raspberry: in https accetta solo il certificato ricordato per quell'host
     * (il nome scritto nel certificato non conta: conta che sia proprio quello).
     */
    fun apri(context: Context, url: URL): HttpURLConnection {
        val collegamento = url.openConnection() as HttpURLConnection
        if (collegamento is HttpsURLConnection) {
            val attesa = leggi(context, url.host) ?: throw java.io.IOException("certificato del Raspberry sconosciuto")
            collegamento.sslSocketFactory = fabbrica(attesa)
            // il nome nel certificato puo' non essere quello scritto nell'app (un IP diverso): conta che sia proprio quel certificato
            collegamento.setHostnameVerifier { _, sessione ->
                val primo = try { sessione.peerCertificates.firstOrNull() as? X509Certificate } catch (e: Exception) { null }
                primo != null && impronta(primo) == attesa
            }
        }
        return collegamento
    }
}
