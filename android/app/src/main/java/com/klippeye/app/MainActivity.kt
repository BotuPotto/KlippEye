package com.klippeye.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
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

    private var currentUrl = "http://${Indirizzi.LOCALE_DI_FABBRICA}:${Indirizzi.PORTA}/"
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

    // Android 13+: il permesso per le notifiche va chiesto all'utente (compare una finestra di sistema)
    private val permessoNotifiche = registerForActivityResult(ActivityResultContracts.RequestPermission()) { concesso ->
        val preferenze = getSharedPreferences("klippeye", MODE_PRIVATE)
        if (!concesso && !preferenze.getBoolean("avviso_permesso_mostrato", false)) {
            preferenze.edit().putBoolean("avviso_permesso_mostrato", true).apply()
            Toast.makeText(this, "Senza il permesso le notifiche non compaiono. Attivalo da Impostazioni > App > KlippEye > Notifiche.", Toast.LENGTH_LONG).show()
        }
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
        // 5 = anche aggiornarsi da sola (appInfo/updateApp). Con un numero più basso la dashboard lascia disattivata la funzione.
        webView.settings.userAgentString = webView.settings.userAgentString + " KlippEyeApp/5"

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

        detectAndLoad()
        avviaNotifiche()
        // Gli APK scaricati per un aggiornamento precedente non servono piu' (quelli appena scaricati restano qualche minuto)
        val cartellaAggiornamenti = AggiornamentoAndroid.cartella(this)
        Thread { Aggiornamento.pulisci(cartellaAggiornamenti, PULIZIA_APK_DOPO_MS) }.start()
    }

    /** Notifiche push: canali, permesso (Android 13+) e iscrizione all'argomento privato. Vedi Notifiche.kt. */
    private fun avviaNotifiche() {
        Notifiche.creaCanali(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            permessoNotifiche.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        val configurato = Notifiche.iscrivi(this) { riuscito ->
            val preferenze = getSharedPreferences("klippeye", MODE_PRIVATE)
            if (riuscito && !preferenze.getBoolean("notifiche_attivate_mostrato", false)) {
                preferenze.edit().putBoolean("notifiche_attivate_mostrato", true).apply()
                Toast.makeText(this, "Notifiche attivate", Toast.LENGTH_SHORT).show()
            }
        }
        if (!configurato) {
            Toast.makeText(this, "Notifiche non attive: nell'app manca google-services.json (vedi la guida)", Toast.LENGTH_LONG).show()
        }
    }

    private fun hostOf(url: String?): String? = try {
        Uri.parse(url ?: "").host
    } catch (e: Exception) {
        null
    }

    /** Cerca il Raspberry tra gli indirizzi (il primo che risponde vince) e carica la dashboard. */
    private fun detectAndLoad() {
        splash.visibility = View.VISIBLE
        webView.visibility = View.INVISIBLE
        progress.visibility = View.VISIBLE
        failureActions.visibility = View.GONE
        statusText.setTextColor(getColor(R.color.vz_text2))
        statusText.text = "Cerco KlippEye in rete locale..."
        errorHost = null

        candidates = Indirizzi.candidati(Indirizzi.leggi(this))
        scope.launch {
            var found = -1
            for ((index, candidate) in candidates.withIndex()) {
                if (index > 0) statusText.text = "Non risponde, provo ${candidate.etichetta} ${candidate.host}..."
                if (withContext(Dispatchers.IO) { isReachable(candidate.url) }) {
                    found = index
                    break
                }
            }
            if (found >= 0) {
                cascade = true
                val candidate = candidates[found]
                connectTo(found, if (found == 0) "Connesso a ${candidate.host}" else "Connesso via ${candidate.etichetta} ${candidate.host}")
            } else {
                // Nessuno risponde: si prova comunque il primo, come prima, ma senza girare gli altri uno a uno
                cascade = false
                connectTo(0, "Provo comunque ${candidates[0].host}...")
            }
        }
    }

    private fun isReachable(baseUrl: String): Boolean {
        return try {
            val url = URL(baseUrl)
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 1200
            conn.readTimeout = 1200
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
        val next = candidateIndex + 1
        if (cascade && next < candidates.size) {
            connectTo(next, "${candidates[candidateIndex].host} non risponde, passo a ${candidates[next].etichetta}...")
        } else {
            // Nessun altro indirizzo da provare: lo spinner si ferma, il messaggio diventa d'errore e si puo' riprovare o cambiare gli indirizzi.
            progress.visibility = View.GONE
            statusText.setTextColor(getColor(R.color.vz_danger))
            statusText.text = "Impossibile connettersi. Controlla Pi e ZeroTier, oppure gli indirizzi."
            failureActions.visibility = View.VISIBLE
        }
    }

    // ---- Indirizzi del Raspberry ----

    /**
     * La finestra "Indirizzi", per quando il Raspberry ha cambiato indirizzo e l'app non lo trova piu'.
     * Gli indirizzi nuovi valgono per l'app subito e, appena la dashboard e' caricata, anche per il suo menu Impostazioni
     * (un'unica coppia di indirizzi, che la camera della dashboard usa a sua volta).
     */
    private fun showAddressesDialog(localText: String? = null, externalText: String? = null) {
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
        val localField = field("IP locale (rete di casa)", localText ?: current.locale)
        val externalField = field("IP esterno (ZeroTier)", externalText ?: current.esterno)
        box.addView(localField)
        box.addView(externalField)
        AlertDialog.Builder(this)
            .setTitle("Indirizzi del Raspberry")
            .setMessage("Solo l'indirizzo, senza http:// e senza porta.")
            .setView(box)
            .setPositiveButton("Salva e riprova") { _, _ ->
                val local = localField.text.toString()
                val external = externalField.text.toString()
                val outcome = Indirizzi.salva(this, local, external)
                if (outcome == "ok") {
                    addressesForPage = Indirizzi.leggi(this)
                    detectAndLoad()
                } else {
                    Toast.makeText(this, outcome, Toast.LENGTH_LONG).show()
                    showAddressesDialog(local, external) // si riapre con quello che era stato scritto
                }
            }
            .setNeutralButton("Valori di fabbrica") { _, _ ->
                Indirizzi.salva(this, Indirizzi.LOCALE_DI_FABBRICA, Indirizzi.ESTERNO_DI_FABBRICA)
                addressesForPage = Indirizzi.DI_FABBRICA
                detectAndLoad()
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
        fun setAddresses(local: String?, external: String?): String = Indirizzi.salva(applicationContext, local, external)

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

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
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
