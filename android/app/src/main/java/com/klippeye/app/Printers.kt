package com.klippeye.app

import android.content.Context

/**
 * More printers (app 1.6.0, dashboard 1.61). Each printer has its own KlippEye; the dashboard keeps the list and, when
 * another printer is chosen from its top menu, asks the app to open it (KlippEyeApp.switchPrinter): the app loads it in the
 * same window instead of handing it to the browser, and remembers it for the next start.
 *
 * The "main" printer is the one of the app's addresses ([Addresses]); another one is written as "host" or "host:port" (the
 * port only when it is not KlippEye's). As for the addresses, private networks only: the dashboard cannot send the app to
 * any site.
 */
object Printers {
    // stored names, kept from the first versions so that an update remembers the printer that was open
    private const val PREFERENCES = "klippeye"
    private const val KEY_OPEN = "stampante_aperta"

    /** "host" or "host:port", cleaned, or null when it is not an address of a private network. */
    fun clean(text: String?): String? {
        if (text == null) return null
        val withoutScheme = text.trim().replace(Regex("^https?://", RegexOption.IGNORE_CASE), "").substringBefore('/')
        val port = Regex(":(\\d{1,5})$").find(withoutScheme)?.groupValues?.get(1)?.toIntOrNull()
        if (port != null && port !in 1..65535) return null
        val host = Addresses.clean(withoutScheme) ?: return null
        if (!Addresses.isPrivate(host)) return null
        return if (port == null || port == Addresses.PORT) host else "$host:$port"
    }

    /** The address of its dashboard when the port is written: http://host:port/. */
    fun url(printer: String): String = if (printer.contains(':')) "http://$printer/" else "http://$printer:${Addresses.PORT}/"

    /** True for the main printer (one of its two addresses, on KlippEye's port). */
    fun isMain(context: Context, printer: String): Boolean {
        if (printer.contains(':')) return false
        val addresses = Addresses.read(context)
        return printer == addresses.local || (addresses.external.isNotEmpty() && printer == addresses.external)
    }

    private fun preferences(context: Context) = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** The other printer that is open ("" = the main one). */
    fun open(context: Context): String = clean(preferences(context).getString(KEY_OPEN, "")) ?: ""

    fun remember(context: Context, printer: String) {
        preferences(context).edit().putString(KEY_OPEN, printer).apply()
    }
}
