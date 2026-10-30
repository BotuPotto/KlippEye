package com.klippeye.app

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Riceve i messaggi di Firebase. Viene chiamato solo con l'app APERTA: con l'app chiusa o in secondo piano la notifica
 * la mostra Android da solo (vedi [Notifiche]).
 */
class KlippEyeMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val notifica = message.notification
        val titolo = notifica?.title ?: message.data["title"] ?: "KlippEye"
        val testo = notifica?.body ?: message.data["body"] ?: return
        Notifiche.mostra(this, message.data["type"], titolo, testo)
        Ascolto.segnaRicevuta(this, "$titolo: $testo")
    }

    /** Il telefono ha ricevuto un nuovo codice da Firebase: l'iscrizione all'argomento va rifatta, e' innocuo se c'e' gia'. */
    override fun onNewToken(token: String) {
        Ascolto.applica(this)
    }
}
