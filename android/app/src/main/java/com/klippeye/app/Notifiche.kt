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
 * Notifiche push (Firebase Cloud Messaging): canali, iscrizione all'argomento privato e notifiche ricevute con l'app aperta.
 *
 * Il Raspberry (klippeye_notifier.py) manda a Firebase un messaggio per l'argomento `notification_topic`; Firebase lo recapita
 * a tutti i telefoni iscritti. Con l'app chiusa la notifica la mostra il telefono da solo, usando il canale scritto nel
 * messaggio (per questo i canali vanno creati subito, appena l'app parte). Con l'app aperta Android non la mostra:
 * arriva a [KlippEyeMessagingService], che la mostra qui con [mostra].
 */
object Notifiche {
    private const val TAG = "KlippEyeNotifiche"

    // Gli stessi nomi di KIND_CHANNEL in notifier/klippeye_notifier.py
    const val CANALE_ALLARMI = "allarmi" // stampante in errore, filamento esaurito, difetti gravi
    const val CANALE_AVVISI = "avvisi" //   pausa, stampa interrotta, difetti rilevati
    const val CANALE_STAMPA = "stampa" //   stampa completata, prova

    /** Il canale di un tipo di notifica (il campo "type" del messaggio). */
    fun canalePer(tipo: String?): String = when (tipo) {
        "error", "runout", "ai_cancel" -> CANALE_ALLARMI
        "complete", "test" -> CANALE_STAMPA
        else -> CANALE_AVVISI
    }

    /** Crea i tre canali (Android 8+). Si puo' chiamare quante volte si vuole: se esistono gia' non cambia nulla. */
    fun creaCanali(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(NotificationManager::class.java) ?: return
            val allarmi = NotificationChannel(CANALE_ALLARMI, "Allarmi e guasti", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Stampante in errore, filamento esaurito, difetti gravi rilevati dall'IA"
                enableVibration(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            val avvisi = NotificationChannel(CANALE_AVVISI, "Avvisi", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Stampa in pausa o interrotta, difetti rilevati dall'IA"
                enableVibration(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            val stampa = NotificationChannel(CANALE_STAMPA, "Stampa completata", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Fine stampa e notifiche di prova"
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            manager.createNotificationChannels(listOf(allarmi, avvisi, stampa))
        }
    }

    /**
     * Si iscrive all'argomento privato. Firebase ricorda l'iscrizione e, se ora manca la rete, la completa appena torna.
     * Restituisce false se l'app e' stata costruita senza google-services.json (Firebase non e' configurato).
     */
    fun iscrivi(context: Context, alTermine: ((Boolean) -> Unit)? = null): Boolean {
        if (FirebaseApp.getApps(context).isEmpty()) return false
        FirebaseMessaging.getInstance().subscribeToTopic(context.getString(R.string.notification_topic))
            .addOnCompleteListener { task ->
                if (!task.isSuccessful) Log.w(TAG, "Iscrizione non riuscita", task.exception)
                alTermine?.invoke(task.isSuccessful)
            }
        return true
    }

    /** Mostra una notifica (usata con l'app aperta). Una nuova notifica dello stesso tipo prende il posto della precedente. */
    @SuppressLint("MissingPermission") // il permesso e' controllato qui sotto
    fun mostra(context: Context, tipo: String?, titolo: String, testo: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            return // l'utente non ha dato il permesso: Android non la mostrerebbe comunque
        }
        creaCanali(context)
        val canale = canalePer(tipo)
        val apriApp = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notifica = NotificationCompat.Builder(context, canale)
            .setSmallIcon(R.drawable.ic_stat_klippeye)
            .setColor(ContextCompat.getColor(context, R.color.vz_accent))
            .setContentTitle(titolo)
            .setContentText(testo)
            .setStyle(NotificationCompat.BigTextStyle().bigText(testo))
            .setPriority(if (canale == CANALE_STAMPA) NotificationCompat.PRIORITY_DEFAULT else NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(apriApp)
            .build()
        NotificationManagerCompat.from(context).notify(tipo ?: "klippeye", 1, notifica)
    }
}
