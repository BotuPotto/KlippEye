package com.klippeye.app

import android.content.Context
import java.io.IOException
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
 * KlippEye's HTTPS (app 1.7.0, KlippEye 1.93): the Raspberry makes its own certificate and no authority signs it, so
 * Android does not recognise it by itself. The dashboard (opened over http) gives the app the certificate's SHA-256
 * fingerprint (`KlippEyeApp.setCertificate`); the app remembers it for that Raspberry and from then on uses https accepting
 * ONLY that certificate: any other, even one valid for a real authority, is refused (certificate pinning).
 *
 * Plain Java apart from the preferences: the fingerprints and the check are tested on their own.
 */
object Certificates {
    // stored names, kept from the first versions
    private const val PREFERENCES = "klippeye"
    private const val KEY_PREFIX = "certificato_"
    private val FORMAT = Regex("^[0-9A-F]{2}(:[0-9A-F]{2}){31}$")

    /** The fingerprint as the dashboard and the browsers show it: "AB:CD:...", 32 pairs. */
    fun fingerprint(certificate: X509Certificate): String = fingerprint(certificate.encoded)

    fun fingerprint(der: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(der).joinToString(":") { "%02X".format(it) }

    /** The fingerprint cleaned (upper case, with the colons), or null when it is not one. */
    fun clean(text: String?): String? {
        val t = text?.trim()?.uppercase() ?: return null
        val withColons = if (!t.contains(':') && t.length == 64) t.chunked(2).joinToString(":") else t
        return if (FORMAT.matches(withColons)) withColons else null
    }

    private fun preferences(context: Context) = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** The fingerprint remembered for that Raspberry, or null (the app then does not try https). */
    fun read(context: Context, host: String): String? = clean(preferences(context).getString(KEY_PREFIX + host, null))

    /** Remembers the fingerprint for that Raspberry; "" or null forgets it (the dashboard says HTTPS is off). -> false for a bad fingerprint. */
    fun save(context: Context, host: String, fingerprint: String?): Boolean {
        val clean = clean(fingerprint)
        if (clean == null && !fingerprint.isNullOrBlank()) return false
        val editor = preferences(context).edit()
        if (clean == null) editor.remove(KEY_PREFIX + host) else editor.putString(KEY_PREFIX + host, clean)
        editor.apply()
        return true
    }

    /** A certificate check that accepts only the one with the `expected` fingerprint. */
    fun trusting(expected: String): X509TrustManager = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            throw CertificateException("not used")
        }

        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            val first = chain?.firstOrNull() ?: throw CertificateException("no certificate")
            if (fingerprint(first) != expected) throw CertificateException("the Raspberry's certificate changed")
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }

    fun socketFactory(expected: String): SSLSocketFactory {
        val context = SSLContext.getInstance("TLS")
        context.init(null, arrayOf<TrustManager>(trusting(expected)), null)
        return context.socketFactory
    }

    /**
     * Opens a connection to an address of the Raspberry: over https it accepts only the certificate remembered for that host
     * (the name written in the certificate does not matter: what matters is that it is that very certificate).
     */
    fun open(context: Context, url: URL): HttpURLConnection {
        val connection = url.openConnection() as HttpURLConnection
        if (connection is HttpsURLConnection) {
            val expected = read(context, url.host) ?: throw IOException("unknown certificate of the Raspberry")
            connection.sslSocketFactory = socketFactory(expected)
            // the name in the certificate may differ from the one in the app (another IP): the certificate itself is checked
            connection.setHostnameVerifier { _, session ->
                val first = try {
                    session.peerCertificates.firstOrNull() as? X509Certificate
                } catch (e: Exception) {
                    null
                }
                first != null && fingerprint(first) == expected
            }
        }
        return connection
    }
}
