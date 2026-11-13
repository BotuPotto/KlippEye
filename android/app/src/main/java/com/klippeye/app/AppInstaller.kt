package com.klippeye.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File

/**
 * The part of the app's update that talks to Android: the installed version, the "Install unknown apps" permission, the
 * installation itself. The rest (checks, download, fingerprint) is in AppUpdate.kt.
 */
object AppInstaller {
    /** The folder in the app's cache where the APK is downloaded; the same as res/xml/file_paths.xml. */
    private const val FOLDER = "updates"
    /** The folder used up to app 1.7 (it is emptied once, so nothing stays in the cache). */
    private const val OLD_FOLDER = "aggiornamenti"

    fun folder(context: Context): File = File(context.cacheDir, FOLDER)

    fun oldFolder(context: Context): File = File(context.cacheDir, OLD_FOLDER)

    /** The version of the installed app: (name, internal number). */
    fun installed(context: Context): Pair<String, Int> {
        @Suppress("DEPRECATION")
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        @Suppress("DEPRECATION")
        val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) info.longVersionCode.toInt() else info.versionCode
        return Pair(info.versionName ?: "?", code)
    }

    /** From Android 8 each app must be allowed to "Install unknown apps"; before, the permission does not exist. */
    fun canInstall(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || context.packageManager.canRequestPackageInstalls()

    /** Android's page where "Allow from this source" is switched on for KlippEye. */
    fun permissionIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))

    /** Opens Android's installer on the downloaded file (the person confirms). */
    fun installIntent(context: Context, file: File): Intent {
        val uri = FileProvider.getUriForFile(context, context.packageName + ".updates", file)
        return Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, AppUpdate.APK_MIME_TYPE)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
}
