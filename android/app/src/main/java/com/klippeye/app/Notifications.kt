package com.klippeye.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging

/**
 * The notifications the app shows: channels, the Firebase subscription and the notifications received (from Firebase with
 * the app open, or from ntfy).
 *
 * Firebase (only on the installation of whoever maintains the project, see [PushSettings]): the Raspberry
 * (klippeye_notifier.py) sends Firebase a message for the private topic it gave the app, and Firebase delivers it to every
 * subscribed phone. With the app closed the phone shows the notification by itself, on the channel named in the message
 * (that is why the channels are created as soon as the app starts). With the app open Android does not show it: it reaches
 * [KlippEyeMessagingService], which shows it here with [show].
 */
object Notifications {
    private const val TAG = "KlippEyeNotifications"

    // The channel ids are the same as KIND_CHANNEL in notifier/klippeye_notifier.py, and Android keeps the person's settings
    // under them: they never change. Their names are in the app's language (res/values*/strings.xml).
    const val CHANNEL_ALARMS = "allarmi" // printer error, filament run out, serious defects
    const val CHANNEL_WARNINGS = "avvisi" // paused, print stopped, defects found
    const val CHANNEL_PRINT = "stampa" // print complete, test
    const val CHANNEL_LISTENING = "ascolto" // the ongoing "KlippEye is listening" notification (ntfy), as discreet as possible

    // stored names of the Firebase subscription, kept from the first versions
    private const val PREFERENCES = "klippeye_notifiche"
    private const val KEY_SUBSCRIBED = "firebase_iscritto"
    private const val KEY_OLD_TOPIC_REMOVED = "vecchio_tolto"

    /** The channel of a kind of notification (the "type" field of the message). */
    fun channelFor(kind: String?): String = when (kind) {
        "error", "runout", "ai_cancel" -> CHANNEL_ALARMS
        "complete", "test" -> CHANNEL_PRINT
        else -> CHANNEL_WARNINGS
    }

    /** The kind of an ntfy notification from its priority (the same table as KIND_NTFY in klippeye_notifier.py): 5 alarm, 4 warning. */
    fun kindFromPriority(priority: Int): String = when {
        priority >= 5 -> "error"
        priority == 4 -> "paused"
        else -> "complete"
    }

    /** Creates the channels (Android 8+). Safe to call again: an existing channel only takes the new name and description. */
    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        fun channel(id: String, name: Int, description: Int, importance: Int) =
            NotificationChannel(id, context.getString(name), importance).apply { this.description = context.getString(description) }
        val alarms = channel(CHANNEL_ALARMS, R.string.channel_alarms, R.string.channel_alarms_description, NotificationManager.IMPORTANCE_HIGH).apply {
            enableVibration(true)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        val warnings = channel(CHANNEL_WARNINGS, R.string.channel_warnings, R.string.channel_warnings_description, NotificationManager.IMPORTANCE_HIGH).apply {
            enableVibration(true)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        val print = channel(CHANNEL_PRINT, R.string.channel_print, R.string.channel_print_description, NotificationManager.IMPORTANCE_DEFAULT).apply {
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        val listening = channel(CHANNEL_LISTENING, R.string.channel_listening, R.string.channel_listening_description, NotificationManager.IMPORTANCE_MIN).apply {
            setShowBadge(false)
        }
        manager.createNotificationChannels(listOf(alarms, warnings, print, listening))
    }

    /** The app was built with google-services.json (Firebase set up). */
    fun firebaseReady(context: Context): Boolean = try {
        FirebaseApp.getApps(context).isNotEmpty()
    } catch (e: Exception) {
        false
    }

    fun permissionGranted(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /**
     * Subscribes the phone to the Firebase `topic` ("" = to none), leaving the one before and the one written inside the apps
     * up to 1.2.0. Firebase remembers the subscriptions and, without a network, completes them as soon as it is back.
     */
    fun subscribeFirebase(context: Context, topic: String) {
        if (!firebaseReady(context)) return
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        val before = preferences.getString(KEY_SUBSCRIBED, "") ?: ""
        val messaging = FirebaseMessaging.getInstance()
        if (!preferences.getBoolean(KEY_OLD_TOPIC_REMOVED, false)) {
            messaging.unsubscribeFromTopic(PushSettings.OLD_TOPIC).addOnCompleteListener { task ->
                if (task.isSuccessful) preferences.edit().putBoolean(KEY_OLD_TOPIC_REMOVED, true).apply()
            }
        }
        if (before.isNotEmpty() && before != topic) messaging.unsubscribeFromTopic(before)
        if (topic.isNotEmpty()) {
            messaging.subscribeToTopic(topic).addOnCompleteListener { task ->
                if (!task.isSuccessful) Log.w(TAG, "Subscription failed", task.exception)
            }
        }
        preferences.edit().putString(KEY_SUBSCRIBED, topic).apply()
    }

    /** The intent that opens the app from a notification. */
    fun openAppIntent(context: Context, requestCode: Int): PendingIntent = PendingIntent.getActivity(
        context,
        requestCode,
        Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    /**
     * Shows a notification. A new notification with the same `tag` (by default its kind) takes the place of the one before;
     * ntfy messages pass their own id, so each one stays.
     */
    @SuppressLint("MissingPermission") // checked first: without it Android would not show it anyway
    fun show(context: Context, kind: String?, title: String, text: String, tag: String? = null) {
        if (!permissionGranted(context)) return
        createChannels(context)
        val channel = channelFor(kind)
        val notification = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_klippeye)
            .setColor(ContextCompat.getColor(context, R.color.ke_accent))
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(if (channel == CHANNEL_PRINT) NotificationCompat.PRIORITY_DEFAULT else NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent(context, 0))
            .build()
        NotificationManagerCompat.from(context).notify(if (tag.isNullOrEmpty()) kind ?: "klippeye" else tag, 1, notification)
    }
}
