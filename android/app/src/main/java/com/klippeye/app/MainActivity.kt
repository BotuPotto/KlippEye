package com.klippeye.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslCertificate
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.MimeTypeMap
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.URL
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * The app's only window: a WebView on the dashboard of the Raspberry, a splash while it looks for it, and the bridge
 * (`window.KlippEyeApp`) through which the dashboard uses what only an app can do (files, notifications, its own update...).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var splash: LinearLayout
    private lateinit var failureActions: LinearLayout

    // The addresses to try, in order (see Addresses.kt)
    private var candidates: List<Addresses.Candidate> = emptyList()
    private var candidateIndex = 0
    // When the page does not load the next address is tried, but only when this one was chosen because it answered
    private var cascade = true
    // The host of the last failed load: the WebView's error page must not uncover the splash
    private var errorHost: String? = null
    // Addresses written in the "Addresses" window: as soon as the dashboard is loaded it gets them, so it uses them too
    private var addressesForPage: Addresses.AddressPair? = null

    private var currentUrl = "http://127.0.0.1:${Addresses.PORT}/" // only until it has connected to an address
    // Another printer opened from the dashboard's top menu (app 1.6.0, see Printers.kt): "" = the main one
    @Volatile private var otherPrinter = ""
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    // The app's update: the download going on and, when Android first asks for the permission to install, what to resume
    private var updateJob: Job? = null
    private var waitingForPermission: AppUpdate.Request? = null

    // A file chosen for the page (<input type="file">, "Upload file" in the configuration files). The WebView waits until it
    // gets an answer: one is always given, even when the person cancels.
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        // parseResult gives null when the person cancelled; the page is told that too
        fileChooserCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
        fileChooserCallback = null
    }

    // Android 13+: the permission for the notifications is asked to the person (a system window). The dashboard's guided
    // set-up asks for it (KlippEyeApp.askNotificationPermission); the answer goes back to the page with the updated state.
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { _ ->
        PushSettings.apply(this)
        sendNotificationState()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webview)
        progress = findViewById(R.id.progress)
        statusText = findViewById(R.id.status)
        splash = findViewById(R.id.splash)
        failureActions = findViewById(R.id.failure_actions)
        findViewById<TextView>(R.id.btn_retry).setOnClickListener { detectAndLoad() }
        findViewById<TextView>(R.id.btn_addresses).setOnClickListener { showAddressesDialog() }

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false // the camera's live video starts by itself
            allowFileAccess = false // the dashboard comes from the Raspberry: the phone's own files are never opened as pages
            // Tells the dashboard what this app can do: 2 = choosing files ("Upload file"), 3 = also saving files in Download,
            // 4 = also the addresses of the Settings menu (setAddresses/getAddresses), 5 = also updating itself (appInfo/updateApp),
            // 6 = also receiving the notifications itself (notifySetup/notifyState..., see PushSettings.kt), 7 = also the back key
            // passed to the page (klippeyeBack) and the links to other sites opened outside the app, 9 = also the other printers
            // opened in the app (switchPrinter) and their notifications. With a lower number the dashboard leaves the feature off.
            userAgentString = "$userAgentString KlippEyeApp/9"
        }

        // Downloads: the WebView does not download by itself. The dashboard calls window.KlippEyeApp.saveUrl(address, name);
        // a link the WebView turns into a download goes through the listener instead.
        webView.addJavascriptInterface(DashboardBridge(), "KlippEyeApp")
        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            downloadFile(url, URLUtil.guessFileName(url, contentDisposition, mimeType))
        }
        webView.webChromeClient = chromeClient()
        webView.webViewClient = pageClient()

        // The back key goes to the dashboard first (see onBack)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = onBack(this)
        })

        // the printer opened last (when it was another one): the app starts from there
        val last = Printers.open(this)
        if (last.isNotEmpty() && Addresses.read(this).local.isNotEmpty() && !Printers.isMain(this, last)) openOtherPrinter(last) else detectAndLoad()

        // Notifications: the channels at once (Firebase uses them with the app closed too) and what was chosen on this phone
        Notifications.createChannels(this)
        PushSettings.apply(this)

        // The APKs downloaded for an earlier update are no longer needed (those just downloaded stay a few minutes)
        val updates = AppInstaller.folder(this)
        val oldUpdates = AppInstaller.oldFolder(this)
        Thread {
            AppUpdate.clean(updates, CLEAN_APK_AFTER_MS)
            oldUpdates.deleteRecursively()
        }.start()
    }

    private fun chromeClient() = object : WebChromeClient() {
        override fun onShowFileChooser(view: WebView?, callback: ValueCallback<Array<Uri>>?, params: FileChooserParams?): Boolean {
            fileChooserCallback?.onReceiveValue(null) // a choice still waiting is closed
            fileChooserCallback = callback
            val intent = params?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
            }
            return try {
                fileChooserLauncher.launch(intent)
                true
            } catch (e: Exception) {
                // no app to choose files: the page gets "no file" and does not stay blocked
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = null
                false
            }
        }
    }

    private fun pageClient() = object : WebViewClient() {
        /**
         * Only the Raspberry's pages stay in the window: a link to another site, to a store or to an app (ntfy://,
         * market://, intent://) opens outside, in the right app, instead of taking the dashboard's place.
         */
        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            if (request == null || !request.isForMainFrame) return false
            val uri = request.url
            val scheme = (uri.scheme ?: "").lowercase()
            if ((scheme == "http" || scheme == "https") && uri.host == hostOf(currentUrl)) return false
            if (scheme == "about" || scheme == "data" || scheme == "blob" || scheme == "javascript") return false
            openOutside(uri)
            return true
        }

        override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
            // the splash stays until the page has finished
        }

        override fun onPageFinished(view: WebView?, url: String?) {
            // After an error Android calls onPageFinished anyway, for its error page: the splash stays
            if (errorHost != null && errorHost == hostOf(url)) return
            splash.visibility = View.GONE
            webView.visibility = View.VISIBLE
            passAddressesToPage()
        }

        /**
         * App 1.7.0: the Raspberry's certificate is not signed by an authority. The page goes on only when it is the very
         * certificate whose fingerprint the dashboard gave (see Certificates.kt); any other error or certificate: stop.
         */
        override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
            val host = hostOf(error?.url)
            val expected = if (host != null) Certificates.read(this@MainActivity, host) else null
            val received = error?.certificate?.let { fingerprintOf(it) }
            if (expected != null && received == expected) handler?.proceed() else handler?.cancel()
        }

        override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
            if (request?.isForMainFrame != true) return
            // An old error, of an address that is no longer the one being tried, does not count
            if (candidates.isNotEmpty() && request.url.host != candidates[candidateIndex].host) return
            errorHost = request.url.host
            handleLoadError()
        }
    }

    /** The state of this phone's notifications, to the page (when it is a dashboard that listens). */
    private fun sendNotificationState() {
        if (!::webView.isInitialized) return
        webView.evaluateJavascript("window.klippeyeNotifyState && window.klippeyeNotifyState(${PushSettings.state(this, otherPrinter)})", null)
    }

    /** The SHA-256 fingerprint of the certificate the WebView received (Android 10+ gives it ready, before it is read again). */
    private fun fingerprintOf(certificate: SslCertificate): String? = try {
        val x509: X509Certificate? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            certificate.x509Certificate
        } else {
            val der = SslCertificate.saveState(certificate).getByteArray("x509-certificate")
            der?.let { CertificateFactory.getInstance("X.509").generateCertificate(it.inputStream()) as X509Certificate }
        }
        x509?.let { Certificates.fingerprint(it) }
    } catch (e: Exception) {
        null
    }

    /**
     * Where KlippEye answers on that Raspberry (app 1.7.0): https without a port when the app knows its certificate, then
     * http without a port, then the service's port. Each address must answer as KlippEye: another page may be at the
     * address without a port. Null when none answers.
     */
    private fun find(host: String): String? =
        Addresses.variants(host, Certificates.read(this, host) != null).firstOrNull { isKlippEye(it) }

    private fun isKlippEye(baseUrl: String): Boolean = try {
        val connection = Certificates.open(this, URL(URL(baseUrl), Addresses.PROBE_PATH))
        connection.connectTimeout = PROBE_TIMEOUT_MS
        connection.readTimeout = PROBE_TIMEOUT_MS
        connection.instanceFollowRedirects = false
        try {
            if (connection.responseCode != 200) {
                false
            } else {
                val body = connection.inputStream.use { readStart(it, PROBE_MAX_BYTES) }
                Addresses.isKlippEye(connection.contentType, body)
            }
        } finally {
            connection.disconnect()
        }
    } catch (e: Exception) {
        false
    }

    /** The first `max` bytes of a stream as text (InputStream.readNBytes exists only from Android 13). */
    private fun readStart(input: InputStream, max: Int): String {
        val buffer = ByteArray(max)
        var read = 0
        while (read < max) {
            val n = input.read(buffer, read, max - read)
            if (n < 0) break
            read += n
        }
        return String(buffer, 0, read, Charsets.UTF_8)
    }

    private fun hostOf(url: String?): String? = try {
        Uri.parse(url ?: "").host
    } catch (e: Exception) {
        null
    }

    /** The splash, with the status pill, while the app looks for a dashboard. */
    private fun showSplash(status: String, busy: Boolean) {
        splash.visibility = View.VISIBLE
        webView.visibility = View.INVISIBLE
        failureActions.visibility = View.GONE
        statusText.setTextColor(getColor(R.color.ke_text2))
        progress.visibility = if (busy) View.VISIBLE else View.GONE
        statusText.text = status
        errorHost = null
    }

    /** Opens the dashboard of another printer (chosen in its top menu): loaded here when it answers, otherwise back to the main one. */
    private fun openOtherPrinter(printer: String) {
        otherPrinter = printer
        Printers.remember(this, printer)
        showSplash(getString(R.string.status_connecting_printer, printer), busy = true)
        candidates = emptyList()
        cascade = false
        scope.launch {
            // with the port written it goes there; without, as for the main printer: without a port, then the service's port
            val address = withContext(Dispatchers.IO) {
                if (printer.contains(':')) Printers.url(printer).takeIf { isKlippEye(it) } else find(printer)
            }
            if (address != null) {
                currentUrl = address
                webView.loadUrl(address)
            } else {
                backToMainPrinter(printer)
            }
        }
    }

    private fun backToMainPrinter(printer: String) {
        Toast.makeText(this, getString(R.string.printer_not_answering, printer), Toast.LENGTH_LONG).show()
        detectAndLoad()
    }

    private fun networkName(candidate: Addresses.Candidate): String =
        getString(if (candidate.network == Addresses.Network.LOCAL) R.string.network_local else R.string.network_external)

    /** Looks for the Raspberry among the addresses (the first that answers wins) and loads the dashboard. */
    private fun detectAndLoad() {
        otherPrinter = ""
        Printers.remember(this, "")
        val chosen = Addresses.read(this)
        if (chosen.local.isEmpty()) {
            // First start (or an address no longer valid): there are no built-in addresses, the Raspberry's is asked
            showSplash(getString(R.string.status_first_start), busy = false)
            failureActions.visibility = View.VISIBLE
            showAddressesDialog(first = true)
            return
        }
        showSplash(getString(R.string.status_searching_local), busy = true)
        candidates = Addresses.candidates(chosen)
        val attempts = Addresses.attempts(chosen)
        scope.launch {
            var found = -1
            for ((index, candidate) in attempts.withIndex()) {
                if (index > 0) {
                    statusText.text = getString(R.string.status_attempt, index + 1, attempts.size, networkName(candidate), candidate.host)
                    if (index % candidates.size == 0) delay(ROUND_PAUSE_MS) // between two rounds the network has a moment to wake up
                }
                val address = withContext(Dispatchers.IO) { find(candidate.host) }
                if (address != null) {
                    found = candidates.indexOfFirst { it.host == candidate.host }
                    candidates = candidates.mapIndexed { i, c -> if (i == found) c.copy(url = address) else c }
                    break
                }
            }
            if (found >= 0) {
                cascade = true
                val candidate = candidates[found]
                connectTo(found, if (found == 0) getString(R.string.status_connected, candidate.host) else getString(R.string.status_connected_via, networkName(candidate), candidate.host))
            } else {
                // Nobody answers after two rounds: it stops and offers to try again or to change the addresses
                cascade = false
                candidateIndex = candidates.size - 1
                handleLoadError()
            }
        }
    }

    private fun connectTo(index: Int, message: String) {
        candidateIndex = index
        currentUrl = candidates[index].url
        errorHost = null
        statusText.text = message
        webView.loadUrl(currentUrl)
    }

    private fun handleLoadError() {
        if (otherPrinter.isNotEmpty()) return backToMainPrinter(otherPrinter)
        val next = candidateIndex + 1
        if (cascade && next < candidates.size) {
            connectTo(next, getString(R.string.status_switching, candidates[candidateIndex].host, networkName(candidates[next])))
        } else {
            // No other address to try: the spinner stops, the message turns into an error, and the person can try again or change the addresses
            progress.visibility = View.GONE
            statusText.setTextColor(getColor(R.color.ke_danger))
            statusText.text = getString(R.string.status_not_answering)
            failureActions.visibility = View.VISIBLE
        }
    }

    // ---- the Raspberry's addresses ----

    /** "ok", or why the addresses are refused, in the app's language. */
    private fun checkText(check: Addresses.Check): String = when (check) {
        Addresses.Check.OK -> "ok"
        Addresses.Check.LOCAL_INVALID -> getString(R.string.address_local_invalid)
        Addresses.Check.LOCAL_NOT_PRIVATE -> getString(R.string.address_local_not_private)
        Addresses.Check.EXTERNAL_INVALID -> getString(R.string.address_external_invalid)
        Addresses.Check.EXTERNAL_NOT_PRIVATE -> getString(R.string.address_external_not_private)
    }

    /**
     * The "Addresses" window, for the first start and for when the Raspberry changed address and the app cannot find it.
     * The new addresses apply to the app at once and, as soon as the dashboard is loaded, to its Settings menu too (one pair
     * of addresses, which the dashboard's camera uses in turn).
     */
    private fun showAddressesDialog(localText: String? = null, externalText: String? = null, first: Boolean = false) {
        val current = Addresses.read(this)
        val padding = (20 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding / 2, padding, 0)
        }
        fun field(hint: Int, value: String) = EditText(this).apply {
            setSingleLine()
            this.hint = getString(hint)
            setText(value)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        val localField = field(R.string.addresses_hint_local, localText ?: current.local)
        val externalField = field(R.string.addresses_hint_external, externalText ?: current.external)
        box.addView(localField)
        box.addView(externalField)
        val explanation = getString(R.string.addresses_explanation)
        AlertDialog.Builder(this)
            .setTitle(if (first) R.string.addresses_welcome_title else R.string.addresses_title)
            .setMessage(if (first) getString(R.string.addresses_welcome_message, explanation) else explanation)
            .setView(box)
            .setPositiveButton(if (first) R.string.addresses_connect else R.string.addresses_save) { _, _ ->
                val local = localField.text.toString()
                val external = externalField.text.toString()
                val outcome = Addresses.save(this, local, external)
                if (outcome == Addresses.Check.OK) {
                    addressesForPage = Addresses.read(this)
                    detectAndLoad()
                } else {
                    Toast.makeText(this, checkText(outcome), Toast.LENGTH_LONG).show()
                    showAddressesDialog(local, external, first) // it opens again with what was written
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** After the "Addresses" window: the loaded dashboard gets the same pair (when it is a dashboard that takes it). */
    private fun passAddressesToPage() {
        val pair = addressesForPage ?: return
        addressesForPage = null
        // They are already clean (letters, digits, dots and hyphens): they can be written between quotes
        webView.evaluateJavascript("window.klippeyeSetAddresses && window.klippeyeSetAddresses('${pair.local}', '${pair.external}')", null)
    }

    /** A link that is not the dashboard's: Android's app that can open it opens it (browser, store, ntfy). */
    private fun openOutside(uri: Uri) {
        val intent = if ((uri.scheme ?: "").equals("intent", ignoreCase = true)) {
            try {
                // only what an ordinary link may do: no component chosen by the page
                Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME).apply {
                    addCategory(Intent.CATEGORY_BROWSABLE)
                    component = null
                    selector = null
                }
            } catch (e: Exception) {
                null
            }
        } else {
            Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE)
        }
        try {
            if (intent != null) startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            Toast.makeText(this, if (uri.scheme == "ntfy") R.string.link_install_ntfy else R.string.link_no_app, Toast.LENGTH_LONG).show()
        }
    }

    /**
     * The bridge for the dashboard (`window.KlippEyeApp`). It runs on a WebView thread, so the work moves to the main thread.
     * The names of its calls and of what they answer are shared with every dashboard version: they never change.
     */
    inner class DashboardBridge {
        @JavascriptInterface
        fun saveUrl(url: String?, fileName: String?) {
            runOnUiThread { downloadFile(url, fileName) }
        }

        /**
         * The dashboard passes the addresses of its Settings menu: the app uses them at its next start. Answers "ok" or why
         * they are refused (only private networks). The addresses are the main printer's: another printer's dashboard does
         * not change them (app 1.6.0).
         */
        @JavascriptInterface
        fun setAddresses(local: String?, external: String?): String {
            if (otherPrinter.isNotEmpty()) return "ok"
            return checkText(Addresses.save(applicationContext, local, external))
        }

        /**
         * App 1.7.0: the SHA-256 fingerprint of the HTTPS certificate of this page's Raspberry (KlippEye 1.93), "" when HTTPS is
         * off. The app remembers it and from its next start uses https accepting only that certificate.
         */
        @JavascriptInterface
        fun setCertificate(fingerprint: String?): String {
            val host = hostOf(currentUrl) ?: return "no page"
            if (!Addresses.isPrivate(host)) return "private networks only"
            return if (Certificates.save(applicationContext, host, fingerprint)) "ok" else "invalid fingerprint"
        }

        /** The addresses the app uses now, as {"local":"...","external":"..."}: the dashboard compares them with its own. */
        @JavascriptInterface
        fun getAddresses(): String = Addresses.toJson(Addresses.read(applicationContext))

        /** The installed app's version, and whether Android lets it install updates: {"version":"1.0.0","code":10000,"canInstall":true}. */
        @JavascriptInterface
        fun appInfo(): String {
            val (name, code) = AppInstaller.installed(applicationContext)
            return AppUpdate.infoJson(name, code, AppInstaller.canInstall(applicationContext))
        }

        /**
         * The dashboard asks to update the app with the backend's APK: `path` is always /app/KlippEye.apk; `version`, `sha256`
         * and `size` are the ones the backend announced (the downloaded file is checked against them). The progress goes back
         * to the page through window.klippeyeAppUpdate (see [reportUpdate]).
         */
        @JavascriptInterface
        fun updateApp(path: String?, version: String?, sha256: String?, size: String?) {
            runOnUiThread { updateApp(path, version, sha256, size?.toLongOrNull() ?: 0L) }
        }

        // ---- the notifications of this phone (app 6, see PushSettings.kt) ----

        /** How the Raspberry has set up the notifications, and the person's choice: see [PushSettings.update]. Answers the state. */
        @JavascriptInterface
        fun notifySetup(json: String?): String {
            val printer = otherPrinter // the page's printer: its notifications are added to those of the others
            PushSettings.update(applicationContext, json, printer)
            return PushSettings.state(applicationContext, printer)
        }

        /** {permission, battery, receive, chosen, mode, connected, lastMessageAt, ...}: see [PushSettings.state]. */
        @JavascriptInterface
        fun notifyState(): String = PushSettings.state(applicationContext, otherPrinter)

        /**
         * More printers (app 1.6.0): the dashboard asks to open another printer, {"host": "192.168.1.50[:port]", "name": "..."}.
         * Answers "ok" or "refused" (not an address of a private network).
         */
        @JavascriptInterface
        fun switchPrinter(json: String?): String {
            val printer = try {
                Printers.clean(JSONObject(json ?: "{}").optString("host", ""))
            } catch (e: Exception) {
                null
            } ?: return "refused"
            runOnUiThread { if (Printers.isMain(this@MainActivity, printer)) detectAndLoad() else openOtherPrinter(printer) }
            return "ok"
        }

        /** Shows Android's window for the notification permission; when Android no longer shows it, opens the app's settings. */
        @JavascriptInterface
        fun askNotificationPermission() {
            runOnUiThread { askNotificationPermissionNow() }
        }

        /** Asks Android not to put KlippEye to sleep (without it the connection to ntfy breaks while the phone is still). */
        @JavascriptInterface
        fun askBatteryExemption() {
            runOnUiThread { askBatteryExemptionNow() }
        }

        /**
         * The camera in full screen (dashboard 1.35, app 1.5.0): `on` hides Android's bars (they come back for a moment with
         * a swipe from the edge); `landscape` turns the screen sideways, following the sensor between the two ways.
         * With `on` false everything goes back as it was.
         */
        @JavascriptInterface
        fun setFullscreen(on: Boolean, landscape: Boolean) {
            runOnUiThread { fullscreen(on, landscape) }
        }

        /** KlippEye's notification settings in Android (to switch them on again or hide the ongoing notification). */
        @JavascriptInterface
        fun openNotificationSettings() {
            runOnUiThread { openNotificationSettingsNow() }
        }
    }

    private fun askNotificationPermissionNow() {
        val preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE)
        // Android shows its window twice at most; after that only the settings can change it
        val canAsk = shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS) || !preferences.getBoolean(KEY_PERMISSION_ASKED, false)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifications.permissionGranted(this) && canAsk) {
            preferences.edit().putBoolean(KEY_PERMISSION_ASKED, true).apply()
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            openNotificationSettingsNow()
        }
    }

    @SuppressLint("BatteryLife") // the app is not on Google Play: it is the only way to receive without delays
    private fun askBatteryExemptionNow() {
        try {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            try {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (e2: Exception) {
                Toast.makeText(this, R.string.battery_settings_hint, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun fullscreen(on: Boolean, landscape: Boolean) {
        val bars = WindowCompat.getInsetsController(window, window.decorView)
        if (on) {
            bars.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            bars.show(WindowInsetsCompat.Type.systemBars())
        }
        requestedOrientation = if (on && landscape) ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
    }

    private fun openNotificationSettingsNow() {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, R.string.notification_settings_hint, Toast.LENGTH_LONG).show()
        }
    }

    // ---- the app's update ----

    /**
     * Tells the page how the update goes (when the dashboard is one that listens): window.klippeyeAppUpdate({stato, ...}).
     * The names are the bridge's, shared with every dashboard version: "stato" ("state") is "scarico" (downloading, with
     * "fatto" and "totale" in bytes), "permesso" (waiting for the permission), "installazione" (Android's installer is open)
     * or "errore" (with "messaggio", the text shown to the person).
     */
    private fun reportUpdate(state: String, vararg details: Pair<String, Any>) {
        val message = JSONObject().put("stato", state)
        for ((key, value) in details) message.put(key, value)
        webView.evaluateJavascript("window.klippeyeAppUpdate && window.klippeyeAppUpdate($message)", null)
    }

    private fun reportUpdateError(text: String) = reportUpdate(UPDATE_ERROR, "messaggio" to text)

    /** The text for the person of a failed update, in the app's language. */
    private fun updateErrorText(error: Throwable): String {
        if (error !is AppUpdate.UpdateException) return getString(R.string.update_error_connection, error.message ?: error.javaClass.simpleName)
        val id = when (error.reason) {
            AppUpdate.Reason.BAD_ADDRESS -> R.string.update_error_bad_address
            AppUpdate.Reason.OTHER_SERVER -> R.string.update_error_other_server
            AppUpdate.Reason.BAD_VERSION -> R.string.update_error_bad_version
            AppUpdate.Reason.UP_TO_DATE -> R.string.update_error_up_to_date
            AppUpdate.Reason.NO_FINGERPRINT -> R.string.update_error_no_fingerprint
            AppUpdate.Reason.BAD_SIZE -> R.string.update_error_bad_size
            AppUpdate.Reason.NO_STORAGE -> R.string.update_error_no_storage
            AppUpdate.Reason.NO_APK -> R.string.update_error_no_apk
            AppUpdate.Reason.HTTP_ERROR -> R.string.update_error_http
            AppUpdate.Reason.NOT_ANNOUNCED -> R.string.update_error_not_announced
            AppUpdate.Reason.TOO_BIG -> R.string.update_error_too_big
            AppUpdate.Reason.INTERRUPTED -> R.string.update_error_interrupted
            AppUpdate.Reason.DAMAGED -> R.string.update_error_damaged
            AppUpdate.Reason.CANNOT_SAVE -> R.string.update_error_cannot_save
        }
        return getString(id, error.detail)
    }

    private fun updateApp(path: String?, version: String?, sha256: String?, size: Long) {
        if (updateJob?.isActive == true) return // already going on: the page already gets the progress
        val request = try {
            AppUpdate.checkRequest(URL(currentUrl), path, version, sha256, size, AppInstaller.installed(this).second)
        } catch (e: Exception) {
            reportUpdateError(updateErrorText(e))
            return
        }
        if (!AppInstaller.canInstall(this)) {
            // Android 8+: KlippEye must first be allowed to "Install unknown apps"; back here (onResume) it goes on from this point
            waitingForPermission = request
            reportUpdate("permesso")
            try {
                startActivity(AppInstaller.permissionIntent(this))
            } catch (e: Exception) {
                waitingForPermission = null
                reportUpdateError(getString(R.string.install_permission_hint))
            }
            return
        }
        downloadAndInstall(request)
    }

    private fun downloadAndInstall(request: AppUpdate.Request) {
        reportUpdate("scarico", "fatto" to 0L, "totale" to request.size)
        updateJob = scope.launch {
            var lastPercent = -1L
            val outcome = withContext(Dispatchers.IO) {
                runCatching {
                    AppUpdate.download(request, AppInstaller.folder(this@MainActivity), { Certificates.open(this@MainActivity, it) }) { received ->
                        // one message per percentage point is enough for the page
                        val percent = received * 100 / request.size
                        if (percent != lastPercent) {
                            lastPercent = percent
                            runOnUiThread { reportUpdate("scarico", "fatto" to received, "totale" to request.size) }
                        }
                    }
                }
            }
            outcome.onSuccess { file ->
                try {
                    startActivity(AppInstaller.installIntent(this@MainActivity, file))
                    reportUpdate("installazione")
                } catch (e: Exception) {
                    reportUpdateError(getString(R.string.installer_failed, e.message ?: e.javaClass.simpleName))
                }
            }.onFailure { error ->
                reportUpdateError(updateErrorText(error))
            }
        }
    }

    override fun onPause() {
        super.onPause()
        // The login cookie stays saved even if Android closes the app right after: no password to type again
        CookieManager.getInstance().flush()
    }

    override fun onResume() {
        super.onResume()
        // Back from Android's settings (permission, battery): the guided set-up sees at once how it went
        sendNotificationState()
        // Back from Android's permission page: when KlippEye can now install, the update goes on by itself
        val request = waitingForPermission ?: return
        waitingForPermission = null
        if (AppInstaller.canInstall(this)) downloadAndInstall(request) else reportUpdateError(getString(R.string.install_permission_missing))
    }

    // ---- downloading the Raspberry's files (configuration files, logs) ----

    /** Downloads `rawUrl` (relative to the dashboard or complete) and saves it in Download as `requestedName`. */
    private fun downloadFile(rawUrl: String?, requestedName: String?) {
        val base = URL(currentUrl)
        val target = try {
            URL(base, rawUrl ?: "")
        } catch (e: Exception) {
            null
        }
        // Only files of the Raspberry the app is connected to (http/https, same address): no blob:, data: or other sites
        if (target == null || (target.protocol != "http" && target.protocol != "https") || target.host != base.host) {
            Toast.makeText(this, R.string.download_not_supported, Toast.LENGTH_LONG).show()
            return
        }
        val fileName = cleanFileName(if (requestedName.isNullOrBlank()) target.path.substringAfterLast('/') else requestedName)
        Toast.makeText(this, getString(R.string.download_started, fileName), Toast.LENGTH_SHORT).show()
        scope.launch {
            val outcome = withContext(Dispatchers.IO) { runCatching { saveToDownloads(target, fileName) } }
            outcome.onSuccess { savedAs ->
                Toast.makeText(this@MainActivity, getString(R.string.download_saved, savedAs), Toast.LENGTH_LONG).show()
            }.onFailure { error ->
                Toast.makeText(this@MainActivity, getString(R.string.download_failed, error.message ?: error.javaClass.simpleName), Toast.LENGTH_LONG).show()
            }
        }
    }

    /** The name without path separators or characters the phone does not accept in a file name. */
    private fun cleanFileName(raw: String): String {
        val name = raw.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), "_").trim().take(MAX_FILE_NAME)
        return if (name.isEmpty() || name.all { it == '.' }) "download" else name
    }

    private fun saveToDownloads(url: URL, fileName: String): String {
        val connection = Certificates.open(this, url)
        connection.connectTimeout = DOWNLOAD_CONNECT_TIMEOUT_MS
        connection.readTimeout = DOWNLOAD_READ_TIMEOUT_MS
        // With the password on (KlippEye 1.2.0) the Raspberry wants the login token: it is the WebView's cookie
        CookieManager.getInstance().getCookie(url.toString())?.let { connection.setRequestProperty("Cookie", it) }
        try {
            val code = connection.responseCode
            if (code !in 200..299) throw IOException("HTTP $code")
            return connection.inputStream.use { input -> writeToDownloads(fileName, input) }
        } finally {
            connection.disconnect()
        }
    }

    /**
     * Android 10+: in the public Download folder through MediaStore (no permission); a name already taken becomes
     * "name (1).ext". Before Android 10 the public folder would need a permission: the file goes into the app's own Download
     * folder (Android/data/com.klippeye.app/files/Download). -> where it was saved, to tell the person.
     */
    private fun writeToDownloads(fileName: String, input: InputStream): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val extension = fileName.substringAfterLast('.', "").lowercase()
            // A type that does not match the extension would make Android add another one (.cfg would become .cfg.txt)
            val mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) ?: "application/octet-stream"
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: throw IOException("Download folder not available")
            try {
                val output = contentResolver.openOutputStream(uri) ?: throw IOException("the file cannot be written")
                output.use { input.copyTo(it) }
                contentResolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
            } catch (e: Exception) {
                contentResolver.delete(uri, null, null) // nothing half-written
                throw e
            }
            val savedName = contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
            return "Download/" + (savedName ?: fileName)
        }

        val folder = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: throw IOException("storage not available")
        folder.mkdirs()
        val dot = fileName.lastIndexOf('.')
        val stem = if (dot > 0) fileName.substring(0, dot) else fileName
        val extension = if (dot > 0) fileName.substring(dot) else ""
        var file = File(folder, fileName)
        var copy = 1
        while (file.exists()) {
            file = File(folder, "$stem ($copy)$extension")
            copy++
        }
        FileOutputStream(file).use { input.copyTo(it) }
        return file.absolutePath
    }

    /**
     * The phone's back key goes to the dashboard first: it closes the open guide or dialog, goes back to the previous page of
     * the menu or the previous step of the guided set-up (window.klippeyeBack). Only when the page has nothing to close does
     * it do the usual: the WebView's previous page, then leaving the app.
     */
    private fun onBack(callback: OnBackPressedCallback) {
        if (webView.visibility != View.VISIBLE) return goBack(callback)
        webView.evaluateJavascript("(function(){ try { return window.klippeyeBack && window.klippeyeBack() ? '1' : '' } catch (e) { return '' } })()") { answer ->
            if (answer?.contains("1") != true) goBack(callback)
        }
    }

    private fun goBack(callback: OnBackPressedCallback) {
        if (webView.canGoBack()) {
            webView.goBack()
            return
        }
        // nothing left in the app: Android's own back (it closes the window)
        callback.isEnabled = false
        onBackPressedDispatcher.onBackPressed()
        callback.isEnabled = true
    }

    override fun onDestroy() {
        super.onDestroy()
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        scope.cancel()
    }

    private companion object {
        /** The APKs downloaded for an update are thrown away at the app's start when older than 10 minutes. */
        const val CLEAN_APK_AFTER_MS = 10 * 60 * 1000L
        /** ZeroTier and VPNs sometimes take a couple of seconds to answer the first time. */
        const val PROBE_TIMEOUT_MS = 2500
        const val PROBE_MAX_BYTES = 4096
        const val ROUND_PAUSE_MS = 800L
        const val DOWNLOAD_CONNECT_TIMEOUT_MS = 5000
        const val DOWNLOAD_READ_TIMEOUT_MS = 30000
        const val MAX_FILE_NAME = 120
        const val UPDATE_ERROR = "errore"
        // stored names, kept from the first versions
        const val PREFERENCES = "klippeye"
        const val KEY_PERMISSION_ASKED = "permesso_chiesto"
    }
}
