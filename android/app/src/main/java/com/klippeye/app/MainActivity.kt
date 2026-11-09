package com.klippeye.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
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
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var splash: LinearLayout
    private lateinit var failureActions: LinearLayout

    // Gli indirizzi da provare, nell'ordine (vedi Indirizzi.kt): quelli del menu Impostazioni della dashboard, poi quelli di fabbrica.
    private var candidates: List<Indirizzi.Candidato> = emptyList()
    private var candidateIndex = 0
    // Se la pagina non si carica si prova l'indirizzo dopo, ma solo se questo era stato scelto perche' rispondeva
    private var cascade = true
    // Host dell'ultimo caricamento fallito: la pagina di errore del WebView non deve scoprire la splash
    private var errorHost: String? = null
    // Indirizzi scritti nella finestra "Indirizzi": appena la dashboard e' caricata glieli passiamo, cosi' li usa anche lei
    private var addressesForPage: Indirizzi.Coppia? = null

    private var currentUrl = "http://127.0.0.1:${Indirizzi.PORTA}/" // vale solo finche' non si e' collegata a un indirizzo
    // Un'altra stampante aperta dal menu in alto della dashboard (app 1.6.0, vedi Stampanti.kt): "" = la principale
    @Volatile private var altra = ""
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    // Aggiornamento dell'app: lo scaricamento in corso e, se Android chiede prima il permesso di installare, cosa riprendere al ritorno
    private var aggiornamento: Job? = null
    private var inAttesaDelPermesso: Aggiornamento.Richiesta? = null

    // Scelta file richiesta dalla pagina (<input type="file">, "Carica file" nei file di configurazione).
    // Il WebView resta in attesa finché non riceve la risposta: va data sempre, anche se si annulla.
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        // parseResult dà null se l'utente ha annullato; anche l'annullamento va comunicato alla pagina
        val files = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
        fileChooserCallback?.onReceiveValue(files)
        fileChooserCallback = null
    }

    // Android 13+: il permesso per le notifiche va chiesto all'utente (compare una finestra di sistema). Lo chiede la procedura
    // guidata della dashboard (KlippEyeApp.askNotificationPermission); la risposta torna alla pagina con lo stato aggiornato.
    private val permessoNotifiche = registerForActivityResult(ActivityResultContracts.RequestPermission()) { _ ->
        Ascolto.applica(this)
        dicoStatoNotifiche()
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

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.settings.allowFileAccessFromFileURLs = true
        webView.settings.allowUniversalAccessFromFileURLs = true
        // Dice alla dashboard cosa sa fare questa app: 2 = scelta file ("Carica file"), 3 = anche salvare file
        // nella cartella Download, 4 = anche usare gli indirizzi del menu Impostazioni (setAddresses/getAddresses),
        // 5 = anche aggiornarsi da sola (appInfo/updateApp), 6 = anche ricevere le notifiche da sola (notifySetup/notifyState...,
        // vedi Ascolto.kt), 7 = anche il tasto indietro passato alla pagina (klippeyeBack) e i collegamenti esterni aperti
        // fuori dall'app (store, ntfy, siti), 9 = anche le altre stampanti aperte nell'app (switchPrinter) e le loro notifiche.
        // Con un numero più basso la dashboard lascia disattivata la funzione.
        webView.settings.userAgentString = webView.settings.userAgentString + " KlippEyeApp/9"

        // Download: il WebView non scarica da solo. La dashboard chiama window.KlippEyeApp.saveUrl(indirizzo, nome);
        // un collegamento che il WebView trasforma in download passa invece dal listener.
        webView.addJavascriptInterface(DashboardBridge(), "KlippEyeApp")
        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            downloadFile(url, URLUtil.guessFileName(url, contentDisposition, mimeType))
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: WebChromeClient.FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null) // una scelta ancora in attesa viene chiusa
                fileChooserCallback = callback
                val intent = params?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                }
                return try {
                    fileChooserLauncher.launch(intent)
                    true
                } catch (e: Exception) {
                    // nessuna app per scegliere i file: la pagina riceve "nessun file" e non resta bloccata
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    false
                }
            }
        }

        webView.webViewClient = object : WebViewClient() {
            /**
             * Solo le pagine del Raspberry restano nella finestra: un collegamento a un altro sito, a uno store o a un'app
             * (ntfy://, market://, intent://) si apre fuori, nell'app giusta, invece di prendere il posto della dashboard.
             */
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                if (request == null || !request.isForMainFrame) return false
                val uri = request.url
                val scheme = (uri.scheme ?: "").lowercase()
                if ((scheme == "http" || scheme == "https") && uri.host == hostOf(currentUrl)) return false
                if (scheme == "about" || scheme == "data" || scheme == "blob" || scheme == "javascript") return false
                apriFuori(uri)
                return true
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                // Splash resta visibile
            }
            override fun onPageFinished(view: WebView?, url: String?) {
                // Dopo un errore Android chiama comunque onPageFinished, per la sua pagina di errore: la splash resta
                if (errorHost != null && errorHost == hostOf(url)) return
                // Nasconde splash e mostra webview
                splash.visibility = View.GONE
                webView.visibility = View.VISIBLE
                passAddressesToPage()
            }
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) {
                    // Un errore vecchio, di un indirizzo che non e' piu' quello in prova, non conta
                    if (candidates.isNotEmpty() && request.url.host != candidates[candidateIndex].host) return
                    errorHost = request.url.host
                    handleLoadError()
                }
            }
        }

        // l'ultima stampante aperta (se era un'altra): si riparte da li'
        val ultima = Stampanti.aperta(this)
        if (ultima.isNotEmpty() && Indirizzi.leggi(this).locale.isNotEmpty() && !Stampanti.principale(this, ultima)) apriAltra(ultima) else detectAndLoad()
        avviaNotifiche()
        // Gli APK scaricati per un aggiornamento precedente non servono piu' (quelli appena scaricati restano qualche minuto)
        val cartellaAggiornamenti = AggiornamentoAndroid.cartella(this)
        Thread { Aggiornamento.pulisci(cartellaAggiornamenti, PULIZIA_APK_DOPO_MS) }.start()
    }

    /**
     * Notifiche: i canali subito (Firebase li usa anche con l'app chiusa) e cio' che era stato scelto su questo telefono (ascolto
     * ntfy o iscrizione Firebase). Il permesso e la scelta li fa la procedura guidata della dashboard (Impostazioni → Notifiche).
     */
    private fun avviaNotifiche() {
        Notifiche.creaCanali(this)
        Ascolto.applica(this)
    }

    /** Lo stato delle notifiche di questo telefono alla pagina (se e' una dashboard che lo ascolta). */
    private fun dicoStatoNotifiche() {
        if (!::webView.isInitialized) return
        webView.evaluateJavascript("window.klippeyeNotifyState && window.klippeyeNotifyState(${Ascolto.stato(this, altra)})", null)
    }

    private fun hostOf(url: String?): String? = try {
        Uri.parse(url ?: "").host
    } catch (e: Exception) {
        null
    }

    /**
     * Apre la dashboard di un'altra stampante (scelta nel suo menu in alto): se risponde la carica qui, altrimenti lo dice e
     * torna alla principale.
     */
    private fun apriAltra(stampante: String) {
        altra = stampante
        Stampanti.apri(this, stampante)
        splash.visibility = View.VISIBLE
        webView.visibility = View.INVISIBLE
        failureActions.visibility = View.GONE
        statusText.setTextColor(getColor(R.color.vz_text2))
        progress.visibility = View.VISIBLE
        statusText.text = "Mi collego a $stampante..."
        errorHost = null
        candidates = emptyList()
        cascade = false
        val indirizzo = Stampanti.url(stampante)
        scope.launch {
            if (withContext(Dispatchers.IO) { isReachable(indirizzo) }) {
                currentUrl = indirizzo
                webView.loadUrl(indirizzo)
            } else {
                tornaAllaPrincipale(stampante)
            }
        }
    }

    private fun tornaAllaPrincipale(stampante: String) {
        Toast.makeText(this, "$stampante non risponde: torno alla stampante principale", Toast.LENGTH_LONG).show()
        detectAndLoad()
    }

    /** Cerca il Raspberry tra gli indirizzi (il primo che risponde vince) e carica la dashboard. */
    private fun detectAndLoad() {
        altra = ""
        Stampanti.apri(this, "")
        splash.visibility = View.VISIBLE
        webView.visibility = View.INVISIBLE
        failureActions.visibility = View.GONE
        statusText.setTextColor(getColor(R.color.vz_text2))
        errorHost = null

        val scelti = Indirizzi.leggi(this)
        if (scelti.locale.isEmpty()) {
            // Primo avvio (o indirizzo non piu' valido): niente indirizzi "di fabbrica", si chiede quello del Raspberry
            progress.visibility = View.GONE
            statusText.text = "Scrivi l'indirizzo del Raspberry per cominciare."
            failureActions.visibility = View.VISIBLE
            showAddressesDialog(first = true)
            return
        }
        progress.visibility = View.VISIBLE
        statusText.text = "Cerco KlippEye in rete locale..."
        candidates = Indirizzi.candidati(scelti)
        val attempts = Indirizzi.tentativi(scelti)
        scope.launch {
            var found = -1
            for ((index, candidate) in attempts.withIndex()) {
                if (index > 0) {
                    statusText.text = "Tentativo ${index + 1} di ${attempts.size}: ${candidate.etichetta} ${candidate.host}..."
                    if (index % candidates.size == 0) delay(800) // tra un giro e l'altro la rete ha un attimo per svegliarsi
                }
                if (withContext(Dispatchers.IO) { isReachable(candidate.url) }) {
                    found = candidates.indexOfFirst { it.host == candidate.host }
                    break
                }
            }
            if (found >= 0) {
                cascade = true
                val candidate = candidates[found]
                connectTo(found, if (found == 0) "Connesso a ${candidate.host}" else "Connesso via ${candidate.etichetta} ${candidate.host}")
            } else {
                // Nessuno risponde dopo due giri: si ferma e propone di riprovare o di cambiare gli indirizzi
                cascade = false
                candidateIndex = candidates.size - 1
                handleLoadError()
            }
        }
    }

    private fun isReachable(baseUrl: String): Boolean {
        return try {
            val url = URL(baseUrl)
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 2500 // ZeroTier e le VPN a volte impiegano un paio di secondi a rispondere la prima volta
            conn.readTimeout = 2500
            conn.requestMethod = "GET"
            conn.connect()
            val code = conn.responseCode
            conn.disconnect()
            code in 200..399
        } catch (e: Exception) {
            false
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
        if (altra.isNotEmpty()) return tornaAllaPrincipale(altra)
        val next = candidateIndex + 1
        if (cascade && next < candidates.size) {
            connectTo(next, "${candidates[candidateIndex].host} non risponde, passo a ${candidates[next].etichetta}...")
        } else {
            // Nessun altro indirizzo da provare: lo spinner si ferma, il messaggio diventa d'errore e si puo' riprovare o cambiare gli indirizzi.
            progress.visibility = View.GONE
            statusText.setTextColor(getColor(R.color.vz_danger))
            statusText.text = "KlippEye non risponde. Controlla che il Raspberry sia acceso e in rete (e ZeroTier, se lo usi), oppure gli indirizzi."
            failureActions.visibility = View.VISIBLE
        }
    }

    // ---- Indirizzi del Raspberry ----

    /**
     * La finestra "Indirizzi", per quando il Raspberry ha cambiato indirizzo e l'app non lo trova piu'.
     * Gli indirizzi nuovi valgono per l'app subito e, appena la dashboard e' caricata, anche per il suo menu Impostazioni
     * (un'unica coppia di indirizzi, che la camera della dashboard usa a sua volta).
     */
    private fun showAddressesDialog(localText: String? = null, externalText: String? = null, first: Boolean = false) {
        val current = Indirizzi.leggi(this)
        val padding = (20 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding / 2, padding, 0)
        }
        fun field(hint: String, value: String) = EditText(this).apply {
            setSingleLine()
            this.hint = hint
            setText(value)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        val localField = field("IP locale, es. 192.168.1.20", localText ?: current.locale)
        val externalField = field("IP esterno (facoltativo: ZeroTier, VPN)", externalText ?: current.esterno)
        box.addView(localField)
        box.addView(externalField)
        val spiegazione = "Lo stesso indirizzo che usi per aprire l'interfaccia della stampante dal browser (senza http:// e senza porta), per esempio " +
            "192.168.1.20 oppure stampante.local. L'esterno serve solo se apri KlippEye da fuori casa con ZeroTier o una VPN."
        AlertDialog.Builder(this)
            .setTitle(if (first) "Benvenuto in KlippEye" else "Indirizzi del Raspberry")
            .setMessage(if (first) "Dov'e' la tua stampante? $spiegazione" else spiegazione)
            .setView(box)
            .setPositiveButton(if (first) "Collegati" else "Salva e riprova") { _, _ ->
                val local = localField.text.toString()
                val external = externalField.text.toString()
                val outcome = Indirizzi.salva(this, local, external)
                if (outcome == "ok") {
                    addressesForPage = Indirizzi.leggi(this)
                    detectAndLoad()
                } else {
                    Toast.makeText(this, outcome, Toast.LENGTH_LONG).show()
                    showAddressesDialog(local, external, first) // si riapre con quello che era stato scritto
                }
            }
            .setNegativeButton("Annulla", null)
            .show()
    }

    /** Dopo la finestra "Indirizzi": la dashboard caricata riceve la stessa coppia (se e' una dashboard che la sa prendere). */
    private fun passAddressesToPage() {
        val pair = addressesForPage ?: return
        addressesForPage = null
        // Sono gia' puliti (lettere, cifre, punti e trattini): si possono scrivere tra apici
        webView.evaluateJavascript("window.klippeyeSetAddresses && window.klippeyeSetAddresses('${pair.locale}', '${pair.esterno}')", null)
    }

    /** Un collegamento che non e' della dashboard: lo apre l'app di Android che lo sa aprire (browser, store, ntfy). */
    private fun apriFuori(uri: Uri) {
        val intent = if ((uri.scheme ?: "").equals("intent", ignoreCase = true)) {
            try {
                Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME).apply { addCategory(Intent.CATEGORY_BROWSABLE); component = null; selector = null }
            } catch (e: Exception) {
                null
            }
        } else {
            Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE)
        }
        try {
            if (intent != null) startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            Toast.makeText(this, if (uri.scheme == "ntfy") "Installa prima l'app ntfy" else "Nessuna app per aprire questo collegamento", Toast.LENGTH_LONG).show()
        }
    }

    // ---- Download dei file del Raspberry (file di configurazione, log) ----

    /** Ponte per la dashboard. Gira su un thread del WebView, quindi il lavoro passa dal thread principale. */
    inner class DashboardBridge {
        @JavascriptInterface
        fun saveUrl(url: String?, fileName: String?) {
            runOnUiThread { downloadFile(url, fileName) }
        }

        /**
         * La dashboard comunica gli indirizzi del suo menu Impostazioni: l'app li usa alla prossima apertura.
         * Risponde "ok" oppure il motivo per cui non li accetta (solo indirizzi di reti private).
         */
        @JavascriptInterface
        fun setAddresses(local: String?, external: String?): String =
            // gli indirizzi sono quelli della stampante principale: la dashboard di un'altra stampante non li cambia (app 1.6.0)
            if (altra.isNotEmpty()) "ok" else Indirizzi.salva(applicationContext, local, external)

        /** Gli indirizzi che l'app usa ora, come {"local":"...","external":"..."}: la dashboard li confronta con i suoi. */
        @JavascriptInterface
        fun getAddresses(): String = Indirizzi.comeJson(Indirizzi.leggi(applicationContext))

        /** Versione dell'app installata e se Android le lascia installare aggiornamenti: {"version":"1.0.0","code":10000,"canInstall":true}. */
        @JavascriptInterface
        fun appInfo(): String {
            val (nome, codice) = AggiornamentoAndroid.installata(applicationContext)
            return Aggiornamento.comeJson(nome, codice, AggiornamentoAndroid.puoInstallare(applicationContext))
        }

        /**
         * La dashboard chiede di aggiornare l'app con l'APK del Brain: `path` e' sempre /app/KlippEye.apk, `version`, `sha256` e
         * `size` sono quelli annunciati dal Brain (l'app controlla il file scaricato contro questi). L'avanzamento torna alla
         * pagina chiamando window.klippeyeAppUpdate({stato: "scarico" | "permesso" | "installazione" | "errore", ...}).
         */
        @JavascriptInterface
        fun updateApp(path: String?, version: String?, sha256: String?, size: String?) {
            runOnUiThread { aggiornaApp(path, version, sha256, size?.toLongOrNull() ?: 0L) }
        }

        // ---- Notifiche su questo telefono (app 6, vedi Ascolto.kt) ----

        /** Come sono impostate le notifiche dal Raspberry e la scelta della persona: vedi [Ascolto.imposta]. Risponde lo stato. */
        @JavascriptInterface
        fun notifySetup(json: String?): String {
            val stampante = altra // la stampante della pagina: le sue notifiche si aggiungono a quelle delle altre
            Ascolto.imposta(applicationContext, json, stampante)
            return Ascolto.stato(applicationContext, stampante)
        }

        /** {permission, battery, receive, chosen, mode, connected, lastMessageAt, ...}: vedi [Ascolto.stato]. */
        @JavascriptInterface
        fun notifyState(): String = Ascolto.stato(applicationContext, altra)

        /**
         * Piu' stampanti (app 1.6.0): la dashboard chiede di aprire un'altra stampante, {"host": "192.168.1.50[:porta]",
         * "name": "..."}. Risponde "ok" oppure "refused" (non e' un indirizzo di una rete privata).
         */
        @JavascriptInterface
        fun switchPrinter(json: String?): String {
            val stampante = try {
                Stampanti.pulisci(JSONObject(json ?: "{}").optString("host", ""))
            } catch (e: Exception) {
                null
            } ?: return "refused"
            runOnUiThread { if (Stampanti.principale(this@MainActivity, stampante)) detectAndLoad() else apriAltra(stampante) }
            return "ok"
        }

        /** Mostra la finestra di Android per il permesso delle notifiche; se Android non la mostra piu', apre le impostazioni dell'app. */
        @JavascriptInterface
        fun askNotificationPermission() {
            runOnUiThread {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !Notifiche.permessoConcesso(this@MainActivity) &&
                    (shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS) || !getSharedPreferences("klippeye", MODE_PRIVATE).getBoolean("permesso_chiesto", false))
                ) {
                    getSharedPreferences("klippeye", MODE_PRIVATE).edit().putBoolean("permesso_chiesto", true).apply()
                    permessoNotifiche.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    apriImpostazioniNotifiche()
                }
            }
        }

        /** Chiede ad Android di non addormentare KlippEye (senza, il collegamento a ntfy si interrompe a telefono fermo). */
        @SuppressLint("BatteryLife") // l'app non e' su Google Play: e' l'unico modo per ricevere senza ritardi
        @JavascriptInterface
        fun askBatteryExemption() {
            runOnUiThread {
                try {
                    startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                } catch (e: Exception) {
                    try {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    } catch (e2: Exception) {
                        Toast.makeText(this@MainActivity, "Apri Impostazioni > App > KlippEye > Batteria e scegli «Senza limitazioni»", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }

        /**
         * La camera a schermo intero (dashboard 1.35, app 1.5.0): `on` nasconde le barre di Android (ricompaiono per un
         * momento scorrendo dal bordo); `landscape` gira lo schermo in orizzontale, seguendo il sensore tra i due versi.
         * Con `on` falso tutto torna com'era.
         */
        @JavascriptInterface
        fun setFullscreen(on: Boolean, landscape: Boolean) {
            runOnUiThread { schermoIntero(on, landscape) }
        }

        /** Le impostazioni delle notifiche di KlippEye in Android (per riattivarle o nascondere la notifica fissa). */
        @JavascriptInterface
        fun openNotificationSettings() {
            runOnUiThread { apriImpostazioniNotifiche() }
        }
    }

    private fun schermoIntero(on: Boolean, landscape: Boolean) {
        val barre = WindowCompat.getInsetsController(window, window.decorView)
        if (on) {
            barre.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            barre.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            barre.show(WindowInsetsCompat.Type.systemBars())
        }
        requestedOrientation = if (on && landscape) ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
    }

    private fun apriImpostazioniNotifiche() {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Apri Impostazioni > App > KlippEye > Notifiche", Toast.LENGTH_LONG).show()
        }
    }

    // ---- Aggiornamento dell'app ----

    /** Dice alla pagina a che punto siamo (se la dashboard e' una di quelle che ascolta). */
    private fun dicoAllaPagina(stato: String, vararg dettagli: Pair<String, Any>) {
        val messaggio = JSONObject().put("stato", stato)
        for ((chiave, valore) in dettagli) messaggio.put(chiave, valore)
        webView.evaluateJavascript("window.klippeyeAppUpdate && window.klippeyeAppUpdate($messaggio)", null)
    }

    private fun aggiornaApp(percorso: String?, versione: String?, sha256: String?, grandezza: Long) {
        if (aggiornamento?.isActive == true) return // gia' in corso: la pagina riceve gia' l'avanzamento
        val richiesta = try {
            Aggiornamento.controllaRichiesta(URL(currentUrl), percorso, versione, sha256, grandezza, AggiornamentoAndroid.installata(this).second)
        } catch (e: Exception) {
            dicoAllaPagina("errore", "messaggio" to (e.message ?: "richiesta non valida"))
            return
        }
        if (!AggiornamentoAndroid.puoInstallare(this)) {
            // Android 8+: prima va concesso a KlippEye il permesso "Installa app sconosciute"; al ritorno (onResume) si riprende da qui
            inAttesaDelPermesso = richiesta
            dicoAllaPagina("permesso")
            try {
                startActivity(AggiornamentoAndroid.intentPermesso(this))
            } catch (e: Exception) {
                inAttesaDelPermesso = null
                dicoAllaPagina("errore", "messaggio" to "Apri Impostazioni > App > KlippEye > Installa app sconosciute e consenti, poi riprova")
            }
            return
        }
        scaricaEInstalla(richiesta)
    }

    private fun scaricaEInstalla(richiesta: Aggiornamento.Richiesta) {
        dicoAllaPagina("scarico", "fatto" to 0L, "totale" to richiesta.grandezza)
        aggiornamento = scope.launch {
            var ultimoPercento = -1L
            val esito = withContext(Dispatchers.IO) {
                runCatching {
                    Aggiornamento.scarica(richiesta, AggiornamentoAndroid.cartella(this@MainActivity)) { scaricati ->
                        // alla pagina basta un messaggio per ogni punto percentuale
                        val percento = scaricati * 100 / richiesta.grandezza
                        if (percento != ultimoPercento) {
                            ultimoPercento = percento
                            runOnUiThread { dicoAllaPagina("scarico", "fatto" to scaricati, "totale" to richiesta.grandezza) }
                        }
                    }
                }
            }
            esito.onSuccess { file ->
                try {
                    startActivity(AggiornamentoAndroid.intentInstallazione(this@MainActivity, file))
                    dicoAllaPagina("installazione")
                } catch (e: Exception) {
                    dicoAllaPagina("errore", "messaggio" to "Non riesco ad aprire l'installazione di Android: ${e.message ?: e.javaClass.simpleName}")
                }
            }.onFailure { errore ->
                dicoAllaPagina("errore", "messaggio" to (errore.message ?: errore.javaClass.simpleName))
            }
        }
    }

    override fun onPause() {
        super.onPause()
        // Il cookie di accesso resta salvato anche se Android chiude l'app subito dopo: niente password da rifare
        CookieManager.getInstance().flush()
    }

    override fun onResume() {
        super.onResume()
        // Tornati dalle impostazioni di Android (permesso, batteria): la procedura guidata vede subito com'e' andata
        dicoStatoNotifiche()
        // Tornati dalla pagina dei permessi di Android: se ora KlippEye puo' installare, l'aggiornamento riparte da solo
        val richiesta = inAttesaDelPermesso ?: return
        inAttesaDelPermesso = null
        if (AggiornamentoAndroid.puoInstallare(this)) {
            scaricaEInstalla(richiesta)
        } else {
            dicoAllaPagina("errore", "messaggio" to "Senza il permesso Android non lascia installare l'aggiornamento: attiva «Consenti da questa fonte» per KlippEye e riprova")
        }
    }

    /** Scarica `rawUrl` (relativo alla dashboard o completo) e lo salva in Download come `requestedName`. */
    private fun downloadFile(rawUrl: String?, requestedName: String?) {
        val base = URL(currentUrl)
        val target = try {
            URL(base, rawUrl ?: "")
        } catch (e: Exception) {
            null
        }
        // Solo file del Raspberry a cui l'app è collegata (http/https, stesso indirizzo): niente blob:, data: o altri siti
        if (target == null || (target.protocol != "http" && target.protocol != "https") || target.host != base.host) {
            Toast.makeText(this, "Download non supportato per questo indirizzo", Toast.LENGTH_LONG).show()
            return
        }
        val fileName = cleanFileName(if (requestedName.isNullOrBlank()) target.path.substringAfterLast('/') else requestedName)
        Toast.makeText(this, "Scarico $fileName...", Toast.LENGTH_SHORT).show()
        scope.launch {
            val outcome = withContext(Dispatchers.IO) { runCatching { saveToDownloads(target, fileName) } }
            outcome.onSuccess { savedAs ->
                Toast.makeText(this@MainActivity, "Salvato in $savedAs", Toast.LENGTH_LONG).show()
            }.onFailure { error ->
                Toast.makeText(this@MainActivity, "Download non riuscito: ${error.message ?: error.javaClass.simpleName}", Toast.LENGTH_LONG).show()
            }
        }
    }

    /** Il nome senza separatori di percorso né caratteri che il telefono non accetta in un nome di file. */
    private fun cleanFileName(raw: String): String {
        val name = raw.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), "_").trim().take(120)
        return if (name.isEmpty() || name.all { it == '.' }) "download" else name
    }

    private fun saveToDownloads(url: URL, fileName: String): String {
        val connection = url.openConnection() as HttpURLConnection
        connection.connectTimeout = 5000
        connection.readTimeout = 30000
        // Con la password attiva (KlippEye 1.2.0) il Raspberry vuole il gettone di accesso: e' il cookie della WebView
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
     * Android 10+: nella cartella Download pubblica tramite MediaStore (nessun permesso); un nome già preso
     * diventa "nome (1).ext". Prima di Android 10 la cartella pubblica chiederebbe un permesso: il file va
     * nella cartella Download dell'app (Android/data/com.klippeye.app/files/Download).
     * Restituisce dove è stato salvato, per dirlo all'utente.
     */
    private fun writeToDownloads(fileName: String, input: InputStream): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val extension = fileName.substringAfterLast('.', "").lowercase()
            // Un tipo che non corrisponde all'estensione farebbe aggiungere un'altra estensione (.cfg diventerebbe .cfg.txt)
            val mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) ?: "application/octet-stream"
            val resolver = contentResolver
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: throw IOException("cartella Download non disponibile")
            try {
                val output = resolver.openOutputStream(uri) ?: throw IOException("impossibile scrivere il file")
                output.use { input.copyTo(it) }
                resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
            } catch (e: Exception) {
                resolver.delete(uri, null, null) // niente file a metà
                throw e
            }
            val savedName = resolver.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
            return "Download/" + (savedName ?: fileName)
        }

        val folder = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: throw IOException("memoria non disponibile")
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
     * Il tasto indietro del telefono va prima alla dashboard: chiude la guida o il dialogo aperto, torna alla pagina precedente
     * del menu o al passo precedente della configurazione guidata (window.klippeyeBack). Solo se la pagina non ha niente da
     * chiudere fa quello di sempre (pagina precedente del WebView, poi esce).
     */
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.visibility != View.VISIBLE) {
            tornaIndietroDavvero()
            return
        }
        webView.evaluateJavascript("(function(){ try { return window.klippeyeBack && window.klippeyeBack() ? '1' : '' } catch (e) { return '' } })()") { risposta ->
            if (risposta?.contains("1") != true) tornaIndietroDavvero()
        }
    }

    @Suppress("DEPRECATION")
    private fun tornaIndietroDavvero() {
        if (webView.canGoBack()) {
            webView.goBack()
            return
        }
        super.onBackPressed()
    }

    private companion object {
        /** Gli APK scaricati per l'aggiornamento si buttano all'avvio dell'app se hanno piu' di 10 minuti */
        const val PULIZIA_APK_DOPO_MS = 10 * 60 * 1000L
    }

    override fun onDestroy() {
        super.onDestroy()
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        scope.cancel()
    }
}
