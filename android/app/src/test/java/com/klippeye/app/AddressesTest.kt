package com.klippeye.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The app's addresses (cleaning, private networks, the list of attempts) and the other printers: no Android, no phone. */
class AddressesTest {

    @Test
    fun cleanKeepsOnlyTheAddress() {
        val cases = listOf(
            "192.168.1.17" to "192.168.1.17", "  192.168.1.17  " to "192.168.1.17", "http://192.168.1.17/" to "192.168.1.17",
            "HTTP://192.168.1.17:8085/dashboard?x=1#y" to "192.168.1.17", "https://172.25.1.2:443" to "172.25.1.2",
            "KlippEye.LOCAL" to "klippeye.local", "klippeye" to "klippeye", "10.0.0.5:8080" to "10.0.0.5", "192.168.1.17:99999" to "192.168.1.17",
        )
        for ((input, expected) in cases) assertEquals(input, expected, Addresses.clean(input))
        val refused = listOf(
            "999.1.1.1", "192.168.1", "192.168.1.1.1", "192.168..1", "1.2.3.256", "1234.1.1.1", "", "   ", "two words", "http://", "-abc",
            "abc-", "a_b", "<script>", "javascript:alert(1)", "a".repeat(120),
        )
        for (input in refused) assertNull(input, Addresses.clean(input))
        assertNull(Addresses.clean(null))
    }

    @Test
    fun onlyPrivateNetworks() {
        val private = listOf(
            "192.168.1.17", "192.168.255.1", "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.25.1.2", "172.31.9.9", "100.64.0.1", "100.127.1.1",
            "klippeye", "klippeye.local", "pi.lan", "pi.home.arpa", "printer.internal",
        )
        val public = listOf(
            "8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.1.1", "192.167.1.1", "100.63.0.1", "100.128.0.1", "11.0.0.1", "127.0.0.1", "169.254.1.1",
            "example.com", "klippeye.example.org", "pi.local.evil.com",
        )
        for (host in private) assertTrue(host, Addresses.isPrivate(host))
        for (host in public) assertFalse(host, Addresses.isPrivate(host))
    }

    @Test
    fun checkSaysWhichAddressIsWrong() {
        assertEquals(Addresses.Check.OK, Addresses.check("192.168.1.17", "172.25.1.2"))
        assertEquals(Addresses.Check.OK, Addresses.check("192.168.1.17", ""))
        assertEquals(Addresses.Check.OK, Addresses.check("pi.local", null))
        assertEquals(Addresses.Check.OK, Addresses.check("http://192.168.1.50:8080/", "10.1.2.3"))
        assertEquals(Addresses.Check.LOCAL_INVALID, Addresses.check("999.1.1.1", "10.1.2.3"))
        assertEquals(Addresses.Check.LOCAL_INVALID, Addresses.check(null, "10.1.2.3"))
        assertEquals(Addresses.Check.LOCAL_INVALID, Addresses.check("", "10.1.2.3"))
        assertEquals(Addresses.Check.EXTERNAL_INVALID, Addresses.check("10.1.2.3", "what now"))
        assertEquals(Addresses.Check.LOCAL_NOT_PRIVATE, Addresses.check("8.8.8.8", "10.1.2.3"))
        assertEquals(Addresses.Check.EXTERNAL_NOT_PRIVATE, Addresses.check("10.1.2.3", "example.com"))
    }

    @Test
    fun attemptsAlternateLocalAndExternal() {
        fun hosts(pair: Addresses.AddressPair) = Addresses.candidates(pair).map { it.host }
        fun attempts(pair: Addresses.AddressPair) = Addresses.attempts(pair).map { it.host }
        assertTrue("no address: nothing to try (the person is asked)", hosts(Addresses.NONE).isEmpty() && attempts(Addresses.NONE).isEmpty() && Addresses.NONE.empty)
        assertEquals(listOf("192.168.1.50", "172.25.9.9", "192.168.1.50", "172.25.9.9"), attempts(Addresses.AddressPair("192.168.1.50", "172.25.9.9")))
        assertEquals(listOf("192.168.1.50", "192.168.1.50"), attempts(Addresses.AddressPair("192.168.1.50", "")))
        assertEquals(listOf("10.0.0.9"), hosts(Addresses.AddressPair("10.0.0.9", "10.0.0.9")))
        val first = Addresses.candidates(Addresses.AddressPair("pi.local", "172.25.1.1")).first()
        assertTrue(first.host == "pi.local" && first.network == Addresses.Network.LOCAL)
        assertEquals("http://192.168.1.17:8085/", Addresses.Candidate("192.168.1.17", Addresses.Network.LOCAL).url)
    }

    @Test
    fun whereKlippEyeIsLookedFor() {
        assertEquals(listOf("http://192.168.1.17/", "http://192.168.1.17:8085/"), Addresses.variants("192.168.1.17", false))
        assertEquals(listOf("https://pi.local/", "http://pi.local/", "http://pi.local:8085/"), Addresses.variants("pi.local", true))
        assertTrue(Addresses.isKlippEye("application/json", "{\"ok\": true, \"enabled\": false, \"logged_in\": true}"))
        assertTrue(Addresses.isKlippEye("application/json; charset=utf-8", "{\"enabled\":true}"))
        assertFalse("another page", Addresses.isKlippEye("text/html", "<html>enabled</html>"))
        assertFalse("another JSON", Addresses.isKlippEye("application/json", "{\"result\": {}}"))
        assertFalse(Addresses.isKlippEye(null, null))
        assertEquals("{\"local\":\"192.168.1.17\",\"external\":\"\"}", Addresses.toJson(Addresses.AddressPair("192.168.1.17", "")))
    }

    @Test
    fun otherPrinters() {
        assertEquals("192.168.1.50", Printers.clean("http://192.168.1.50/"))
        assertEquals("192.168.1.50", Printers.clean("192.168.1.50:8085"))
        assertEquals("192.168.1.50:8080", Printers.clean("192.168.1.50:8080"))
        assertEquals("pi.local:81", Printers.clean("http://pi.local:81/x"))
        assertNull("public address", Printers.clean("8.8.8.8"))
        assertNull("port out of range", Printers.clean("192.168.1.50:70000"))
        assertNull(Printers.clean(null))
        assertEquals("http://192.168.1.50:8080/", Printers.url("192.168.1.50:8080"))
        assertEquals("http://192.168.1.50:8085/", Printers.url("192.168.1.50"))
    }

    @Test
    fun certificateFingerprints() {
        val colons = (1..32).joinToString(":") { "AB" }
        assertEquals(colons, Certificates.clean("ab".repeat(32)))
        assertEquals(colons, Certificates.clean("  " + colons.lowercase() + " "))
        assertNull(Certificates.clean("ab".repeat(31)))
        assertNull(Certificates.clean("zz".repeat(32)))
        assertNull(Certificates.clean(null))
        // SHA-256 of an empty input, as the browsers show a fingerprint
        assertEquals("E3:B0:C4:42:98:FC:1C:14:9A:FB:F4:C8:99:6F:B9:24:27:AE:41:E4:64:9B:93:4C:A4:95:99:1B:78:52:B8:55", Certificates.fingerprint(ByteArray(0)))
    }

    @Test
    fun howNotificationsArrive() {
        fun settings(receive: Boolean, chosen: Boolean, topic: String, firebase: String) = PushSettings.Settings(receive, chosen, "https://ntfy.sh", topic, "", firebase)
        assertEquals("firebase before the choice", "firebase", settings(false, false, "", "fb-topic").mode(true))
        assertEquals("no Firebase in the app: nothing before the choice", "", settings(false, false, "t", "fb-topic").mode(false))
        assertEquals("not on this phone", "", settings(false, true, "t", "fb-topic").mode(true))
        assertEquals("ntfy after the choice", "ntfy", settings(true, true, "t", "").mode(true))
        assertEquals("Firebase wins over ntfy", "firebase", settings(true, true, "t", "fb-topic").mode(true))
        assertEquals("no topic: nothing", "", settings(true, true, "", "").mode(true))
        assertEquals("error", Notifications.kindFromPriority(5))
        assertEquals("paused", Notifications.kindFromPriority(4))
        assertEquals("complete", Notifications.kindFromPriority(3))
        assertEquals(Notifications.CHANNEL_ALARMS, Notifications.channelFor("runout"))
        assertEquals(Notifications.CHANNEL_PRINT, Notifications.channelFor("test"))
        assertEquals(Notifications.CHANNEL_WARNINGS, Notifications.channelFor("paused"))
        assertEquals(Notifications.CHANNEL_WARNINGS, Notifications.channelFor(null))
    }
}
