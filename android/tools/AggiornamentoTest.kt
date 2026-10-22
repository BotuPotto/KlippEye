// Prova da sola dell'aggiornamento dell'app (controlli sulla richiesta, scaricamento, impronta, file rovinati): niente Android,
// niente telefono. Un piccolo server nel programma fa da Brain, anche quando sbaglia di proposito.
// Si lancia da fuori di Gradle (vedi README, "Prove"):
//   kotlinc app/src/main/java/com/vzbot/dashboard/Aggiornamento.kt tools/AggiornamentoTest.kt -d prova
//   java -cp prova:kotlin-stdlib.jar com.vzbot.dashboard.AggiornamentoTestKt
package com.vzbot.dashboard

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.URL
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger

var errori = 0

fun prova(nome: String, ok: Boolean, dettaglio: String = "") {
    if (!ok) errori++
    println((if (ok) "PASS " else "FAIL ") + nome + (if (!ok && dettaglio.isNotEmpty()) " :: $dettaglio" else ""))
}

fun sha(byte: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(byte).joinToString("") { "%02x".format(it) }

/** Esegue `azione` e dice se ha lanciato un IOException il cui messaggio contiene `parola`. */
fun rifiuta(parola: String, azione: () -> Unit): Boolean = try {
    azione()
    false
} catch (e: IOException) {
    e.message?.contains(parola) == true
}

fun main() {
    // ---- codice della versione (stessa formula di app/build.gradle) ----
    val versioni = listOf(
        "1.0.0" to 10000, "1.2.3" to 10203, "0.0.1" to 1, "99.99.99" to 999999, " 1.0.1 " to 10001, "2.10.0" to 21000,
        "1.0" to null, "1.0.0.0" to null, "01.0.0" to 10000, "100.0.0" to null, "1.0.100" to null, "a.b.c" to null, "" to null, "1.0.0-beta" to null, "mk218" to null, "1,0,0" to null,
    )
    for ((testo, atteso) in versioni) prova("codiceVersione(\"$testo\") = $atteso", Aggiornamento.codiceVersione(testo) == atteso, "ottenuto ${Aggiornamento.codiceVersione(testo)}")
    prova("codiceVersione(null) = null", Aggiornamento.codiceVersione(null) == null)
    prova("le versioni crescono come i loro codici", listOf("1.0.0", "1.0.1", "1.0.9", "1.1.0", "1.9.9", "2.0.0").map { Aggiornamento.codiceVersione(it)!! }.zipWithNext().all { (a, b) -> a < b })

    // ---- impronta ----
    val buona = "a".repeat(64)
    prova("impronta: 64 cifre", Aggiornamento.improntaValida(buona) == buona)
    prova("impronta: maiuscole e spazi si sistemano", Aggiornamento.improntaValida("  " + "AB".repeat(32) + "\n") == "ab".repeat(32))
    for (cattiva in listOf("", "abc", "g".repeat(64), "a".repeat(63), "a".repeat(65), "a".repeat(32) + " " + "a".repeat(31))) prova("impronta non valida: \"${cattiva.take(12)}...\"", Aggiornamento.improntaValida(cattiva) == null)
    prova("impronta: null", Aggiornamento.improntaValida(null) == null)

    // ---- controllo della richiesta ----
    val base = URL("http://192.168.1.17:8085/")
    val installata = 10000
    fun richiesta(percorso: String? = "/app/VzBot.apk", versione: String? = "1.0.1", impronta: String? = buona, grandezza: Long = 1000, b: URL = base, codice: Int = installata) =
        Aggiornamento.controllaRichiesta(b, percorso, versione, impronta, grandezza, codice)
    val giusta = richiesta()
    prova("richiesta valida", giusta.url.toString() == "http://192.168.1.17:8085/app/VzBot.apk" && giusta.codice == 10001 && giusta.versione == "1.0.1" && giusta.sha256 == buona && giusta.grandezza == 1000L)
    prova("richiesta: la versione si pulisce dagli spazi", richiesta(versione = " 1.0.1 ").versione == "1.0.1")
    prova("richiesta: indirizzo completo dello stesso Brain ok", richiesta(percorso = "http://192.168.1.17:8085/app/VzBot.apk").url.host == "192.168.1.17")
    prova("richiesta: altro sito rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "http://example.com/app/VzBot.apk") })
    prova("richiesta: altro indirizzo privato rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "http://192.168.1.99:8085/app/VzBot.apk") })
    prova("richiesta: altra porta rifiutata", rifiuta("solo dal Raspberry") { richiesta(percorso = "http://192.168.1.17:9999/app/VzBot.apk") })
    prova("richiesta: https al posto di http rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "https://192.168.1.17:8085/app/VzBot.apk") })
    prova("richiesta: altro file rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "/app/altro.apk") })
    prova("richiesta: percorso con ../ rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "/app/../api/health") })
    prova("richiesta: parametri in coda rifiutati", rifiuta("solo dal Raspberry") { richiesta(percorso = "/app/VzBot.apk?x=1") })
    prova("richiesta: file: rifiutato", rifiuta("") { richiesta(percorso = "file:///sdcard/x.apk") })
    prova("richiesta: percorso vuoto o assente rifiutato", rifiuta("solo dal Raspberry") { richiesta(percorso = "") } && rifiuta("solo dal Raspberry") { richiesta(percorso = null) })
    prova("richiesta: versione non valida", rifiuta("versione") { richiesta(versione = "boh") } && rifiuta("versione") { richiesta(versione = null) })
    prova("richiesta: versione uguale a quella installata", rifiuta("già aggiornata") { richiesta(versione = "1.0.0") })
    prova("richiesta: versione piu' vecchia", rifiuta("già aggiornata") { richiesta(versione = "0.9.9") })
    prova("richiesta: manca l'impronta", rifiuta("impronta") { richiesta(impronta = null) } && rifiuta("impronta") { richiesta(impronta = "123") })
    prova("richiesta: grandezza 0, negativa o enorme", rifiuta("grandezza") { richiesta(grandezza = 0) } && rifiuta("grandezza") { richiesta(grandezza = -5) } && rifiuta("grandezza") { richiesta(grandezza = 151L * 1024 * 1024) })

    // ---- scaricamento, contro un Brain finto ----
    val apk = ByteArray(300_000) { ((it * 31 + 7) % 251).toByte() }
    val apkSha = sha(apk)
    val colpi = AtomicInteger()
    val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
    fun rispondi(e: HttpExchange, codice: Int, corpo: ByteArray) {
        e.responseHeaders.add("Content-Type", "application/vnd.android.package-archive")
        e.sendResponseHeaders(codice, corpo.size.toLong())
        e.responseBody.use { it.write(corpo) }
    }
    server.createContext("/app/VzBot.apk") { e -> colpi.incrementAndGet(); rispondi(e, 200, apk) }
    server.createContext("/mancante/app") { e -> colpi.incrementAndGet(); rispondi(e, 404, "no".toByteArray()) }
    server.createContext("/rotto/app") { e -> colpi.incrementAndGet(); rispondi(e, 500, "no".toByteArray()) }
    server.createContext("/rovinato/app") { e -> colpi.incrementAndGet(); rispondi(e, 200, apk.copyOf().also { it[1234] = (it[1234] + 1).toByte() }) }
    server.createContext("/piccolo/app") { e -> colpi.incrementAndGet(); rispondi(e, 200, apk.copyOf(1000)) }
    server.createContext("/troncato/app") { e ->
        // annuncia tutto il file ma chiude a meta': il collegamento si interrompe
        colpi.incrementAndGet()
        e.sendResponseHeaders(200, apk.size.toLong())
        e.responseBody.write(apk, 0, 100_000)
        e.responseBody.flush()
        e.close()
    }
    server.createContext("/lungo/app") { e ->
        // senza Content-Length (a pezzi) e piu' grande di quanto annunciato dal Brain
        colpi.incrementAndGet()
        e.sendResponseHeaders(200, 0)
        e.responseBody.use { it.write(apk + ByteArray(5000)) }
    }
    server.start()
    val porta = server.address.port
    val cartella = Files.createTempDirectory("aggiornamento-prova").toFile()
    fun r(percorso: String, grandezza: Long = apk.size.toLong(), impronta: String = apkSha) =
        Aggiornamento.Richiesta(URL("http://127.0.0.1:$porta$percorso"), "1.0.1", 10001, impronta, grandezza)
    fun tracce() = cartella.listFiles()?.map { it.name }?.sorted() ?: emptyList()

    try {
        val passi = mutableListOf<Long>()
        val file = Aggiornamento.scarica(r("/app/VzBot.apk"), cartella) { passi += it }
        prova("scarico: il file e' identico", file.isFile && file.readBytes().contentEquals(apk) && file.name == "VzBot-1.0.1.apk")
        prova("scarico: l'avanzamento sale fino alla grandezza", passi.isNotEmpty() && passi.zipWithNext().all { (a, b) -> a <= b } && passi.last() == apk.size.toLong())
        prova("scarico: nella cartella resta solo il file finito", tracce() == listOf("VzBot-1.0.1.apk"), tracce().toString())
        prova("scarico: sha256(file) e' quella giusta", Aggiornamento.sha256(file) == apkSha)

        val prima = colpi.get()
        val passi2 = mutableListOf<Long>()
        val ancora = Aggiornamento.scarica(r("/app/VzBot.apk"), cartella) { passi2 += it }
        prova("scarico ripetuto: riusa il file gia' scaricato senza richiederlo", colpi.get() == prima && ancora.readBytes().contentEquals(apk) && passi2 == listOf(apk.size.toLong()))

        // un file vecchio (o rovinato) nella cartella non si riusa e non resta
        File(cartella, "VzBot-0.9.0.apk").writeBytes(ByteArray(10))
        file.writeBytes(apk.copyOf(1000)) // il file giusto e' rovinato
        val rifatto = Aggiornamento.scarica(r("/app/VzBot.apk"), cartella) { }
        prova("scarico: un file rovinato nella cartella viene scaricato di nuovo, i vecchi spariscono", rifatto.readBytes().contentEquals(apk) && tracce() == listOf("VzBot-1.0.1.apk"), tracce().toString())

        fun fallisce(parola: String, richiesta: Aggiornamento.Richiesta): Boolean {
            Aggiornamento.pulisci(cartella) // senza un file gia' scaricato che farebbe da cache
            val esito = rifiuta(parola) { Aggiornamento.scarica(richiesta, cartella) { } }
            return esito && tracce().none { it.endsWith(".parte") || it.endsWith(".apk") }
        }
        prova("errore: 404 (il Raspberry non ha l'APK)", fallisce("non ha l'APK", r("/mancante/app")))
        prova("errore: 500", fallisce("500", r("/rotto/app")))
        prova("errore: file rovinato (impronta diversa)", fallisce("rovinato", r("/rovinato/app")))
        prova("errore: il file e' piu' piccolo di quello annunciato dal Brain", fallisce("non è quello annunciato", r("/piccolo/app")))
        prova("errore: il collegamento cade a meta'", fallisce("", r("/troncato/app")))
        prova("errore: piu' grande del previsto (senza lunghezza annunciata)", fallisce("più grande", r("/lungo/app")))
        prova("errore: grandezza annunciata dalla pagina diversa dal file", fallisce("non è quello annunciato", r("/app/VzBot.apk", grandezza = apk.size + 10L)))
        prova("errore: impronta annunciata sbagliata", fallisce("rovinato", r("/app/VzBot.apk", impronta = "0".repeat(64))))
        prova("errore: server che non c'e'", try {
            Aggiornamento.scarica(Aggiornamento.Richiesta(URL("http://127.0.0.1:1/app/VzBot.apk"), "1.0.1", 10001, apkSha, apk.size.toLong()), cartella) { }
            false
        } catch (e: IOException) {
            true
        })

        // pulisci
        File(cartella, "a.apk").writeBytes(ByteArray(1)).also { File(cartella, "a.apk").setLastModified(System.currentTimeMillis() - 3_600_000) }
        File(cartella, "b.apk").writeBytes(ByteArray(1))
        Aggiornamento.pulisci(cartella, 600_000)
        prova("pulisci: toglie solo i file piu' vecchi del limite", !File(cartella, "a.apk").exists() && File(cartella, "b.apk").exists())
        Aggiornamento.pulisci(cartella)
        prova("pulisci: senza limite toglie tutto", tracce().isEmpty())
        Aggiornamento.pulisci(File(cartella, "non-esiste"))
        prova("pulisci: cartella che non c'e' non da' errore", true)
        val nuova = File(cartella, "sotto/cartella")
        val creato = Aggiornamento.scarica(r("/app/VzBot.apk"), nuova) { }
        prova("scarico: crea la cartella se manca", creato.isFile && nuova.isDirectory)
    } finally {
        server.stop(0)
        cartella.deleteRecursively()
    }

    // ---- risposta del ponte ----
    prova("comeJson", Aggiornamento.comeJson("1.0.0", 10000, true) == "{\"version\":\"1.0.0\",\"code\":10000,\"canInstall\":true}")
    prova("comeJson: toglie i caratteri strani dal nome", Aggiornamento.comeJson("1.0\"}<x>", 5, false) == "{\"version\":\"1.0x\",\"code\":5,\"canInstall\":false}", Aggiornamento.comeJson("1.0\"}<x>", 5, false))

    println(if (errori == 0) "ALL PASS" else "FAILS: $errori")
    if (errori != 0) System.exit(1)
}
