package com.vzbot.dashboard

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File

/**
 * La parte dell'aggiornamento dell'app che parla con Android: la versione installata, il permesso "Installa app
 * sconosciute", l'installazione vera e propria. Il resto (controlli, scaricamento, impronta) e' in Aggiornamento.kt.
 */
object AggiornamentoAndroid {
    /** Cartella dentro la cache dell'app dove si scarica l'APK; deve essere la stessa di res/xml/file_paths.xml. */
    private const val CARTELLA = "aggiornamenti"

    fun cartella(context: Context): File = File(context.cacheDir, CARTELLA)

    /** Versione dell'app installata: (nome, numero interno). */
    fun installata(context: Context): Pair<String, Int> {
        @Suppress("DEPRECATION")
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        @Suppress("DEPRECATION")
        val codice = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) info.longVersionCode.toInt() else info.versionCode
        return Pair(info.versionName ?: "?", codice)
    }

    /** Android 8+ fa concedere a ogni app il permesso "Installa app sconosciute"; prima non c'e'. */
    fun puoInstallare(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || context.packageManager.canRequestPackageInstalls()

    /** La pagina di Android dove si attiva "Consenti da questa fonte" per VzBot. */
    fun intentPermesso(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))

    /** Apre l'installazione di Android per il file scaricato (la conferma la da' l'utente). */
    fun intentInstallazione(context: Context, file: File): Intent {
        val uri = FileProvider.getUriForFile(context, context.packageName + ".aggiornamenti", file)
        return Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, Aggiornamento.TIPO_APK)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
}
