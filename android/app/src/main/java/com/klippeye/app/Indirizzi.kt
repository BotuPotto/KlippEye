package com.klippeye.app

import android.content.Context

/**
 * Gli indirizzi del Raspberry a cui l'app si collega: la rete di casa e ZeroTier (la porta e' sempre quella del Brain).
 *
 * Arrivano dal menu Impostazioni della dashboard, che li comunica con `KlippEyeApp.setAddresses` (vedi
 * [MainActivity.DashboardBridge]), oppure dalla finestra "Indirizzi" dell'app: al primo avvio (dalla 1.4.0 non ci sono piu'
 * indirizzi "di fabbrica": erano quelli di chi ha scritto l'app) e quando non riesce a connettersi.
 * L'esterno (ZeroTier, VPN) e' facoltativo. Prima di arrendersi l'app prova due giri, locale ed esterno alternati.
 *
 * Qui non c'e' niente di Android a parte le preferenze: la pulizia e i controlli si provano da soli (IndirizziTest.kt).
 */
object Indirizzi {
    /** La porta del servizio KlippEye: c'e' sempre. Dalla 1.94 KlippEye risponde anche all'indirizzo senza porta (nginx). */
    const val PORTA = 8085
    /** Dove l'app chiede "sei KlippEye?": risponde anche con la password attiva, e un'altra pagina non lo ha. */
    const val PERCORSO_PROVA = "api/auth/status"
    /** Quanti giri di tentativi (locale, esterno) prima di mostrare "Riprova / Indirizzi". */
    const val GIRI = 2

    private const val PREFERENZE = "klippeye"
    private const val CHIAVE_LOCALE = "ip_locale"
    private const val CHIAVE_ESTERNO = "ip_esterno"

    /**
     * Un indirizzo da provare: `etichetta` dice di che rete si tratta ("rete locale", "ZeroTier"...); `url` e' quello
     * trovato (all'inizio quello con la porta del servizio).
     */
    data class Candidato(val host: String, val etichetta: String, val url: String = "http://$host:$PORTA/")

    /**
     * Gli indirizzi di un Raspberry, dal migliore (app 1.7.0): https senza porta se l'app ne conosce il certificato, poi http
     * senza porta (KlippEye 1.94), poi la porta del servizio, che c'e' sempre.
     */
    fun varianti(host: String, conCertificato: Boolean): List<String> =
        (if (conCertificato) listOf("https://$host/") else emptyList()) + listOf("http://$host/", "http://$host:$PORTA/")

    /** La risposta di [PERCORSO_PROVA] e' quella di KlippEye: un JSON con "enabled" (la password accesa o spenta). */
    fun eKlippEye(tipo: String?, corpo: String?): Boolean =
        (tipo ?: "").contains("json", ignoreCase = true) && Regex("\"enabled\"\\s*:\\s*(true|false)").containsMatchIn(corpo ?: "")

    /** I due indirizzi; "" = non impostato (l'esterno puo' mancare; il locale manca solo prima del primo avvio). */
    data class Coppia(val locale: String, val esterno: String) {
        val vuota: Boolean get() = locale.isEmpty() && esterno.isEmpty()
    }

    val NESSUNA = Coppia("", "")

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
        if (!privato(l)) return "L'IP locale deve essere di una rete privata (192.168.x.x, 10.x.x.x, 172.16-31.x.x)"
        if (esterno.isNullOrBlank()) return "ok" // facoltativo: solo con ZeroTier o una VPN
        val e = pulisci(esterno) ?: return "L'IP esterno non e' un indirizzo valido"
        if (!privato(e)) return "L'IP esterno deve essere di una rete privata (ZeroTier, VPN)"
        return "ok"
    }

    /** Gli indirizzi diversi da provare: locale, poi esterno (se c'e' ed e' diverso). */
    fun candidati(scelti: Coppia): List<Candidato> {
        val lista = ArrayList<Candidato>()
        if (scelti.locale.isNotEmpty()) lista.add(Candidato(scelti.locale, "rete locale"))
        if (scelti.esterno.isNotEmpty() && scelti.esterno != scelti.locale) lista.add(Candidato(scelti.esterno, "ZeroTier / VPN"))
        return lista
    }

    /** I tentativi in ordine: [GIRI] giri di locale ed esterno alternati (locale, esterno, locale, esterno). */
    fun tentativi(scelti: Coppia): List<Candidato> {
        val giro = candidati(scelti)
        return (1..GIRI).flatMap { giro }
    }

    // ---- Le preferenze del telefono ----

    private fun preferenze(context: Context) = context.applicationContext.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE)

    /** Gli indirizzi salvati; quello che manca o non e' piu' accettabile e' "" (da chiedere). */
    fun leggi(context: Context): Coppia {
        val p = preferenze(context)
        fun valido(chiave: String): String {
            val host = pulisci(p.getString(chiave, null))
            return if (host != null && privato(host)) host else ""
        }
        return Coppia(valido(CHIAVE_LOCALE), valido(CHIAVE_ESTERNO))
    }

    /** Salva i due indirizzi (puliti) se vanno bene. Restituisce "ok" oppure il motivo del rifiuto: in quel caso non cambia nulla. */
    fun salva(context: Context, locale: String?, esterno: String?): String {
        val esito = controlla(locale, esterno)
        if (esito != "ok") return esito
        val nuovi = Coppia(pulisci(locale)!!, pulisci(esterno) ?: "")
        if (nuovi != leggi(context)) {
            preferenze(context).edit().putString(CHIAVE_LOCALE, nuovi.locale).putString(CHIAVE_ESTERNO, nuovi.esterno).apply()
        }
        return "ok"
    }

    /** Gli indirizzi come li legge la dashboard: {"local":"...","external":"..."}. Gli indirizzi sono gia' puliti, niente da proteggere. */
    fun comeJson(scelti: Coppia): String = "{\"local\":\"${scelti.locale}\",\"external\":\"${scelti.esterno}\"}"
}
