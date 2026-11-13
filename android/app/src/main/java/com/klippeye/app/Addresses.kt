package com.klippeye.app

import android.content.Context

/**
 * The addresses of the Raspberry the app connects to: the home network and, optionally, an external one (ZeroTier, a VPN).
 *
 * They come from the dashboard's Settings menu, which passes them with `KlippEyeApp.setAddresses` (see
 * [MainActivity.DashboardBridge]), or from the app's own "Addresses" window: at the first start (there are no built-in
 * addresses) and whenever the app cannot connect. Before giving up the app tries two rounds, local and external in turn.
 *
 * Nothing here needs Android except the stored preferences: the cleaning and the checks are tested on their own (AddressesTest).
 */
object Addresses {
    /** The port of the KlippEye service: always there. From KlippEye 1.94 it also answers without a port (nginx). */
    const val PORT = 8085
    /** Where the app asks "are you KlippEye?": it answers even with the password on, and another page does not have it. */
    const val PROBE_PATH = "api/auth/status"
    /** Rounds of attempts (local, external) before showing "Try again / Addresses". */
    const val ROUNDS = 2

    // The names the addresses are stored under (kept from the first versions of the app, so an update keeps them)
    private const val PREFERENCES = "klippeye"
    private const val KEY_LOCAL = "ip_locale"
    private const val KEY_EXTERNAL = "ip_esterno"

    /** Which network an address belongs to: the app says it while connecting. */
    enum class Network { LOCAL, EXTERNAL }

    /** An address to try; `url` is where KlippEye was found (at first the address with the service's port). */
    data class Candidate(val host: String, val network: Network, val url: String = "http://$host:$PORT/")

    /** Whether a pair of addresses can be used, and if not, which one is wrong (the app shows the reason in its language). */
    enum class Check { OK, LOCAL_INVALID, LOCAL_NOT_PRIVATE, EXTERNAL_INVALID, EXTERNAL_NOT_PRIVATE }

    /**
     * Where KlippEye may answer on a Raspberry, best first (app 1.7.0): https without a port when the app knows its
     * certificate, then http without a port (KlippEye 1.94), then the service's port, which is always there.
     */
    fun variants(host: String, withCertificate: Boolean): List<String> =
        (if (withCertificate) listOf("https://$host/") else emptyList()) + listOf("http://$host/", "http://$host:$PORT/")

    /** The answer of [PROBE_PATH] is KlippEye's: a JSON with "enabled" (the password on or off). */
    fun isKlippEye(contentType: String?, body: String?): Boolean =
        (contentType ?: "").contains("json", ignoreCase = true) && Regex("\"enabled\"\\s*:\\s*(true|false)").containsMatchIn(body ?: "")

    /** The two addresses; "" = not set (the external one is optional; the local one is missing only before the first start). */
    data class AddressPair(val local: String, val external: String) {
        val empty: Boolean get() = local.isEmpty() && external.isEmpty()
    }

    val NONE = AddressPair("", "")

    private val NAME_FORMAT = Regex("^[a-z0-9]([a-z0-9.-]{0,98}[a-z0-9])?$")
    private val LOCAL_SUFFIXES = listOf(".local", ".lan", ".home", ".internal", ".home.arpa")

    private fun numeric(host: String) = host.all { it.isDigit() || it == '.' }

    /**
     * Only the address: drops "http://", the port and the path, makes it lower case. Null when what is left is not a name
     * or a whole IPv4 address.
     */
    fun clean(text: String?): String? {
        if (text == null) return null
        var host = text.trim().replace(Regex("^https?://", RegexOption.IGNORE_CASE), "")
        host = host.substringBefore('/').substringBefore('?').substringBefore('#')
        host = host.replace(Regex(":\\d{1,5}$"), "").lowercase()
        if (!NAME_FORMAT.matches(host)) return null
        if (numeric(host)) {
            val parts = host.split('.')
            if (parts.size != 4 || parts.any { it.isEmpty() || it.length > 3 || it.toInt() > 255 }) return null
        }
        return host
    }

    /**
     * Only private networks (home, VPN, ZeroTier: 10.x, 172.16-31.x, 192.168.x, 100.64-127.x) and names of the local
     * network. The app never looks for KlippEye on the internet, so a page shown in a frame of the dashboard cannot send
     * it to any site by changing the addresses.
     */
    fun isPrivate(host: String): Boolean {
        if (numeric(host)) {
            val p = host.split('.').map { it.toInt() }
            return p[0] == 10 || (p[0] == 172 && p[1] in 16..31) || (p[0] == 192 && p[1] == 168) || (p[0] == 100 && p[1] in 64..127)
        }
        return !host.contains('.') || LOCAL_SUFFIXES.any { host.endsWith(it) }
    }

    fun check(local: String?, external: String?): Check {
        val l = clean(local) ?: return Check.LOCAL_INVALID
        if (!isPrivate(l)) return Check.LOCAL_NOT_PRIVATE
        if (external.isNullOrBlank()) return Check.OK // optional: only with ZeroTier or a VPN
        val e = clean(external) ?: return Check.EXTERNAL_INVALID
        if (!isPrivate(e)) return Check.EXTERNAL_NOT_PRIVATE
        return Check.OK
    }

    /** The different addresses to try: the local one, then the external one (when set and different). */
    fun candidates(chosen: AddressPair): List<Candidate> {
        val list = ArrayList<Candidate>()
        if (chosen.local.isNotEmpty()) list.add(Candidate(chosen.local, Network.LOCAL))
        if (chosen.external.isNotEmpty() && chosen.external != chosen.local) list.add(Candidate(chosen.external, Network.EXTERNAL))
        return list
    }

    /** The attempts in order: [ROUNDS] rounds of local and external in turn (local, external, local, external). */
    fun attempts(chosen: AddressPair): List<Candidate> {
        val round = candidates(chosen)
        return (1..ROUNDS).flatMap { round }
    }

    // ---- the phone's preferences ----

    private fun preferences(context: Context) = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** The stored addresses; one that is missing or no longer acceptable is "" (to be asked). */
    fun read(context: Context): AddressPair {
        val p = preferences(context)
        fun valid(key: String): String {
            val host = clean(p.getString(key, null))
            return if (host != null && isPrivate(host)) host else ""
        }
        return AddressPair(valid(KEY_LOCAL), valid(KEY_EXTERNAL))
    }

    /** Stores the two addresses (cleaned) when they can be used; otherwise nothing changes. -> the outcome of [check]. */
    fun save(context: Context, local: String?, external: String?): Check {
        val outcome = check(local, external)
        if (outcome != Check.OK) return outcome
        val chosen = AddressPair(clean(local)!!, clean(external) ?: "")
        if (chosen != read(context)) {
            preferences(context).edit().putString(KEY_LOCAL, chosen.local).putString(KEY_EXTERNAL, chosen.external).apply()
        }
        return Check.OK
    }

    /** The addresses as the dashboard reads them: {"local":"...","external":"..."}. They are already clean: nothing to escape. */
    fun toJson(chosen: AddressPair): String = "{\"local\":\"${chosen.local}\",\"external\":\"${chosen.external}\"}"
}
