package com.klippeye.app

import android.app.Notification
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
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * How the notifications reach THIS phone (app 1.3.0).
 *
 * The dashboard, opened in the app, reads from the Raspberry how the notifications are set up (/api/notifications/app) and
 * passes it here with the bridge call KlippEyeApp.notifySetup(). Then:
 *   · Firebase  when the Raspberry has the Firebase key (only the installation of whoever maintains the project) the app
 *               subscribes to the topic the Raspberry gives it. No topic is written inside the app any more;
 *   · ntfy      otherwise the app listens to the private ntfy topic by itself ([NtfyListenerService], a foreground service
 *               with a small ongoing notification), without the ntfy app.
 * Notifications reach this phone only when the person chose so (the guided set-up in the dashboard).
 *
 * App 1.6.0 (more printers, see [Printers]): each printer opened in the app gives its ntfy topic; the app listens to all of
 * them (one connection per server, the topics separated by commas), so the notifications come from every printer, not only
 * the one on the screen. The main printer stays in the usual keys, the others in "altre" (JSON per printer).
 */
object PushSettings {
    // The Firebase topic written inside the apps up to 1.2.0 (it was public in the repository): the app always leaves it.
    const val OLD_TOPIC = "vzbot-pp3zt27qxb49fw3fsbvv"

    // What the dashboard sends: {"ricevi": true|false (optional), "ntfy": {"server","topic","token"} | null, "firebaseTopic": "..." | ""}.
    // "ricevi" ("receive") is a name of the bridge, shared with every dashboard version: it stays.
    private const val FIELD_RECEIVE = "ricevi"

    // The stored names, kept from the first versions so that an update keeps the choice of this phone
    private const val PREFERENCES = "klippeye_notifiche"
    private const val KEY_RECEIVE = "ricevi"
    private const val KEY_SERVER = "server"
    private const val KEY_TOPIC = "argomento"
    private const val KEY_TOKEN = "token"
    private const val KEY_FIREBASE = "firebase"
    private const val KEY_OTHERS = "altre"
    private const val KEY_CONNECTED = "collegato"
    private const val KEY_CONNECTED_AT = "collegato_alle"
    private const val KEY_LAST_AT = "ultima_alle"
    private const val KEY_LAST_TITLE = "ultima_titolo"
    private const val KEY_LAST_ID = "ultimo_id"

    const val MODE_FIREBASE = "firebase"
    const val MODE_NTFY = "ntfy"

    data class Settings(
        val receive: Boolean, // the person chose to receive the notifications on this phone
        val chosen: Boolean, // ...and made the choice (false: not decided yet)
        val server: String,
        val topic: String,
        val token: String,
        val firebaseTopic: String,
    ) {
        /**
         * How they arrive now: "firebase", "ntfy" or "" (none). Firebase wins (no ongoing notification). Firebase applies even
         * before the choice (whoever used it with app 1.2.0 keeps receiving without doing anything) until the person says
         * "not on this phone"; ntfy only after the choice (it starts a service with an ongoing notification).
         */
        fun mode(firebaseReady: Boolean): String = when {
            firebaseTopic.isNotEmpty() && firebaseReady && (receive || !chosen) -> MODE_FIREBASE
            receive && topic.isNotEmpty() && server.isNotEmpty() -> MODE_NTFY
            else -> ""
        }
    }

    /** One ntfy topic to listen to. */
    data class Topic(val server: String, val topic: String, val token: String)

    private val TOPIC_FORMAT = Regex("^[-_A-Za-z0-9]{1,64}$")
    private val SERVER_FORMAT = Regex("^https?://[A-Za-z0-9.\\-]+(:\\d{1,5})?(/[A-Za-z0-9._~\\-/]*)?$")

    private fun preferences(context: Context) = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun read(context: Context): Settings {
        val p = preferences(context)
        return Settings(
            p.getBoolean(KEY_RECEIVE, false), p.contains(KEY_RECEIVE), p.getString(KEY_SERVER, "") ?: "", p.getString(KEY_TOPIC, "") ?: "",
            p.getString(KEY_TOKEN, "") ?: "", p.getString(KEY_FIREBASE, "") ?: "",
        )
    }

    /** The "ntfy" part of what the dashboard sent, when it is valid: (server, topic, token). */
    private fun ntfyOf(data: JSONObject): Topic? {
        val ntfy = data.optJSONObject("ntfy") ?: return null
        val server = ntfy.optString("server", "").trimEnd('/')
        val topic = ntfy.optString("topic", "")
        return if (SERVER_FORMAT.matches(server) && TOPIC_FORMAT.matches(topic)) Topic(server, topic, ntfy.optString("token", "")) else null
    }

    /**
     * Stores what the dashboard of `printer` sends ("" = the main printer); values that are not valid are dropped. Then starts
     * or stops listening and the Firebase subscription.
     */
    fun update(context: Context, json: String?, printer: String = "") {
        val data = try {
            JSONObject(json ?: "{}")
        } catch (e: Exception) {
            return
        }
        val editor = preferences(context).edit()
        if (data.has(FIELD_RECEIVE)) editor.putBoolean(KEY_RECEIVE, data.optBoolean(FIELD_RECEIVE, false))
        if (printer.isNotEmpty()) {
            // another printer: its ntfy topic next to the main printer's (Firebase stays the main printer's)
            if (data.has("ntfy")) {
                val others = others(context)
                val ntfy = ntfyOf(data)
                if (ntfy != null) {
                    others.put(printer, JSONObject().put(KEY_SERVER, ntfy.server).put(KEY_TOPIC, ntfy.topic).put(KEY_TOKEN, ntfy.token))
                } else {
                    others.remove(printer)
                }
                editor.putString(KEY_OTHERS, others.toString())
            }
        } else {
            if (data.has("ntfy")) {
                val ntfy = ntfyOf(data)
                editor.putString(KEY_SERVER, ntfy?.server ?: "")
                editor.putString(KEY_TOPIC, ntfy?.topic ?: "")
                editor.putString(KEY_TOKEN, ntfy?.token ?: "")
            }
            if (data.has("firebaseTopic")) {
                val topic = data.optString("firebaseTopic", "")
                editor.putString(KEY_FIREBASE, if (TOPIC_FORMAT.matches(topic)) topic else "")
            }
        }
        editor.apply()
        apply(context)
    }

    private fun others(context: Context): JSONObject = try {
        JSONObject(preferences(context).getString(KEY_OTHERS, "{}") ?: "{}")
    } catch (e: Exception) {
        JSONObject()
    }

    /** Every ntfy topic to listen to: the main printer's and those of the other printers opened in the app. */
    fun topics(context: Context): List<Topic> {
        val list = ArrayList<Topic>()
        val main = read(context)
        if (main.topic.isNotEmpty() && main.server.isNotEmpty()) list.add(Topic(main.server, main.topic, main.token))
        val others = others(context)
        for (key in others.keys()) {
            val one = others.optJSONObject(key) ?: continue
            val server = one.optString(KEY_SERVER, "")
            val topic = one.optString(KEY_TOPIC, "")
            if (SERVER_FORMAT.matches(server) && TOPIC_FORMAT.matches(topic) && list.none { it.server == server && it.topic == topic }) {
                list.add(Topic(server, topic, one.optString(KEY_TOKEN, "")))
            }
        }
        return list
    }

    /** The topics per server: one connection per server, "topicA,topicB" (ntfy listens to them together), the first token found. */
    fun byServer(context: Context): Map<String, Pair<String, String>> =
        topics(context).groupBy { it.server }.mapValues { (_, list) ->
            Pair(list.joinToString(",") { it.topic }, list.firstOrNull { it.token.isNotEmpty() }?.token ?: "")
        }

    /** How this phone receives: Firebase as before; ntfy when the person chose to receive and there is at least one topic. */
    fun mode(context: Context): String {
        val settings = read(context)
        if (settings.mode(Notifications.firebaseReady(context)) == MODE_FIREBASE) return MODE_FIREBASE
        return if (settings.receive && topics(context).isNotEmpty()) MODE_NTFY else ""
    }

    /** Makes the phone match the settings: the ntfy service on or off, the right Firebase subscription. */
    fun apply(context: Context) {
        val settings = read(context)
        val mode = mode(context)
        Notifications.subscribeFirebase(context, if (mode == MODE_FIREBASE) settings.firebaseTopic else "")
        val service = Intent(context, NtfyListenerService::class.java)
        if (mode == MODE_NTFY) {
            try {
                ContextCompat.startForegroundService(context, service)
            } catch (e: Exception) {
                // Android 12+ refuses to start a foreground service from the background in some cases: it starts with the app
                Log.w(TAG, "Cannot start listening", e)
            }
        } else {
            context.stopService(service)
            noteConnected(context, false)
        }
    }

    // ---- what the dashboard's guided set-up shows ----

    fun noteConnected(context: Context, connected: Boolean) {
        preferences(context).edit().putBoolean(KEY_CONNECTED, connected).putLong(KEY_CONNECTED_AT, System.currentTimeMillis()).apply()
    }

    fun noteReceived(context: Context, title: String, ntfyId: String? = null) {
        val editor = preferences(context).edit().putLong(KEY_LAST_AT, System.currentTimeMillis()).putString(KEY_LAST_TITLE, title)
        if (!ntfyId.isNullOrEmpty()) editor.putString(KEY_LAST_ID, ntfyId)
        editor.apply()
    }

    fun lastId(context: Context): String = preferences(context).getString(KEY_LAST_ID, "") ?: ""

    /** When the last notification arrived (ms), to start again from there after a break with more topics. */
    fun lastAt(context: Context): Long = preferences(context).getLong(KEY_LAST_AT, 0L)

    fun batteryUnrestricted(context: Context): Boolean {
        val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return true
        return power.isIgnoringBatteryOptimizations(context.packageName)
    }

    /** The state for the dashboard (KlippEyeApp.notifyState()). */
    fun state(context: Context, printer: String = ""): String {
        val settings = read(context)
        val p = preferences(context)
        val topic = if (printer.isEmpty()) settings.topic else others(context).optJSONObject(printer)?.optString(KEY_TOPIC, "") ?: ""
        return JSONObject()
            .put("permission", Notifications.permissionGranted(context))
            .put("askPermission", Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            .put("battery", batteryUnrestricted(context))
            .put("receive", settings.receive)
            .put("chosen", settings.chosen)
            .put("mode", mode(context))
            .put("firebaseBuilt", Notifications.firebaseReady(context))
            .put("ntfyTopic", topic)
            .put("connected", p.getBoolean(KEY_CONNECTED, false))
            .put("lastMessageAt", p.getLong(KEY_LAST_AT, 0L))
            .put("lastTitle", p.getString(KEY_LAST_TITLE, "") ?: "")
            .toString()
    }

    private const val TAG = "KlippEyePush"
}

/**
 * Listens to the Raspberry's ntfy topics (https://docs.ntfy.sh/subscribe/api/: GET <server>/<topics>/json, one JSON line per
 * event) and shows the notifications. It stays in the foreground (Android requires it for a connection that is always open),
 * with a discreet ongoing notification; it reconnects by itself when the network is back, and with `since` it gets the
 * messages missed meanwhile.
 */
class NtfyListenerService : Service() {
    // One thread per ntfy server (usually one: ntfy.sh). Each start of the service (settings changed) opens a new
    // "generation": the threads of the one before close their connection and end, the new ones listen to the current topics.
    @Volatile private var generation = 0
    private val threads = ConcurrentHashMap<String, Thread>()
    private val connections = ConcurrentHashMap<String, HttpURLConnection>()
    private val seen = LinkedHashSet<String>() // the ids of the last messages: guarded by itself

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Notifications.createChannels(this)
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, ONGOING_NOTIFICATION_ID, ongoingNotification(), type)
        val servers = PushSettings.byServer(this)
        if (servers.isEmpty()) {
            stopSelf()
            return START_NOT_STICKY
        }
        val mine = ++generation
        closeAll()
        for (server in servers.keys) {
            threads[server] = Thread({ listen(server, mine) }, "ntfy-listener").apply {
                isDaemon = true
                start()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        generation++
        closeAll()
        PushSettings.noteConnected(this, false)
        super.onDestroy()
    }

    private fun closeAll() {
        connections.values.forEach {
            try {
                it.disconnect()
            } catch (e: Exception) {
                // already closed
            }
        }
        threads.values.forEach { it.interrupt() }
        threads.clear()
    }

    private fun ongoingNotification(): Notification =
        NotificationCompat.Builder(this, Notifications.CHANNEL_LISTENING)
            .setSmallIcon(R.drawable.ic_stat_klippeye)
            .setContentTitle(getString(R.string.listening_title))
            .setContentText(getString(R.string.listening_text))
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setOngoing(true)
            .setShowWhen(false)
            .setContentIntent(Notifications.openAppIntent(this, 1))
            .build()

    private fun listen(server: String, mine: Int) {
        var wait = FIRST_WAIT_MS
        while (generation == mine) {
            val group = PushSettings.byServer(this)[server] ?: break
            try {
                connect(server, group.first, group.second, mine)
                wait = FIRST_WAIT_MS // it was connected: next time it tries again soon
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                Log.w(TAG, "Connection to ntfy lost: ${e.message}")
            }
            PushSettings.noteConnected(this, false)
            if (generation != mine) break
            try {
                Thread.sleep(wait)
            } catch (e: InterruptedException) {
                break
            }
            wait = minOf(wait * 2, MAX_WAIT_MS)
        }
        threads.remove(server, Thread.currentThread())
        if (generation == mine && threads.isEmpty()) stopSelf()
    }

    private fun connect(server: String, topics: String, token: String, mine: Int) {
        // With one topic it starts again from the last message (its id); with more topics from the time of the last one
        val since = if (!topics.contains(',')) PushSettings.lastId(this) else PushSettings.lastAt(this).let { if (it > 0) (it / 1000).toString() else "" }
        val address = server.trimEnd('/') + "/" + topics + "/json" + (if (since.isNotEmpty()) "?since=" + URLEncoder.encode(since, "UTF-8") else "")
        val connection = URL(address).openConnection() as HttpURLConnection
        connections[server] = connection
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        connection.setRequestProperty("User-Agent", "KlippEyeApp")
        if (token.isNotEmpty()) connection.setRequestProperty("Authorization", "Bearer $token")
        try {
            if (connection.responseCode !in 200..299) throw IOException("ntfy answered ${connection.responseCode}")
            BufferedReader(InputStreamReader(connection.inputStream, Charsets.UTF_8)).use { reader ->
                while (generation == mine) {
                    val line = reader.readLine() ?: break
                    handle(line)
                }
            }
        } finally {
            connections.remove(server, connection)
            connection.disconnect()
        }
    }

    /** True the first time an id is seen (starting again from the time of the last message may bring it back once). */
    private fun firstTime(id: String): Boolean = synchronized(seen) {
        if (!seen.add(id)) return false
        if (seen.size > SEEN_MAX) seen.remove(seen.first())
        true
    }

    private fun handle(line: String) {
        val event = try {
            JSONObject(line)
        } catch (e: Exception) {
            return
        }
        when (event.optString("event")) {
            "open", "keepalive" -> PushSettings.noteConnected(this, true)
            "message" -> {
                val id = event.optString("id", "")
                if (id.isNotEmpty() && !firstTime(id)) return
                val title = event.optString("title", "").ifEmpty { "KlippEye" }
                val text = event.optString("message", "")
                Notifications.show(this, Notifications.kindFromPriority(event.optInt("priority", 3)), title, text, id)
                PushSettings.noteReceived(this, "$title: $text", id)
            }
        }
    }

    private companion object {
        const val TAG = "KlippEyeNtfy"
        const val ONGOING_NOTIFICATION_ID = 7001
        const val FIRST_WAIT_MS = 5_000L
        const val MAX_WAIT_MS = 60_000L
        const val CONNECT_TIMEOUT_MS = 15_000
        const val READ_TIMEOUT_MS = 100_000 // ntfy sends a "keepalive" every 45 seconds: nothing for 100 s means the line is dead
        const val SEEN_MAX = 200
    }
}

/** When the phone starts and after an update of the app, listening starts again by itself (when it was chosen). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) PushSettings.apply(context)
    }
}
