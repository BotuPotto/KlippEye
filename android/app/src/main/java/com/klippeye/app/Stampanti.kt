package com.klippeye.app

import android.content.Context

/**
 * Piu' stampanti (app 1.6.0, dashboard 1.61). Ogni stampante ha il suo KlippEye; la dashboard ne ha l'elenco e, quando si
 * sceglie un'altra stampante dal suo menu in alto, chiede all'app di aprirla (KlippEyeApp.switchPrinter): l'app la carica
 * nella stessa finestra invece di passarla al browser, e se lo ricorda alla prossima apertura.
 *
 * La stampante "principale" e' quella degli indirizzi dell'app ([Indirizzi]); un'altra e' scritta come "host" oppure
 * "host:porta" (la porta solo se non e' quella di KlippEye). Come per gli indirizzi, solo reti private: la dashboard non puo'
 * mandare l'app su un sito qualsiasi.
 */
object Stampanti {
    private const val PREFERENZE = "klippeye"
    private const val CHIAVE_APERTA = "stampante_aperta"

    /** "host" o "host:porta" pulito, o null se non e' un indirizzo di una rete privata. */
    fun pulisci(testo: String?): String? {
        if (testo == null) return null
        val senzaSchema = testo.trim().replace(Regex("^https?://", RegexOption.IGNORE_CASE), "").substringBefore('/')
        val porta = Regex(":(\\d{1,5})$").find(senzaSchema)?.groupValues?.get(1)?.toIntOrNull()
        if (porta != null && porta !in 1..65535) return null
        val host = Indirizzi.pulisci(senzaSchema) ?: return null
        if (!Indirizzi.privato(host)) return null
        return if (porta == null || porta == Indirizzi.PORTA) host else "$host:$porta"
    }

    /** L'indirizzo della sua dashboard: http://host:8085/ (o la porta scritta). */
    fun url(stampante: String): String = if (stampante.contains(':')) "http://$stampante/" else "http://$stampante:${Indirizzi.PORTA}/"

    /** Il solo nome dell'host (senza porta), per confrontarlo con quello della pagina caricata. */
    fun host(stampante: String): String = stampante.substringBefore(':')

    /** True se e' la stampante principale (uno dei suoi due indirizzi, sulla porta di KlippEye). */
    fun principale(context: Context, stampante: String): Boolean {
        if (stampante.contains(':')) return false
        val indirizzi = Indirizzi.leggi(context)
        return stampante == indirizzi.locale || (indirizzi.esterno.isNotEmpty() && stampante == indirizzi.esterno)
    }

    /** L'altra stampante aperta ("" = la principale). */
    fun aperta(context: Context): String =
        pulisci(context.applicationContext.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE).getString(CHIAVE_APERTA, "")) ?: ""

    fun apri(context: Context, stampante: String) {
        context.applicationContext.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE).edit().putString(CHIAVE_APERTA, stampante).apply()
    }
}
