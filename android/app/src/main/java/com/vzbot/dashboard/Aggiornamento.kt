package com.vzbot.dashboard

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * L'aggiornamento dell'app da dentro l'app. Il Raspberry tiene l'ultimo APK (cartella apk/ del repository, lo costruisce
 * GitHub) e lo offre su /app/VzBot.apk; la dashboard (Impostazioni > Aggiornamenti > App Android) dice all'app di
 * scaricarlo con `VzBotApp.updateApp(...)` e l'app lo passa all'installazione di Android.
 *
 * Prima di installare qualcosa l'app controlla:
 *  - che l'indirizzo sia quello del Brain a cui e' collegata, col percorso fisso [PERCORSO_APK] (niente altri siti, niente altri file);
 *  - che la versione sia piu' nuova di quella installata;
 *  - che il file scaricato abbia la grandezza e l'impronta SHA-256 annunciate dal Brain (un file rovinato o a meta' si butta);
 *  e Android, da parte sua, installa solo un APK firmato con la STESSA chiave dell'app attuale e chiede sempre conferma.
 *
 * Qui non c'e' niente di Android (solo Java): si prova da sola, vedi tools/AggiornamentoTest.kt. Quello che parla con il
 * sistema (versione installata, permesso, installazione) sta in AggiornamentoAndroid.kt.
 */
object Aggiornamento {
    /** L'unico percorso da cui l'app accetta il proprio aggiornamento. */
    const val PERCORSO_APK = "/app/VzBot.apk"
    const val TIPO_APK = "application/vnd.android.package-archive"

    private const val GRANDEZZA_MASSIMA = 150L * 1024 * 1024
    private const val ATTESA_COLLEGAMENTO_MS = 5000
    private const val ATTESA_DATI_MS = 30000
    private val FORMATO_VERSIONE = Regex("""^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$""")
    private val FORMATO_IMPRONTA = Regex("[0-9a-f]{64}")

    /** Cosa chiede la pagina, gia' controllato: dove scaricare, che versione e' e come riconoscere il file giusto. */
    class Richiesta(val url: URL, val versione: String, val codice: Int, val sha256: String, val grandezza: Long)

    /** "1.2.3" diventa 10203 (stessa formula di app/build.gradle); null se non sono tre numeri da 0 a 99. */
    fun codiceVersione(nome: String?): Int? {
        val trovato = FORMATO_VERSIONE.matchEntire(nome?.trim() ?: "") ?: return null
        val (maggiore, minore, correzione) = trovato.destructured
        return maggiore.toInt() * 10000 + minore.toInt() * 100 + correzione.toInt()
    }

    /** L'impronta in minuscolo se sono 64 cifre esadecimali, altrimenti null. */
    fun improntaValida(testo: String?): String? {
        val pulito = testo?.trim()?.lowercase() ?: return null
        return if (FORMATO_IMPRONTA.matches(pulito)) pulito else null
    }

    private fun inEsadecimale(byte: ByteArray): String = byte.joinToString("") { "%02x".format(it) }

    fun sha256(file: File): String {
        val calcolo = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { dentro ->
            val blocco = ByteArray(64 * 1024)
            while (true) {
                val letti = dentro.read(blocco)
                if (letti < 0) break
                calcolo.update(blocco, 0, letti)
            }
        }
        return inEsadecimale(calcolo.digest())
    }

    /**
     * Controlla quello che arriva dalla pagina. `base` e' l'indirizzo della dashboard caricata; `codiceInstallato` la versione
     * di questa app. Se qualcosa non va lancia un [IOException] con il motivo, scritto per l'utente.
     */
    fun controllaRichiesta(base: URL, percorso: String?, versione: String?, sha256: String?, grandezza: Long, codiceInstallato: Int): Richiesta {
        val url = try {
            URL(base, percorso ?: "")
        } catch (e: Exception) {
            throw IOException("indirizzo dell'aggiornamento non valido")
        }
        val stessoServer = url.protocol == base.protocol && url.host == base.host && url.port == base.port
        if (!stessoServer || url.path != PERCORSO_APK || !url.query.isNullOrEmpty()) {
            throw IOException("l'app scarica aggiornamenti solo dal Raspberry a cui è collegata")
        }
        val codice = codiceVersione(versione) ?: throw IOException("numero di versione non valido")
        if (codice <= codiceInstallato) throw IOException("l'app è già aggiornata")
        val impronta = improntaValida(sha256) ?: throw IOException("manca l'impronta del file: ricontrolla gli aggiornamenti")
        if (grandezza <= 0 || grandezza > GRANDEZZA_MASSIMA) throw IOException("grandezza del file non valida")
        return Richiesta(url, versione!!.trim(), codice, impronta, grandezza)
    }

    /** Toglie dalla cartella i file piu' vecchi di `piuVecchiDiMs` (0 = tutti). Un file ancora in uso dall'installazione resta. */
    fun pulisci(cartella: File, piuVecchiDiMs: Long = 0) {
        val limite = System.currentTimeMillis() - piuVecchiDiMs
        cartella.listFiles()?.forEach { if (it.isFile && it.lastModified() <= limite) it.delete() }
    }

    /**
     * Scarica l'APK in `cartella` e lo controlla; `avanzamento` riceve i byte scaricati finora. Restituisce il file pronto.
     * Se un file identico e' gia' stato scaricato (per esempio mentre si concedeva il permesso) lo riusa. In caso di errore
     * non lascia niente a meta'.
     */
    fun scarica(richiesta: Richiesta, cartella: File, avanzamento: (Long) -> Unit): File {
        if (!cartella.isDirectory && !cartella.mkdirs()) throw IOException("la memoria del telefono non è disponibile")
        val finale = File(cartella, "VzBot-${richiesta.versione}.apk")
        if (finale.isFile && finale.length() == richiesta.grandezza && sha256(finale) == richiesta.sha256) {
            avanzamento(richiesta.grandezza)
            return finale
        }
        pulisci(cartella)
        val parziale = File(cartella, finale.name + ".parte")
        val collegamento = richiesta.url.openConnection() as HttpURLConnection
        collegamento.connectTimeout = ATTESA_COLLEGAMENTO_MS
        collegamento.readTimeout = ATTESA_DATI_MS
        try {
            val risposta = collegamento.responseCode
            if (risposta == 404) throw IOException("il Raspberry non ha l'APK: aggiorna prima VzBot e ricontrolla")
            if (risposta != 200) throw IOException("il Raspberry ha risposto $risposta")
            val annunciata = collegamento.contentLengthLong
            if (annunciata >= 0 && annunciata != richiesta.grandezza) {
                throw IOException("il file sul Raspberry non è quello annunciato: ricontrolla gli aggiornamenti")
            }
            val calcolo = MessageDigest.getInstance("SHA-256")
            var scaricati = 0L
            collegamento.inputStream.use { dentro ->
                FileOutputStream(parziale).use { fuori ->
                    val blocco = ByteArray(32 * 1024)
                    while (true) {
                        val letti = dentro.read(blocco)
                        if (letti < 0) break
                        scaricati += letti
                        if (scaricati > richiesta.grandezza) throw IOException("il file è più grande del previsto")
                        fuori.write(blocco, 0, letti)
                        calcolo.update(blocco, 0, letti)
                        avanzamento(scaricati)
                    }
                }
            }
            if (scaricati != richiesta.grandezza) throw IOException("scaricamento interrotto: arrivati $scaricati byte su ${richiesta.grandezza}")
            if (inEsadecimale(calcolo.digest()) != richiesta.sha256) throw IOException("il file scaricato è rovinato (impronta diversa): riprova")
            if (!parziale.renameTo(finale)) throw IOException("impossibile salvare il file nella memoria del telefono")
            return finale
        } catch (e: Exception) {
            parziale.delete()
            throw e
        } finally {
            collegamento.disconnect()
        }
    }

    /** Cosa risponde `VzBotApp.appInfo()`: {"version":"1.0.0","code":10000,"canInstall":true}. */
    fun comeJson(versione: String, codice: Int, puoInstallare: Boolean): String {
        val pulita = versione.replace(Regex("[^0-9A-Za-z._+-]"), "")
        return "{\"version\":\"$pulita\",\"code\":$codice,\"canInstall\":$puoInstallare}"
    }
}
