package com.klippeye.app

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * The app updating itself. The Raspberry keeps the latest APK (the repository's apk/ folder, built by GitHub) and serves it
 * at /app/KlippEye.apk; the dashboard (Settings → Updates → Android app) asks the app to download it with
 * `KlippEyeApp.updateApp(...)`, and the app hands it to Android's installer.
 *
 * Before installing anything the app checks:
 *  - that the address is the KlippEye it is connected to, with the fixed path [APK_PATH] (no other site, no other file);
 *  - that the version is newer than the installed one;
 *  - that the downloaded file has the size and the SHA-256 fingerprint the backend announced (a damaged or partial file is thrown away);
 * and Android, for its part, installs only an APK signed with the SAME key as the current app, and always asks first.
 *
 * Nothing here needs Android (plain Java), so it is tested on its own: AppUpdateTest. What talks to the system (installed
 * version, permission, installer) is in AppInstaller.kt.
 */
object AppUpdate {
    /** The only path the app accepts its own update from. */
    const val APK_PATH = "/app/KlippEye.apk"
    const val APK_MIME_TYPE = "application/vnd.android.package-archive"

    private const val MAX_SIZE = 150L * 1024 * 1024
    private const val CONNECT_TIMEOUT_MS = 5000
    private const val READ_TIMEOUT_MS = 30000
    private const val BUFFER_SIZE = 64 * 1024
    private val VERSION_FORMAT = Regex("""^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$""")
    private val FINGERPRINT_FORMAT = Regex("[0-9a-f]{64}")

    /** Why an update cannot go on. The text shown to the person is chosen by the app (MainActivity), in its language. */
    enum class Reason { BAD_ADDRESS, OTHER_SERVER, BAD_VERSION, UP_TO_DATE, NO_FINGERPRINT, BAD_SIZE, NO_STORAGE, NO_APK, HTTP_ERROR, NOT_ANNOUNCED, TOO_BIG, INTERRUPTED, DAMAGED, CANNOT_SAVE }

    /** A refused request or a failed download; `detail` is the HTTP code or the bytes received, when they matter. */
    class UpdateException(val reason: Reason, val detail: String = "") : IOException(reason.name + if (detail.isEmpty()) "" else ": $detail")

    /** What the page asked for, already checked: where to download, which version, and how to recognise the right file. */
    class Request(val url: URL, val version: String, val code: Int, val sha256: String, val size: Long)

    /** "1.2.3" becomes 10203 (the same formula as app/build.gradle); null when it is not three numbers from 0 to 99. */
    fun versionCode(name: String?): Int? {
        val found = VERSION_FORMAT.matchEntire(name?.trim() ?: "") ?: return null
        val (major, minor, patch) = found.destructured
        return major.toInt() * 10000 + minor.toInt() * 100 + patch.toInt()
    }

    /** The fingerprint in lower case when it is 64 hexadecimal digits, otherwise null. */
    fun validFingerprint(text: String?): String? {
        val clean = text?.trim()?.lowercase() ?: return null
        return if (FINGERPRINT_FORMAT.matches(clean)) clean else null
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return hex(digest.digest())
    }

    /**
     * Checks what the page sent. `base` is the address of the loaded dashboard; `installedCode` the version of this app.
     * Throws an [UpdateException] when something is wrong.
     */
    fun checkRequest(base: URL, path: String?, version: String?, sha256: String?, size: Long, installedCode: Int): Request {
        val url = try {
            URL(base, path ?: "")
        } catch (e: Exception) {
            throw UpdateException(Reason.BAD_ADDRESS)
        }
        val sameServer = url.protocol == base.protocol && url.host == base.host && url.port == base.port
        if (!sameServer || url.path != APK_PATH || !url.query.isNullOrEmpty()) throw UpdateException(Reason.OTHER_SERVER)
        val code = versionCode(version) ?: throw UpdateException(Reason.BAD_VERSION)
        if (code <= installedCode) throw UpdateException(Reason.UP_TO_DATE)
        val fingerprint = validFingerprint(sha256) ?: throw UpdateException(Reason.NO_FINGERPRINT)
        if (size <= 0 || size > MAX_SIZE) throw UpdateException(Reason.BAD_SIZE)
        return Request(url, version!!.trim(), code, fingerprint, size)
    }

    /** Removes from `folder` the files older than `olderThanMs` (0 = all of them). */
    fun clean(folder: File, olderThanMs: Long = 0) {
        val limit = System.currentTimeMillis() - olderThanMs
        folder.listFiles()?.forEach { if (it.isFile && it.lastModified() <= limit) it.delete() }
    }

    /**
     * Downloads the APK into `folder` and checks it; `progress` receives the bytes downloaded so far. -> the file, ready.
     * A file already downloaded and identical (while the permission was being granted, say) is used again. On an error
     * nothing half-written is left behind.
     */
    fun download(
        request: Request,
        folder: File,
        open: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
        progress: (Long) -> Unit,
    ): File {
        if (!folder.isDirectory && !folder.mkdirs()) throw UpdateException(Reason.NO_STORAGE)
        val target = File(folder, "KlippEye-${request.version}.apk")
        if (target.isFile && target.length() == request.size && sha256(target) == request.sha256) {
            progress(request.size)
            return target
        }
        clean(folder)
        val partial = File(folder, target.name + ".part")
        val connection = open(request.url) // over https: only the Raspberry's own certificate (Certificates.kt)
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        try {
            val status = connection.responseCode
            if (status == 404) throw UpdateException(Reason.NO_APK)
            if (status != 200) throw UpdateException(Reason.HTTP_ERROR, status.toString())
            val announced = connection.contentLengthLong
            if (announced >= 0 && announced != request.size) throw UpdateException(Reason.NOT_ANNOUNCED)
            val digest = MessageDigest.getInstance("SHA-256")
            var received = 0L
            connection.inputStream.use { input ->
                FileOutputStream(partial).use { output ->
                    val buffer = ByteArray(BUFFER_SIZE)
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        received += read
                        if (received > request.size) throw UpdateException(Reason.TOO_BIG)
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                        progress(received)
                    }
                }
            }
            if (received != request.size) throw UpdateException(Reason.INTERRUPTED, "$received/${request.size}")
            if (hex(digest.digest()) != request.sha256) throw UpdateException(Reason.DAMAGED)
            if (!partial.renameTo(target)) throw UpdateException(Reason.CANNOT_SAVE)
            return target
        } catch (e: Exception) {
            partial.delete()
            throw e
        } finally {
            connection.disconnect()
        }
    }

    /** What `KlippEyeApp.appInfo()` answers: {"version":"1.0.0","code":10000,"canInstall":true}. */
    fun infoJson(version: String, code: Int, canInstall: Boolean): String {
        val clean = version.replace(Regex("[^0-9A-Za-z._+-]"), "")
        return "{\"version\":\"$clean\",\"code\":$code,\"canInstall\":$canInstall}"
    }
}
