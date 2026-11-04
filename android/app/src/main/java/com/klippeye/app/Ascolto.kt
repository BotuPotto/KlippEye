package com.klippeye.app

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Dove arrivano le notifiche su QUESTO telefono (app 1.3.0, fase 5d di KlippEye).
 *
 * La dashboard, aperta nell'app, legge dal Raspberry come sono impostate le notifiche (/api/notifications/app) e le passa
 * qui con il ponte KlippEyeApp.notifySetup(). Poi:
 *   · Firebase  se il Raspberry ha la chiave Firebase (solo l'installazione di chi mantiene il progetto) l'app si iscrive
 *               all'argomento che il Raspberry le dice. Nessun argomento e' piu' scritto dentro l'app;
 *   · ntfy      altrimenti l'app ascolta da sola l'argomento privato ntfy ([AscoltoNtfy], un servizio in primo piano con una
 *               piccola notifica fissa), senza bisogno dell'app ntfy.
 * Le notifiche arrivano su questo telefono solo se la persona lo ha scelto (procedura guidata nella dashboard).
 *
 * App 1.6.0 (piu' stampanti, vedi [Stampanti]): ogni stampante aperta nell'app dice il suo argomento ntfy; l'app li ascolta
 * tutti (un collegamento per server, con gli argomenti separati da virgole), cosi' le notifiche arrivano da ogni stampante,
 * non solo da quella sullo schermo. La principale resta nelle chiavi di sempre, le altre in "altre" (JSON per stampante).
 */
object Ascolto {
    private const val PREFERENZE = "klippeye_notifiche"
    // L'argomento Firebase scritto dentro le app fino alla 1.2.0 (era pubblico nel repository): l'app se ne cancella sempre.
    const val ARGOMENTO_VECCHIO = "vzbot-pp3zt27qxb49fw3fsbvv"

    data class Impostazioni(
        val ricevi: Boolean,          // la persona ha scelto di ricevere le notifiche su questo telefono
        val scelto: Boolean,          // ...e lo ha scelto (false: non ancora deciso)
        val server: String,
        val argomento: String,
        val token: String,
        val argomentoFirebase: String,
    ) {
        /** Il modo in cui arrivano ora: "firebase", "ntfy" oppure "" (nessuno). Firebase vince: niente notifica fissa. */
        // Firebase vale anche prima della scelta (chi lo usava con l'app 1.2.0 continua a ricevere senza fare nulla), finche' la
        // persona non dice "non su questo telefono"; ntfy solo dopo la scelta (accende un servizio con una notifica fissa).
        fun modo(firebasePronto: Boolean): String = when {
            argomentoFirebase.isNotEmpty() && firebasePronto && (ricevi || !scelto) -> "firebase"
            ricevi && argomento.isNotEmpty() && server.isNotEmpty() -> "ntfy"
            else -> ""
        }
    }

    private fun preferenze(context: Context) = context.getSharedPreferences(PREFERENZE, Context.MODE_PRIVATE)

    fun leggi(context: Context): Impostazioni {
        val p = preferenze(context)
        return Impostazioni(
            p.getBoolean("ricevi", false), p.contains("ricevi"), p.getString("server", "") ?: "", p.getString("argomento", "") ?: "",
            p.getString("token", "") ?: "", p.getString("firebase", "") ?: "",
        )
    }

    private val ARGOMENTO = Regex("^[-_A-Za-z0-9]{1,64}$")
    private val SERVER = Regex("^https?://[A-Za-z0-9.\\-]+(:\\d{1,5})?(/[A-Za-z0-9._~\\-/]*)?$")

    /**
     * Salva cio' che la dashboard manda: {"ricevi": true|false (facoltativo), "ntfy": {"server","topic","token"} | null,
     * "firebaseTopic": "..." | ""}. I valori non validi sono scartati. Poi avvia o ferma l'ascolto e l'iscrizione Firebase.
     */
    fun imposta(context: Context, json: String?, stampante: String = "") {
        val dati = try {
            JSONObject(json ?: "{}")
        } catch (e: Exception) {
            return
        }
        val modifica = preferenze(context).edit()
        if (dati.has("ricevi")) modifica.putBoolean("ricevi", dati.optBoolean("ricevi", false))
        if (stampante.isNotEmpty()) {
            // un'altra stampante: il suo argomento ntfy accanto a quello della principale (Firebase resta della principale)
            if (dati.has("ntfy")) {
                val altre = altre(context)
                val ntfy = dati.optJSONObject("ntfy")
                val server = ntfy?.optString("server", "")?.trimEnd('/') ?: ""
                val argomento = ntfy?.optString("topic", "") ?: ""
                if (ntfy != null && SERVER.matches(server) && ARGOMENTO.matches(argomento)) {
                    altre.put(stampante, JSONObject().put("server", server).put("argomento", argomento).put("token", ntfy.optString("token", "")))
                } else {
                    altre.remove(stampante)
                }
                modifica.putString("altre", altre.toString())
            }
            modifica.apply()
            applica(context)
            return
        }
        if (dati.has("ntfy")) {
            val ntfy = dati.optJSONObject("ntfy")
            val server = ntfy?.optString("server", "")?.trimEnd('/') ?: ""
            val argomento = ntfy?.optString("topic", "") ?: ""
            val valido = ntfy != null && SERVER.matches(server) && ARGOMENTO.matches(argomento)
            modifica.putString("server", if (valido) server else "")
            modifica.putString("argomento", if (valido) argomento else "")
            modifica.putString("token", if (valido) ntfy?.optString("token", "") ?: "" else "")
        }
        if (dati.has("firebaseTopic")) {
            val argomento = dati.optString("firebaseTopic", "")
            modifica.putString("firebase", if (ARGOMENTO.matches(argomento)) argomento else "")
        }
        modifica.apply()
        applica(context)
    }

    private fun altre(context: Context): JSONObject = try {
        JSONObject(preferenze(context).getString("altre", "{}") ?: "{}")
    } catch (e: Exception) {
        JSONObject()
    }

    /** Un argomento da ascoltare: server, argomento, token. */
    data class Argomento(val server: String, val argomento: String, val token: String)

    /** Tutti gli argomenti ntfy da ascoltare: quello della principale e quelli delle altre stampanti aperte nell'app. */
    fun argomenti(context: Context): List<Argomento> {
        val lista = ArrayList<Argomento>()
        val principale = leggi(context)
        if (principale.argomento.isNotEmpty() && principale.server.isNotEmpty()) lista.add(Argomento(principale.server, principale.argomento, principale.token))
        val altre = altre(context)
        for (chiave in altre.keys()) {
            val una = altre.optJSONObject(chiave) ?: continue
            val server = una.optString("server", "")
            val argomento = una.optString("argomento", "")
            if (SERVER.matches(server) && ARGOMENTO.matches(argomento) && lista.none { it.server == server && it.argomento == argomento }) {
                lista.add(Argomento(server, argomento, una.optString("token", "")))
            }
        }
        return lista
    }

    /** Gli argomenti per server: un collegamento per server, "argA,argB" (ntfy li ascolta insieme), il primo token trovato. */
    fun gruppi(context: Context): Map<String, Pair<String, String>> =
        argomenti(context).groupBy { it.server }.mapValues { (_, lista) -> Pair(lista.joinToString(",") { it.argomento }, lista.firstOrNull { it.token.isNotEmpty() }?.token ?: "") }

    /** Il modo di questo telefono: Firebase come prima; ntfy se la persona ha scelto di ricevere e c'e' almeno un argomento. */
    fun modo(context: Context): String {
        val impostazioni = leggi(context)
        val firebase = impostazioni.modo(Notifiche.firebasePronto(context))
        if (firebase == "firebase") return firebase
        return if (impostazioni.ricevi && argomenti(context).isNotEmpty()) "ntfy" else ""
    }

    /** Fa corrispondere il telefono alle impostazioni: servizio ntfy acceso o spento, iscrizione Firebase giusta. */
    fun applica(context: Context) {
        val impostazioni = leggi(context)
        val modo = modo(context)
        Notifiche.iscriviFirebase(context, if (modo == "firebase") impostazioni.argomentoFirebase else "")
        val servizio = Intent(context, AscoltoNtfy::class.java)
        if (modo == "ntfy") {
            try {
                ContextCompat.startForegroundService(context, servizio)
            } catch (e: Exception) {
                Log.w("KlippEyeAscolto", "Non riesco ad avviare l'ascolto", e)
            }
        } else {
            context.stopService(servizio)
            segnaCollegato(context, false)
        }
    }

    // ---- quello che la procedura guidata della dashboard mostra ----

    fun segnaCollegato(context: Context, collegato: Boolean) {
        preferenze(context).edit().putBoolean("collegato", collegato).putLong("collegato_alle", System.currentTimeMillis()).apply()
    }

    fun segnaRicevuta(context: Context, titolo: String, idNtfy: String? = null) {
        val modifica = preferenze(context).edit().putLong("ultima_alle", System.currentTimeMillis()).putString("ultima_titolo", titolo)
        if (!idNtfy.isNullOrEmpty()) modifica.putString("ultimo_id", idNtfy)
        modifica.apply()
    }

    fun ultimoId(context: Context): String = preferenze(context).getString("ultimo_id", "") ?: ""

    /** Quando e' arrivata l'ultima notifica (ms), per riprendere da li' dopo un'interruzione con piu' argomenti. */
    fun ultimaAlle(context: Context): Long = preferenze(context).getLong("ultima_alle", 0L)

    fun batteriaLibera(context: Context): Boolean {
        val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return true
        return power.isIgnoringBatteryOptimizations(context.packageName)
    }

    /** Lo stato per la dashboard (KlippEyeApp.notifyState()). */
    fun stato(context: Context, stampante: String = ""): String {
        val impostazioni = leggi(context)
        val p = preferenze(context)
        val argomento = if (stampante.isEmpty()) impostazioni.argomento else altre(context).optJSONObject(stampante)?.optString("argomento", "") ?: ""
        return JSONObject()
            .put("permission", Notifiche.permessoConcesso(context))
            .put("askPermission", Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            .put("battery", batteriaLibera(context))
            .put("receive", impostazioni.ricevi)
            .put("chosen", impostazioni.scelto)
            .put("mode", modo(context))
            .put("firebaseBuilt", Notifiche.firebasePronto(context))
            .put("ntfyTopic", argomento)
            .put("connected", p.getBoolean("collegato", false))
            .put("lastMessageAt", p.getLong("ultima_alle", 0L))
            .put("lastTitle", p.getString("ultima_titolo", "") ?: "")
            .toString()
    }
}

/**
 * Ascolta l'argomento ntfy del Raspberry (https://docs.ntfy.sh/subscribe/api/: GET <server>/<argomento>/json, una riga JSON per
 * evento) e mostra le notifiche. Resta acceso in primo piano (Android lo chiede per un collegamento sempre aperto), con una
 * notifica fissa e discreta; si ricollega da solo quando la rete torna, e con `since` recupera i messaggi persi nel frattempo.
 */
class AscoltoNtfy : Service() {
    // Un filo per server ntfy (di solito uno: ntfy.sh). Ogni avvio del servizio (impostazioni cambiate) apre una nuova
    // "generazione": i fili di quella prima chiudono il loro collegamento ed escono, i nuovi ascoltano gli argomenti di adesso.
    @Volatile private var generazione = 0
    private val fili = ConcurrentHashMap<String, Thread>()
    private val collegamenti = ConcurrentHashMap<String, HttpURLConnection>()
    private val visti = java.util.Collections.synchronizedSet(LinkedHashSet<String>())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Notifiche.creaCanali(this)
        val tipo = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, ID_NOTIFICA_FISSA, notificaFissa(), tipo)
        val gruppi = Ascolto.gruppi(this)
        if (gruppi.isEmpty()) {
            stopSelf()
            return START_NOT_STICKY
        }
        val mia = ++generazione
        collegamenti.values.forEach { try { it.disconnect() } catch (e: Exception) {} }
        fili.values.forEach { it.interrupt() }
        fili.clear()
        for (server in gruppi.keys) {
            fili[server] = Thread({ ascolta(server, mia) }, "ascolto-ntfy").apply { isDaemon = true; start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        generazione++
        collegamenti.values.forEach { try { it.disconnect() } catch (e: Exception) {} }
        fili.values.forEach { it.interrupt() }
        Ascolto.segnaCollegato(this, false)
        super.onDestroy()
    }

    private fun notificaFissa(): Notification {
        val apri = PendingIntent.getActivity(
            this, 1, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, Notifiche.CANALE_ASCOLTO)
            .setSmallIcon(R.drawable.ic_stat_klippeye)
            .setContentTitle("KlippEye in ascolto")
            .setContentText("Riceve le notifiche delle stampanti. Tieni premuto per nasconderla.")
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setOngoing(true)
            .setShowWhen(false)
            .setContentIntent(apri)
            .build()
    }

    private fun ascolta(server: String, mia: Int) {
        var attesa = 5_000L
        while (generazione == mia) {
            val gruppo = Ascolto.gruppi(this)[server] ?: break
            try {
                collegati(server, gruppo.first, gruppo.second, mia)
                attesa = 5_000L // si era collegato: la prossima volta si riprova subito
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                Log.w(TAG, "Collegamento a ntfy interrotto: ${e.message}")
            }
            Ascolto.segnaCollegato(this, false)
            if (generazione != mia) break
            try {
                Thread.sleep(attesa)
            } catch (e: InterruptedException) {
                break
            }
            attesa = minOf(attesa * 2, 60_000L)
        }
        fili.remove(server, Thread.currentThread())
        if (generazione == mia && fili.isEmpty()) stopSelf()
    }

    private fun collegati(server: String, argomenti: String, token: String, mia: Int) {
        // Con un solo argomento si riprende dall'ultimo messaggio (il suo id); con piu' argomenti dall'ora dell'ultimo
        val since = if (!argomenti.contains(',')) Ascolto.ultimoId(this) else Ascolto.ultimaAlle(this).let { if (it > 0) (it / 1000).toString() else "" }
        val indirizzo = server.trimEnd('/') + "/" + argomenti + "/json" + (if (since.isNotEmpty()) "?since=" + URLEncoder.encode(since, "UTF-8") else "")
        val connessione = URL(indirizzo).openConnection() as HttpURLConnection
        collegamenti[server] = connessione
        connessione.connectTimeout = 15_000
        connessione.readTimeout = 100_000 // ntfy manda un "keepalive" ogni 45 secondi: senza nulla per 100 s la linea e' morta
        connessione.setRequestProperty("User-Agent", "KlippEyeApp")
        if (token.isNotEmpty()) connessione.setRequestProperty("Authorization", "Bearer " + token)
        try {
            if (connessione.responseCode !in 200..299) throw java.io.IOException("ntfy ha risposto ${connessione.responseCode}")
            BufferedReader(InputStreamReader(connessione.inputStream, Charsets.UTF_8)).use { lettore ->
                while (generazione == mia) {
                    val riga = lettore.readLine() ?: break
                    gestisci(riga)
                }
            }
        } finally {
            collegamenti.remove(server, connessione)
            connessione.disconnect()
        }
    }

    private fun gestisci(riga: String) {
        val evento = try {
            JSONObject(riga)
        } catch (e: Exception) {
            return
        }
        when (evento.optString("event")) {
            "open", "keepalive" -> Ascolto.segnaCollegato(this, true)
            "message" -> {
                val id = evento.optString("id", "")
                if (id.isNotEmpty()) {
                    // ripresa dall'ora dell'ultimo messaggio: quello stesso puo' tornare una volta
                    if (!visti.add(id)) return
                    if (visti.size > 200) visti.remove(visti.first())
                }
                val titolo = evento.optString("title", "").ifEmpty { "KlippEye" }
                val testo = evento.optString("message", "")
                Notifiche.mostra(this, Notifiche.tipoDaPriorita(evento.optInt("priority", 3)), titolo, testo, id)
                Ascolto.segnaRicevuta(this, titolo + ": " + testo, id)
            }
        }
    }

    private companion object {
        const val TAG = "KlippEyeAscolto"
        const val ID_NOTIFICA_FISSA = 7001
    }
}

/** All'accensione del telefono e dopo un aggiornamento dell'app l'ascolto riparte da solo (se era scelto). */
class RiavvioAscolto : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val azione = intent?.action ?: return
        if (azione == Intent.ACTION_BOOT_COMPLETED || azione == Intent.ACTION_MY_PACKAGE_REPLACED) {
            Ascolto.applica(context)
        }
    }
}
