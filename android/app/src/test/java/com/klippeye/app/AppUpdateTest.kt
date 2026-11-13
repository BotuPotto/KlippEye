package com.klippeye.app

import org.junit.AfterClass
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.BeforeClass
import org.junit.Test
import java.io.File
import java.io.IOException
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger

/**
 * The app's update (checks on the request, download, fingerprint, damaged files): no Android, no phone. A small server
 * inside the test stands in for the backend, also when it goes wrong on purpose.
 */
class AppUpdateTest {

    private fun sha(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** Runs `action` and checks that it stops with an UpdateException for `reason` (null: any IOException). */
    private fun assertRefused(reason: AppUpdate.Reason?, action: () -> Unit) {
        try {
            action()
        } catch (e: AppUpdate.UpdateException) {
            if (reason != null) assertEquals(reason, e.reason)
            return
        } catch (e: IOException) {
            if (reason == null) return
            fail("expected $reason, got $e")
        }
        fail("expected $reason, nothing happened")
    }

    @Test
    fun versionCodes() {
        val versions = listOf(
            "1.0.0" to 10000, "1.2.3" to 10203, "0.0.1" to 1, "99.99.99" to 999999, " 1.0.1 " to 10001, "2.10.0" to 21000, "01.0.0" to 10000,
            "1.0" to null, "1.0.0.0" to null, "100.0.0" to null, "1.0.100" to null, "a.b.c" to null, "" to null, "1.0.0-beta" to null, "1,0,0" to null,
        )
        for ((text, expected) in versions) assertEquals(text, expected, AppUpdate.versionCode(text))
        assertNull(AppUpdate.versionCode(null))
        val codes = listOf("1.0.0", "1.0.1", "1.0.9", "1.1.0", "1.9.9", "2.0.0").map { AppUpdate.versionCode(it)!! }
        assertTrue("the versions grow as their codes", codes.zipWithNext().all { (a, b) -> a < b })
    }

    @Test
    fun fingerprints() {
        assertEquals(GOOD, AppUpdate.validFingerprint(GOOD))
        assertEquals("ab".repeat(32), AppUpdate.validFingerprint("  " + "AB".repeat(32) + "\n"))
        for (bad in listOf("", "abc", "g".repeat(64), "a".repeat(63), "a".repeat(65), "a".repeat(32) + " " + "a".repeat(31), null)) {
            assertNull(bad, AppUpdate.validFingerprint(bad))
        }
    }

    private fun request(
        path: String? = "/app/KlippEye.apk", version: String? = "1.0.1", fingerprint: String? = GOOD, size: Long = 1000,
    ) = AppUpdate.checkRequest(URL("http://192.168.1.17:8085/"), path, version, fingerprint, size, 10000)

    @Test
    fun theRequestIsChecked() {
        val right = request()
        assertEquals("http://192.168.1.17:8085/app/KlippEye.apk", right.url.toString())
        assertTrue(right.code == 10001 && right.version == "1.0.1" && right.sha256 == GOOD && right.size == 1000L)
        assertEquals("1.0.1", request(version = " 1.0.1 ").version)
        assertEquals("192.168.1.17", request(path = "http://192.168.1.17:8085/app/KlippEye.apk").url.host)
        for (path in listOf(
            "http://example.com/app/KlippEye.apk", "http://192.168.1.99:8085/app/KlippEye.apk", "http://192.168.1.17:9999/app/KlippEye.apk",
            "https://192.168.1.17:8085/app/KlippEye.apk", "/app/other.apk", "/app/../api/health", "/app/KlippEye.apk?x=1", "", null,
        )) assertRefused(AppUpdate.Reason.OTHER_SERVER) { request(path = path) }
        assertRefused(null) { request(path = "file:///sdcard/x.apk") }
        assertRefused(AppUpdate.Reason.BAD_VERSION) { request(version = "what") }
        assertRefused(AppUpdate.Reason.BAD_VERSION) { request(version = null) }
        assertRefused(AppUpdate.Reason.UP_TO_DATE) { request(version = "1.0.0") }
        assertRefused(AppUpdate.Reason.UP_TO_DATE) { request(version = "0.9.9") }
        assertRefused(AppUpdate.Reason.NO_FINGERPRINT) { request(fingerprint = null) }
        assertRefused(AppUpdate.Reason.NO_FINGERPRINT) { request(fingerprint = "123") }
        for (size in listOf(0L, -5L, 151L * 1024 * 1024)) assertRefused(AppUpdate.Reason.BAD_SIZE) { request(size = size) }
    }

    private fun served(path: String, size: Long = APK.size.toLong(), fingerprint: String = APK_SHA) =
        AppUpdate.Request(URL("http://127.0.0.1:${server.localPort}$path"), "1.0.1", 10001, fingerprint, size)

    private fun left(folder: File) = folder.listFiles()?.map { it.name }?.sorted() ?: emptyList()

    @Test
    fun downloadAndReuse() {
        val folder = Files.createTempDirectory("update-test").toFile()
        try {
            val steps = mutableListOf<Long>()
            val file = AppUpdate.download(served("/app/KlippEye.apk"), folder) { steps += it }
            assertArrayEquals(APK, file.readBytes())
            assertEquals("KlippEye-1.0.1.apk", file.name)
            assertTrue("the progress grows up to the size", steps.zipWithNext().all { (a, b) -> a <= b } && steps.last() == APK.size.toLong())
            assertEquals(listOf("KlippEye-1.0.1.apk"), left(folder))
            assertEquals(APK_SHA, AppUpdate.sha256(file))

            val before = hits.get()
            val again = mutableListOf<Long>()
            AppUpdate.download(served("/app/KlippEye.apk"), folder) { again += it }
            assertEquals("the file already downloaded is used again without asking for it", before, hits.get())
            assertEquals(listOf(APK.size.toLong()), again)

            // an old or damaged file in the folder is not used and does not stay
            File(folder, "KlippEye-0.9.0.apk").writeBytes(ByteArray(10))
            file.writeBytes(APK.copyOf(1000))
            assertArrayEquals(APK, AppUpdate.download(served("/app/KlippEye.apk"), folder) { }.readBytes())
            assertEquals(listOf("KlippEye-1.0.1.apk"), left(folder))

            val created = File(folder, "sub/folder")
            assertTrue("the folder is made when missing", AppUpdate.download(served("/app/KlippEye.apk"), created) { }.isFile)
        } finally {
            folder.deleteRecursively()
        }
    }

    @Test
    fun aFailedDownloadLeavesNothing() {
        val folder = Files.createTempDirectory("update-test").toFile()
        try {
            fun fails(reason: AppUpdate.Reason?, request: AppUpdate.Request) {
                AppUpdate.clean(folder)
                assertRefused(reason) { AppUpdate.download(request, folder) { } }
                assertTrue(left(folder).toString(), left(folder).isEmpty())
            }
            fails(AppUpdate.Reason.NO_APK, served("/missing/app"))
            fails(AppUpdate.Reason.HTTP_ERROR, served("/broken/app"))
            fails(AppUpdate.Reason.DAMAGED, served("/damaged/app"))
            fails(AppUpdate.Reason.NOT_ANNOUNCED, served("/small/app"))
            fails(null, served("/cut/app"))
            fails(AppUpdate.Reason.TOO_BIG, served("/long/app"))
            fails(AppUpdate.Reason.NOT_ANNOUNCED, served("/app/KlippEye.apk", size = APK.size + 10L))
            fails(AppUpdate.Reason.DAMAGED, served("/app/KlippEye.apk", fingerprint = "0".repeat(64)))
            assertRefused(null) {
                AppUpdate.download(AppUpdate.Request(URL("http://127.0.0.1:1/app/KlippEye.apk"), "1.0.1", 10001, APK_SHA, APK.size.toLong()), folder) { }
            }
        } finally {
            folder.deleteRecursively()
        }
    }

    @Test
    fun cleanRemovesOldFiles() {
        val folder = Files.createTempDirectory("update-test").toFile()
        try {
            File(folder, "a.apk").apply { writeBytes(ByteArray(1)) }.setLastModified(System.currentTimeMillis() - 3_600_000)
            File(folder, "b.apk").writeBytes(ByteArray(1))
            AppUpdate.clean(folder, 600_000)
            assertEquals(listOf("b.apk"), left(folder))
            AppUpdate.clean(folder)
            assertTrue(left(folder).isEmpty())
            AppUpdate.clean(File(folder, "not-there")) // no error
        } finally {
            folder.deleteRecursively()
        }
    }

    @Test
    fun bridgeAnswer() {
        assertEquals("{\"version\":\"1.0.0\",\"code\":10000,\"canInstall\":true}", AppUpdate.infoJson("1.0.0", 10000, true))
        assertEquals("{\"version\":\"1.0x\",\"code\":5,\"canInstall\":false}", AppUpdate.infoJson("1.0\"}<x>", 5, false))
    }

    companion object {
        private val GOOD = "a".repeat(64)
        private val APK = ByteArray(300_000) { ((it * 31 + 7) % 251).toByte() }
        private val APK_SHA = MessageDigest.getInstance("SHA-256").digest(APK).joinToString("") { "%02x".format(it) }
        private val hits = AtomicInteger()
        private lateinit var server: ServerSocket

        // A tiny HTTP/1.1 server on a plain socket: the JDK's com.sun.net.httpserver is not on the Android
        // unit-test classpath. One request per connection, then the connection is closed.
        private fun head(out: OutputStream, code: Int, length: Long?) {
            val lines = StringBuilder("HTTP/1.1 $code X\r\nContent-Type: ${AppUpdate.APK_MIME_TYPE}\r\nConnection: close\r\n")
            if (length != null) lines.append("Content-Length: $length\r\n")
            out.write(lines.append("\r\n").toString().toByteArray())
        }

        private fun answer(out: OutputStream, code: Int, body: ByteArray) {
            head(out, code, body.size.toLong())
            out.write(body)
        }

        private fun serve(socket: Socket) {
            socket.use { s ->
                val reader = s.getInputStream().bufferedReader()
                val path = (reader.readLine() ?: return).split(" ").getOrNull(1)?.substringBefore("?") ?: return
                while (!reader.readLine().isNullOrEmpty()) { /* the request's headers: not needed */ }
                val out = s.getOutputStream()
                hits.incrementAndGet()
                when (path) {
                    "/app/KlippEye.apk" -> answer(out, 200, APK)
                    "/missing/app" -> answer(out, 404, "no".toByteArray())
                    "/broken/app" -> answer(out, 500, "no".toByteArray())
                    "/damaged/app" -> answer(out, 200, APK.copyOf().also { bytes -> bytes[1234] = (bytes[1234] + 1).toByte() })
                    "/small/app" -> answer(out, 200, APK.copyOf(1000))
                    "/cut/app" -> { // announces the whole file but stops halfway: the connection breaks
                        head(out, 200, APK.size.toLong())
                        out.write(APK, 0, 100_000)
                    }
                    "/long/app" -> { // no Content-Length (the end of the connection ends it), bigger than the backend announced
                        head(out, 200, null)
                        out.write(APK + ByteArray(5000))
                    }
                    else -> answer(out, 404, "no".toByteArray())
                }
                out.flush()
            }
        }

        @BeforeClass
        @JvmStatic
        fun startServer() {
            server = ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"))
            Thread {
                while (!server.isClosed) {
                    val socket = try { server.accept() } catch (e: IOException) { break }
                    Thread { try { serve(socket) } catch (e: IOException) { /* the client went away */ } }.apply { isDaemon = true }.start()
                }
            }.apply { isDaemon = true }.start()
        }

        @AfterClass
        @JvmStatic
        fun stopServer() {
            server.close()
        }
    }
}
