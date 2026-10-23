package com.klippeye.app

import android.content.Context

/**
 * Gli indirizzi del Raspberry a cui l'app si collega: la rete di casa e ZeroTier (la porta e' sempre quella del Brain).
 *
 * Arrivano dal menu Impostazioni della dashboard, che li comunica con `KlippEyeApp.setAddresses` (vedi
 * [MainActivity.DashboardBridge]), oppure dalla finestra "Indirizzi" dell'app, che compare quando non riesce a connettersi.
 * Senza niente di salvato valgono quelli di fabbrica: gli stessi di sempre. Quelli di fabbrica restano anche in fondo alla
 * lista dei tentativi: se un indirizzo scritto male impedisce la connessione, l'app non resta chiusa fuori.
 *
 * Qui non c'e' niente di Android a parte le preferenze: la pulizia e i controlli si provano da soli (IndirizziTest.kt).
 */
object Indirizzi {
    const val PORTA = 8085
    const val LOCALE_DI_FABBRICA = "192.168.1.17"
    const val ESTERNO_DI_FABBRICA = "172.25.170.177"

    private const val PREFERENZE = "klippeye"
    private const val CHIAVE_LOCALE = "ip_locale"
    private const val CHIAVE_ESTERNO = "ip_esterno"

    /** Un indirizzo da provare: `etichetta` dice di che rete si tratta ("rete locale", "ZeroTier"...). */
    data class Candidato(val host: String, val etichetta: String) {
        val url: String get() = "http://$host:$PORTA/"
    }

    data class Coppia(val locale: String, val esterno: String)

    val DI_FABBRICA = Coppia(LOCALE_DI_FABBRICA, ESTERNO_DI_FABBRICA)

    private val FORMA_NOME = Regex("^[a-z0-9]([a-z0-9.-]{0,98}[a-z0-9])?$")
    private val SUFFISSI_LOCALI = listOf(".local", ".lan", ".home", ".internal", ".home.arpa")

    private fun soloNumeri(host: String) = host.all { it.isDigit() || it == '.' }

    /**
     * Solo l'indirizzo: toglie "http://", la porta e il percorso, mette in minuscolo. Restituisce null se quello che resta
     * non e' un nome o un indirizzo IPv4 intero.
     */
    fun pulisci(testo: String?): String? {
        if (testo == null) return null
        var host = testo.trim().replace(Regex("^https?://", RegexOption.IGNORE_CASE), "")
        host = host.substringBefore('/').substringBefore('?').substringBefore('#')
        host = host.replace(Regex(":\\d{1,5}$"), "").lowercase()
        if (!FORMA_NOME.matches(host)) return null
        if (soloNumeri(host)) {
            val parti = host.split('.')
            if (parti.size != 4 || parti.any { it.isEmpty() || it.length > 3 || it.toInt() > 255 }) return null
        }
        return host
    }

    /**
     * Solo reti private (casa, VPN, ZeroTier: 10.x, 172.16-31.x, 192.168.x, 100.64-127.x) e nomi della rete locale.
     * L'app non va mai a cercare KlippEye su internet: una pagina strana, mostrata in un riquadro della dashboard, non puo'
     * quindi dirottarla su un sito qualsiasi cambiando gli indirizzi.
     */
    fun privato(host: String): Boolean {
        if (soloNumeri(host)) {
            val p = host.split('.').map { it.toInt() }
            return p[0] == 10 || (p[0] == 172 && p[1] in 16..31) || (p[0] == 192 && p[1] == 168) || (p[0] == 100 && p[1] in 64..127)
        }
        return !host.contains('.') || SUFFISSI_LOCALI.any { host.endsWith(it) }
    }

    /** "ok" se i due indirizzi vanno bene, altrimenti il motivo (in italiano, e' quello che vede l'utente). */
    fun controlla(locale: String?, esterno: String?): String {
        val l = pulisci(locale) ?: return "L'IP locale non e' un indirizzo valido"
        val e = pulisci(esterno) ?: return "L'IP esterno non e' un indirizzo valido"
        if (!privato(l)) return "L'IP locale deve essere di una rete privata (192.168.x.x, 10.x.x.x, 172.16-31.x.x)"
        if (!privato(e)) return "L'IP esterno deve essere di una rete privata (ZeroTier, VPN)"
        return "ok"
    }

    /**
     * In che ordine provare gli indirizzi: locale, esterno, poi quelli di fabbrica (se diversi). Senza ripetizioni.
     * Con gli indirizzi di fabbrica salvati la lista e' quella di sempre: due tentativi.
     */
    fun candidati(scelti: Coppia): List<Candidato> {
        val lista = ArrayList<Candidato>()
        fun aggiungi(host: String, etichetta: String) {
            if (lista.none { it.host == host }) lista.add(Candidato(host, etichetta))
        }
        aggiungi(scelti.locale, "rete locale")
        aggiungi(scelti.esterno, "ZeroTier")
        aggiungi(LOCALE_DI_FABBRICA, "rete locale di fabbrica")
        aggiungi(ESTERNO_DI_FABBRICA, "ZeroTier di fabbrica")
        return lista
    }

    // ---- Le preferenze del telefono ----

    private fun preferenze(context: Context) = context.applicationContext.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE)

    /** Gli indirizzi salvati; quello che manca o non e' piu' accettabile torna quello di fabbrica. */
    fun leggi(context: Context): Coppia {
        val p = preferenze(context)
        fun valido(chiave: String, predefinito: String): String {
            val host = pulisci(p.getString(chiave, null))
            return if (host != null && privato(host)) host else predefinito
        }
        return Coppia(valido(CHIAVE_LOCALE, LOCALE_DI_FABBRICA), valido(CHIAVE_ESTERNO, ESTERNO_DI_FABBRICA))
    }

    /** Salva i due indirizzi (puliti) se vanno bene. Restituisce "ok" oppure il motivo del rifiuto: in quel caso non cambia nulla. */
    fun salva(context: Context, locale: String?, esterno: String?): String {
        val esito = controlla(locale, esterno)
        if (esito != "ok") return esito
        val nuovi = Coppia(pulisci(locale)!!, pulisci(esterno)!!)
        if (nuovi != leggi(context)) {
            preferenze(context).edit().putString(CHIAVE_LOCALE, nuovi.locale).putString(CHIAVE_ESTERNO, nuovi.esterno).apply()
        }
        return "ok"
    }

    /** Gli indirizzi come li legge la dashboard: {"local":"...","external":"..."}. Gli indirizzi sono gia' puliti, niente da proteggere. */
    fun comeJson(scelti: Coppia): String = "{\"local\":\"${scelti.locale}\",\"external\":\"${scelti.esterno}\"}"
}
