#!/usr/bin/env python3
"""
I passi "furbi" del workflow .github/workflows/app.yml, che costruisce l'APK dell'app Android sul computer di GitHub.
Sono qui (e non scritti dentro il file del workflow) per poterli provare da soli (senza GitHub).

    app_ci.py decidi      deve costruire un APK nuovo? (confronta android/VERSION con apk/versione.json)
    app_ci.py chiave      la chiave che firma l'APK: la crea la prima volta, poi controlla che la password sia quella giusta
    app_ci.py google      scrive app/google-services.json (le notifiche) dal segreto GOOGLE_SERVICES_JSON, se c'e'
    app_ci.py pubblica    controlla l'APK costruito e lo mette in apk/ con apk/versione.json
    app_ci.py salva       fa il commit di quello che e' cambiato e lo spedisce su GitHub

Solo libreria standard di Python. Dentro GitHub gli errori diventano annotazioni rosse ("::error::") con il motivo scritto
per una persona, non per un programmatore; le uscite per i passi dopo vanno in $GITHUB_OUTPUT.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

PACCHETTO = "com.klippeye.app"
ALIAS_CHIAVE = "klippeye"
FORMATO_VERSIONE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")
PASSWORD_MINIMA = 16
APK_DI_COSTRUZIONE = os.path.join("android", "app", "build", "outputs", "apk", "release", "app-release.apk")


class Errore(Exception):
    """Un problema che l'utente puo' risolvere: il messaggio e' per lui."""


def percorsi(radice):
    return {
        "radice": radice,
        "versione_app": os.path.join(radice, "android", "VERSION"),
        "chiave": os.path.join(radice, "android", "chiave", "klippeye.p12"),
        "google": os.path.join(radice, "android", "app", "google-services.json"),
        "apk": os.path.join(radice, "apk", "KlippEye.apk"),
        "info": os.path.join(radice, "apk", "versione.json"),
    }


def codice_versione(testo):
    """1.2.3 -> 10203 (la stessa formula di android/app/build.gradle e di Aggiornamento.kt); None se il formato non va."""
    trovato = FORMATO_VERSIONE.match((testo or "").strip())
    if not trovato:
        return None
    maggiore, minore, correzione = (int(x) for x in trovato.groups())
    return maggiore * 10000 + minore * 100 + correzione


def leggi_versione(p):
    try:
        with open(p["versione_app"], encoding="utf-8") as f:
            testo = f.read().strip()
    except OSError:
        raise Errore("Manca il file android/VERSION (dentro c'è scritto il numero della versione, per esempio 1.0.0).")
    codice = codice_versione(testo)
    if codice is None:
        raise Errore("android/VERSION deve contenere tre numeri da 0 a 99 separati da punti (per esempio 1.0.1): trovato «%s»." % testo[:40])
    return testo, codice


def leggi_pubblicata(p):
    """Il contenuto valido di apk/versione.json, oppure None (manca, e' rovinato o l'APK non c'e')."""
    try:
        with open(p["info"], encoding="utf-8") as f:
            dati = json.load(f)
        if not isinstance(dati, dict) or codice_versione(dati.get("version")) is None:
            return None
        if not os.path.isfile(p["apk"]):
            return None
        return dati
    except (OSError, ValueError):
        return None


def sha256_file(percorso):
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blocco)
    return h.hexdigest()


def scrivi_uscite(**valori):
    """Per i passi seguenti del workflow ($GITHUB_OUTPUT); fuori da GitHub le stampa soltanto."""
    riga = "".join("%s=%s\n" % (k, v) for k, v in valori.items())
    destinazione = os.environ.get("GITHUB_OUTPUT")
    if destinazione:
        with open(destinazione, "a", encoding="utf-8") as f:
            f.write(riga)
    print(riga, end="")


# ---------------------------------------------------------------------------------------------------- decidi
def decidi(p, forza=False, evento="", password=""):
    """
    Costruire o no? `evento` e' quello che ha avviato il workflow ("push" o "workflow_dispatch"). Un caricamento di file senza la
    password della chiave non e' un errore (e' il primo caricamento: il segreto si crea dopo): non si costruisce e lo si dice.
    Un avvio a mano senza password, invece, e' un errore: lo ha chiesto una persona.
    """
    esito = _decidi(p, forza)
    if esito["build"] == "true" and evento == "push" and not password:
        return dict(build="false", version=esito["version"], code=esito["code"],
                    motivo="manca il segreto KLIPPEYE_CHIAVE_PASSWORD: crealo (docs/GUIDA.md, parte C1) e poi avvia a mano il workflow «App Android»")
    return esito


def _decidi(p, forza):
    versione, codice = leggi_versione(p)
    pubblicata = leggi_pubblicata(p)
    if pubblicata is None:
        return dict(build="true", version=versione, code=codice, motivo="nessuna app pubblicata finora")
    vecchia = pubblicata["version"]
    codice_vecchio = codice_versione(vecchia)
    if codice < codice_vecchio:
        raise Errore("In android/VERSION c'è la %s ma l'app già pubblicata è la %s: Android non installa mai una versione più vecchia sopra una più nuova. "
                     "Scrivi un numero più alto di %s." % (versione, vecchia, vecchia))
    if codice > codice_vecchio:
        return dict(build="true", version=versione, code=codice, motivo="nuova versione: %s al posto della %s" % (versione, vecchia))
    if forza:
        return dict(build="true", version=versione, code=codice, motivo="ricostruzione voluta della %s" % versione)
    return dict(build="false", version=versione, code=codice, motivo="la %s è già pubblicata: per una nuova app alza il numero in android/VERSION" % versione)


# ---------------------------------------------------------------------------------------------------- chiave
def keytool(argomenti, password):
    ambiente = dict(os.environ, KLIPPEYE_KEYSTORE_PASSWORD=password)
    return subprocess.run(["keytool"] + argomenti, capture_output=True, text=True, env=ambiente)


def controlla_password(password):
    if not password:
        raise Errore("Manca il segreto KLIPPEYE_CHIAVE_PASSWORD: in GitHub vai su Settings → Secrets and variables → Actions → New repository secret, "
                     "chiamalo KLIPPEYE_CHIAVE_PASSWORD e come valore scrivi una frase lunga (vedi docs/GUIDA.md, «L'app Android»).")
    if "\n" in password or "\r" in password:
        raise Errore("La password nel segreto KLIPPEYE_CHIAVE_PASSWORD ha un «a capo»: rimettila su una riga sola.")
    if len(password) < PASSWORD_MINIMA:
        raise Errore("La password nel segreto KLIPPEYE_CHIAVE_PASSWORD è troppo corta (%d caratteri): ne servono almeno %d, perché la chiave sta nel repository "
                     "e solo la password la protegge. Una frase di quattro o cinque parole va bene." % (len(password), PASSWORD_MINIMA))


def chiave(p, password):
    """Crea la chiave di firma se manca; se c'e' controlla che la password la apra. Restituisce 'creata' o 'esistente'."""
    controlla_password(password)
    file_chiave = p["chiave"]
    if os.path.isfile(file_chiave):
        r = keytool(["-list", "-keystore", file_chiave, "-storetype", "PKCS12", "-storepass:env", "KLIPPEYE_KEYSTORE_PASSWORD", "-alias", ALIAS_CHIAVE], password)
        if r.returncode != 0:
            raise Errore("La password nel segreto KLIPPEYE_CHIAVE_PASSWORD non apre la chiave android/chiave/klippeye.p12. Se l'hai cambiata rimetti quella di prima. "
                         "Se l'hai persa, cancella android/chiave/klippeye.p12 da GitHub: ne verrà creata una nuova, ma le app già installate non potranno più "
                         "aggiornarsi sopra (vanno disinstallate e reinstallate una volta) e serve «nuova_chiave» nell'avvio manuale.")
        return "esistente"
    os.makedirs(os.path.dirname(file_chiave), exist_ok=True)
    r = keytool([
        "-genkeypair", "-keystore", file_chiave, "-storetype", "PKCS12", "-alias", ALIAS_CHIAVE,
        "-keyalg", "RSA", "-keysize", "4096", "-validity", "36500", "-dname", "CN=KlippEye, O=KlippEye",
        "-storepass:env", "KLIPPEYE_KEYSTORE_PASSWORD", "-keypass:env", "KLIPPEYE_KEYSTORE_PASSWORD",
    ], password)
    if r.returncode != 0 or not os.path.isfile(file_chiave):
        raise Errore("Non sono riuscito a creare la chiave di firma: %s" % (r.stderr.strip() or r.stdout.strip() or "errore sconosciuto"))
    return "creata"


# ---------------------------------------------------------------------------------------------------- google
def google(p, contenuto):
    """Scrive google-services.json dal segreto. Restituisce True se l'ha scritto, False se non c'era (app senza notifiche)."""
    contenuto = (contenuto or "").strip()
    if not contenuto:
        return False
    try:
        dati = json.loads(contenuto)
        clienti = dati["client"]
        pacchetti = [c["client_info"]["android_client_info"]["package_name"] for c in clienti]
    except (ValueError, KeyError, TypeError):
        raise Errore("Il segreto GOOGLE_SERVICES_JSON non è un file google-services.json: incolla tutto il contenuto del file scaricato da Firebase, dalla prima all'ultima graffa.")
    if PACCHETTO not in pacchetti:
        raise Errore("Il google-services.json nel segreto GOOGLE_SERVICES_JSON è di un'altra app (%s): in Firebase aggiungi un'app Android chiamata %s, scarica il nuovo google-services.json e incolla il suo contenuto nel segreto GOOGLE_SERVICES_JSON."
                     % (", ".join(pacchetti) or "nessuna", PACCHETTO))
    with open(p["google"], "w", encoding="utf-8") as f:
        f.write(contenuto + "\n")
    return True


# ---------------------------------------------------------------------------------------------------- pubblica
def trova_strumento(nome, cartelle_extra=()):
    """aapt2 / apksigner: nelle build-tools dell'SDK Android (la versione piu' alta), poi nel PATH."""
    candidati = list(cartelle_extra)
    for variabile in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        radice = os.environ.get(variabile)
        if radice and os.path.isdir(os.path.join(radice, "build-tools")):
            versioni = sorted(os.listdir(os.path.join(radice, "build-tools")), key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v)], reverse=True)
            candidati += [os.path.join(radice, "build-tools", v) for v in versioni]
    for cartella in candidati:
        percorso = os.path.join(cartella, nome)
        if os.path.isfile(percorso) and os.access(percorso, os.X_OK):
            return percorso
    trovato = shutil.which(nome)
    if trovato:
        return trovato
    raise Errore("Non trovo «%s» nell'SDK Android del computer di GitHub." % nome)


def leggi_dati_apk(apk, aapt2):
    r = subprocess.run([aapt2, "dump", "badging", apk], capture_output=True, text=True)
    trovato = re.search(r"package: name='([^']*)' versionCode='(\d+)' versionName='([^']*)'", r.stdout)
    if r.returncode != 0 or not trovato:
        raise Errore("L'APK costruito non si riesce a leggere (aapt2: %s)." % (r.stderr.strip()[:200] or "nessuna risposta"))
    return trovato.group(1), int(trovato.group(2)), trovato.group(3)


def leggi_firma(apk, apksigner):
    """L'impronta SHA-256 del certificato che ha firmato l'APK (e controlla che la firma sia valida)."""
    r = subprocess.run([apksigner, "verify", "--print-certs", apk], capture_output=True, text=True)
    trovato = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]{64})", r.stdout)
    if r.returncode != 0 or not trovato:
        raise Errore("L'APK costruito non è firmato bene (apksigner: %s)." % ((r.stderr or r.stdout).strip()[:300] or "nessuna risposta"))
    return trovato.group(1).lower()


def pubblica(p, apk, aapt2, apksigner, ammetti_nuova_firma=False, sorgente="", adesso=None):
    versione, codice = leggi_versione(p)
    if not os.path.isfile(apk) or os.path.getsize(apk) < 100 * 1024:
        raise Errore("La costruzione dell'APK non ha prodotto il file (%s)." % os.path.basename(apk))
    try:
        with zipfile.ZipFile(apk) as z:
            nomi = set(z.namelist())
    except zipfile.BadZipFile:
        raise Errore("Il file costruito non è un APK valido.")
    if "AndroidManifest.xml" not in nomi or not any(n.endswith(".dex") for n in nomi):
        raise Errore("Il file costruito non è un APK valido (manca il manifest o il codice).")
    pacchetto, codice_apk, versione_apk = leggi_dati_apk(apk, aapt2)
    if pacchetto != PACCHETTO or codice_apk != codice or versione_apk != versione:
        raise Errore("L'APK costruito dice «%s %s (%d)» ma android/VERSION dice «%s %s (%d)»." % (pacchetto, versione_apk, codice_apk, PACCHETTO, versione, codice))
    firma = leggi_firma(apk, apksigner)
    precedente = leggi_pubblicata(p)
    if precedente and precedente.get("firma") and precedente["firma"] != firma and not ammetti_nuova_firma:
        raise Errore("Questo APK è firmato con una chiave DIVERSA da quella dell'app pubblicata prima: i telefoni che hanno già l'app non potrebbero "
                     "aggiornarsi (Android rifiuta) e andrebbero disinstallati e reinstallati. Se è proprio quello che vuoi, rilancia il workflow a mano "
                     "spuntando «nuova_chiave». Altrimenti rimetti la chiave e la password di prima.")
    os.makedirs(os.path.dirname(p["apk"]), exist_ok=True)
    temporaneo = p["apk"] + ".parte"
    shutil.copyfile(apk, temporaneo)
    os.replace(temporaneo, p["apk"])
    quando = (adesso or datetime.datetime.now(datetime.timezone.utc)).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    info = {
        "version": versione,
        "code": codice,
        "size": os.path.getsize(p["apk"]),
        "sha256": sha256_file(p["apk"]),
        "firma": firma,
        "built": quando,
        "source": sorgente[:12],
    }
    with open(p["info"] + ".parte", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(p["info"] + ".parte", p["info"])
    return info


# ---------------------------------------------------------------------------------------------------- salva
def git(radice, *argomenti, controlla=True):
    r = subprocess.run(["git", "-C", radice] + list(argomenti), capture_output=True, text=True)
    if controlla and r.returncode != 0:
        raise Errore("git %s: %s" % (" ".join(argomenti[:2]), (r.stderr or r.stdout).strip()[:300]))
    return r


def salva(radice, ramo, messaggio, cartelle, tentativi=4, utente=("KlippEye (GitHub Actions)", "actions@users.noreply.github.com")):
    """
    Commit di `cartelle` (le sole cose che il workflow cambia) e push. Se nel frattempo qualcuno ha spedito altro, il push viene
    rifiutato: allora si riparte dall'ultimo stato di GitHub e si rimette sopra lo stesso contenuto (niente rebase, che su una copia
    "corta" fatta da actions/checkout puo' fallire). Restituisce True se ha spedito qualcosa, False se non c'era niente da spedire.
    """
    git(radice, "config", "user.name", utente[0])
    git(radice, "config", "user.email", utente[1])
    esistenti = [c for c in cartelle if os.path.exists(os.path.join(radice, c))]
    git(radice, "add", "-A", "--", *esistenti)
    if git(radice, "diff", "--cached", "--quiet", controlla=False).returncode == 0:
        return False
    git(radice, "commit", "-q", "-m", messaggio)
    ultimo = ""
    for tentativo in range(tentativi):
        r = git(radice, "push", "origin", "HEAD:refs/heads/" + ramo, controlla=False)
        if r.returncode == 0:
            return True
        ultimo = (r.stderr or r.stdout).strip()[:300]
        # Rifatto sopra l'ultimo stato di GitHub: si salvano i file, si riparte dalla punta del ramo e si rimettono
        copia = tempfile.mkdtemp(prefix="salva-")
        try:
            for c in esistenti:
                sorgente = os.path.join(radice, c)
                if os.path.isdir(sorgente):
                    shutil.copytree(sorgente, os.path.join(copia, c))
                elif os.path.isfile(sorgente):
                    os.makedirs(os.path.dirname(os.path.join(copia, c)), exist_ok=True)
                    shutil.copy2(sorgente, os.path.join(copia, c))
            git(radice, "fetch", "-q", "--depth=1", "origin", ramo)
            git(radice, "reset", "-q", "--hard", "FETCH_HEAD")
            for c in esistenti:
                destinazione = os.path.join(radice, c)
                if os.path.isdir(destinazione):
                    shutil.rmtree(destinazione)
                if os.path.isdir(os.path.join(copia, c)):
                    shutil.copytree(os.path.join(copia, c), destinazione)
                elif os.path.isfile(os.path.join(copia, c)):
                    os.makedirs(os.path.dirname(destinazione), exist_ok=True)
                    shutil.copy2(os.path.join(copia, c), destinazione)
            git(radice, "add", "-A", "--", *esistenti)
            if git(radice, "diff", "--cached", "--quiet", controlla=False).returncode == 0:
                return False
            git(radice, "commit", "-q", "-m", messaggio)
        finally:
            shutil.rmtree(copia, ignore_errors=True)
    raise Errore("Non riesco a salvare l'APK su GitHub dopo %d tentativi: %s" % (tentativi, ultimo))


# ---------------------------------------------------------------------------------------------------- riga di comando
def radice_di_default():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--radice", default=radice_di_default(), help="la cartella del repository")
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("decidi")
    s.add_argument("--forza", default="false")
    s.add_argument("--evento", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    sub.add_parser("chiave")
    sub.add_parser("google")
    s = sub.add_parser("pubblica")
    s.add_argument("--apk", default=None)
    s.add_argument("--nuova-chiave", default="false")
    s.add_argument("--sorgente", default=os.environ.get("GITHUB_SHA", ""))
    s = sub.add_parser("salva")
    s.add_argument("--ramo", required=True)
    s.add_argument("--messaggio", required=True)
    args = parser.parse_args(argv)
    p = percorsi(os.path.abspath(args.radice))
    vero = lambda testo: str(testo).strip().lower() in ("1", "true", "si", "sì", "yes")

    try:
        if args.comando == "decidi":
            esito = decidi(p, vero(args.forza), args.evento, os.environ.get("KLIPPEYE_KEYSTORE_PASSWORD", ""))
            scrivi_uscite(**esito)
            if esito["build"] == "false":
                livello = "warning" if "manca il segreto" in esito["motivo"] else "notice"
                print("::%s title=App non costruita::%s" % (livello, esito["motivo"]))
        elif args.comando == "chiave":
            esito = chiave(p, os.environ.get("KLIPPEYE_KEYSTORE_PASSWORD", ""))
            print("Chiave di firma: %s (android/chiave/klippeye.p12)" % esito)
            scrivi_uscite(chiave=esito)
        elif args.comando == "google":
            if google(p, os.environ.get("GOOGLE_SERVICES_JSON", "")):
                print("Notifiche: google-services.json scritto, l'app avrà le notifiche.")
            else:
                print("::warning title=App senza notifiche::manca il segreto GOOGLE_SERVICES_JSON: l'app si costruisce lo stesso ma senza notifiche (vedi docs/GUIDA.md)")
        elif args.comando == "pubblica":
            apk = args.apk or os.path.join(p["radice"], APK_DI_COSTRUZIONE)
            info = pubblica(p, apk, trova_strumento("aapt2"), trova_strumento("apksigner"), vero(args.nuova_chiave), args.sorgente)
            print("Pubblicato apk/KlippEye.apk: versione %s, %d byte, sha256 %s" % (info["version"], info["size"], info["sha256"]))
        elif args.comando == "salva":
            spedito = salva(p["radice"], args.ramo, args.messaggio, ["apk", os.path.join("android", "chiave")])
            print("Salvato su GitHub." if spedito else "Niente di cambiato: non salvo niente.")
    except Errore as errore:
        print("::error title=App Android::%s" % str(errore).replace("\n", " "))
        print(str(errore), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
