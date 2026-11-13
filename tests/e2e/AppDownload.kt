// End-to-end check: the real Kotlin code of the app (AppUpdate.kt) against the real backend.
// args: <backend address> <version> <sha256> <size> <installed version code> <folder>
import com.klippeye.app.AppUpdate
import java.io.File
import java.io.IOException
import java.net.URL

fun main(args: Array<String>) {
    try {
        val request = AppUpdate.checkRequest(URL(args[0]), "/app/KlippEye.apk", args[1], args[2], args[3].toLong(), args[4].toInt())
        val file = AppUpdate.download(request, File(args[5])) { }
        println("OK " + file.absolutePath + " " + AppUpdate.sha256(file))
    } catch (e: IOException) {
        println("ERROR " + e.message)
        System.exit(2)
    }
}
