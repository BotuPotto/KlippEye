// Prova da sola degli indirizzi dell'app (pulizia, reti private, elenco dei tentativi): niente Android, niente telefono.
// Si lancia da fuori di Gradle (vedi README, "Indirizzi dell'app"):
//   kotlinc -cp android.jar ../app/src/main/java/com/vzbot/dashboard/Indirizzi.kt IndirizziTest.kt -d prova
//   java -cp prova:kotlin-stdlib.jar:android.jar com.vzbot.dashboard.IndirizziTestKt
package com.vzbot.dashboard

var errori = 0

fun prova(nome: String, ok: Boolean, dettaglio: String = "") {
    if (!ok) errori++
    println((if (ok) "PASS " else "FAIL ") + nome + (if (!ok && dettaglio.isNotEmpty()) " :: $dettaglio" else ""))
}

fun main() {
    // pulisci: toglie http://, porta e percorso; minuscole; null se non e' un indirizzo
    val casi = listOf(
        "192.168.1.17" to "192.168.1.17", "  192.168.1.17  " to "192.168.1.17", "http://192.168.1.17/" to "192.168.1.17",
        "HTTP://192.168.1.17:8085/dashboard?x=1#y" to "192.168.1.17", "https://172.25.170.177:443" to "172.25.170.177",
        "VzBot.LOCAL" to "vzbot.local", "vzbot" to "vzbot", "10.0.0.5:8080" to "10.0.0.5",
        "999.1.1.1" to null, "192.168.1" to null, "192.168.1.1.1" to null, "192.168..1" to null, "1.2.3.256" to null, "1234.1.1.1" to null,
        "" to null, "   " to null, "due parole" to null, "http://" to null, "-abc" to null, "abc-" to null, "a_b" to null, "<script>" to null,
        "javascript:alert(1)" to null, "192.168.1.17:99999" to "192.168.1.17", "a".repeat(120) to null,
    )
    for ((entrata, atteso) in casi) prova("pulisci(\"${entrata.take(30)}\") = $atteso", Indirizzi.pulisci(entrata) == atteso, "ottenuto ${Indirizzi.pulisci(entrata)}")
    prova("pulisci(null) = null", Indirizzi.pulisci(null) == null)

    // privato: casa, VPN, ZeroTier, nomi locali; mai internet
    val privati = listOf("192.168.1.17", "192.168.255.1", "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.25.170.177", "172.31.9.9", "100.64.0.1", "100.127.1.1", "vzbot", "vzbot.local", "pi.lan", "pi.home.arpa", "stampante.internal")
    val pubblici = listOf("8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.1.1", "192.167.1.1", "100.63.0.1", "100.128.0.1", "11.0.0.1", "127.0.0.1", "169.254.1.1", "example.com", "vzbot.example.org", "pi.local.evil.com")
    for (h in privati) prova("privato($h)", Indirizzi.privato(h))
    for (h in pubblici) prova("NON privato($h)", !Indirizzi.privato(h))

    // controlla: "ok" o il motivo
    prova("controlla: i due di fabbrica sono ok", Indirizzi.controlla("192.168.1.17", "172.25.170.177") == "ok")
    prova("controlla: con http:// e porta e' ok", Indirizzi.controlla("http://192.168.1.50:8080/", "10.1.2.3") == "ok")
    prova("controlla: locale sbagliato", Indirizzi.controlla("999.1.1.1", "10.1.2.3").contains("IP locale"))
    prova("controlla: esterno sbagliato", Indirizzi.controlla("10.1.2.3", "boh boh").contains("IP esterno"))
    prova("controlla: pubblico rifiutato", Indirizzi.controlla("8.8.8.8", "10.1.2.3").contains("rete privata") && Indirizzi.controlla("10.1.2.3", "example.com").contains("rete privata"))
    prova("controlla: null", Indirizzi.controlla(null, "10.1.2.3") != "ok" && Indirizzi.controlla("10.1.2.3", null) != "ok")

    // candidati: locale, esterno, poi quelli di fabbrica, senza ripetizioni
    fun hosts(c: Indirizzi.Coppia) = Indirizzi.candidati(c).map { it.host }
    prova("candidati di fabbrica: due tentativi, come prima", hosts(Indirizzi.DI_FABBRICA) == listOf("192.168.1.17", "172.25.170.177"), hosts(Indirizzi.DI_FABBRICA).toString())
    prova("candidati cambiati: quattro, in ordine", hosts(Indirizzi.Coppia("192.168.1.50", "172.25.9.9")) == listOf("192.168.1.50", "172.25.9.9", "192.168.1.17", "172.25.170.177"))
    prova("candidati: solo il locale cambiato", hosts(Indirizzi.Coppia("192.168.1.50", "172.25.170.177")) == listOf("192.168.1.50", "172.25.170.177", "192.168.1.17"))
    prova("candidati: locale e esterno uguali non si ripetono", hosts(Indirizzi.Coppia("10.0.0.9", "10.0.0.9")) == listOf("10.0.0.9", "192.168.1.17", "172.25.170.177"))
    prova("candidati: il primo e' sempre il locale scelto", Indirizzi.candidati(Indirizzi.Coppia("pi.local", "172.25.1.1")).first().let { it.host == "pi.local" && it.etichetta == "rete locale" })
    prova("candidato: indirizzo con la porta del Brain", Indirizzi.Candidato("192.168.1.17", "x").url == "http://192.168.1.17:8085/")
    prova("comeJson", Indirizzi.comeJson(Indirizzi.DI_FABBRICA) == "{\"local\":\"192.168.1.17\",\"external\":\"172.25.170.177\"}")

    println(if (errori == 0) "ALL PASS" else "FAILS: $errori")
    if (errori != 0) System.exit(1)
}
