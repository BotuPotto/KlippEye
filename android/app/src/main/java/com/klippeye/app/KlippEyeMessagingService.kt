package com.klippeye.app

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Receives Firebase's messages. Called only with the app OPEN: with the app closed or in the background Android shows the
 * notification by itself (see [Notifications]).
 */
class KlippEyeMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val notification = message.notification
        val title = notification?.title ?: message.data["title"] ?: "KlippEye"
        val text = notification?.body ?: message.data["body"] ?: return
        Notifications.show(this, message.data["type"], title, text)
        PushSettings.noteReceived(this, "$title: $text")
    }

    /** The phone got a new code from Firebase: the topic subscription is made again (harmless when it is already there). */
    override fun onNewToken(token: String) {
        PushSettings.apply(this)
    }
}
