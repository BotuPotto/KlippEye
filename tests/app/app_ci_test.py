"""Prova da sola di ci/app_ci.py (i passi del workflow dell'app): keytool vero, git vero, aapt2/apksigner finti."""
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository
spec = importlib.util.spec_from_file_location("app_ci", os.path.join(ROOT, "ci", "app_ci.py"))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

errori = 0


def prova(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(("PASS " if ok else "FAIL ") + nome + ("" if ok or not dettaglio else " :: " + str(dettaglio)))


def lancia_errore(funzione, parola=""):
    try:
        funzione()
    except ci.Errore as e:
        return parola.lower() in str(e).lower()
    return False


def repo(versione="1.0.0", pubblicata=None):
    radice = tempfile.mkdtemp(prefix="repo-")
    os.makedirs(radice + "/android")
    if versione is not None:
        open(radice + "/android/VERSION", "w").write(versione + "\n")
    if pubblicata:
        os.makedirs(radice + "/apk")
        open(radice + "/apk/KlippEye.apk", "wb").write(b"x" * 10)
        json.dump(pubblicata, open(radice + "/apk/version.json", "w"))
    return radice, ci.percorsi(radice)


# ---- codice versione: gli stessi valori provati in Gradle e in Kotlin ----
for testo, atteso in [("1.0.0", 10000), ("1.2.3", 10203), ("0.0.1", 1), ("99.99.99", 999999), (" 2.10.0 ", 21000), ("1.0", None), ("1.0.100", None), ("mk218", None), ("1.0.0-beta", None), ("", None), (None, None)]:
    prova("codice_versione(%r) = %s" % (testo, atteso), ci.codice_versione(testo) == atteso)

# ---- decidi ----
radice, p = repo("1.0.0")
r = ci.decidi(p)
prova("decidi: niente pubblicato -> costruisce", r["build"] == "true" and r["version"] == "1.0.0" and r["code"] == 10000)
radice, p = repo("1.0.0", {"version": "1.0.0"})
prova("decidi: stessa versione -> non costruisce", ci.decidi(p)["build"] == "false")
prova("decidi: stessa versione ma forzato -> costruisce", ci.decidi(p, forza=True)["build"] == "true")
radice, p = repo("1.0.1", {"version": "1.0.0"})
r = ci.decidi(p)
prova("decidi: versione piu' alta -> costruisce", r["build"] == "true" and "1.0.1" in r["motivo"] and "1.0.0" in r["motivo"])
radice, p = repo("1.0.0", {"version": "1.0.1"})
prova("decidi: versione piu' bassa -> errore chiaro", lancia_errore(lambda: ci.decidi(p), "più vecchia"))
prova("decidi: versione piu' bassa anche se forzato -> errore", lancia_errore(lambda: ci.decidi(p, forza=True), "più vecchia"))
radice, p = repo("1.0.0", {"version": "1.0.0"})
os.remove(radice + "/apk/KlippEye.apk")
prova("decidi: version.json c'e' ma l'APK no -> costruisce", ci.decidi(p)["build"] == "true")
radice, p = repo("1.0.0")
os.makedirs(radice + "/apk")
open(radice + "/apk/version.json", "w").write("{rotto")
open(radice + "/apk/KlippEye.apk", "wb").write(b"x")
prova("decidi: version.json rovinato -> costruisce", ci.decidi(p)["build"] == "true")
radice, p = repo("1.0.0")
r = ci.decidi(p, evento="push", password="")
prova("decidi: primo caricamento (push) senza password -> non costruisce e dice di creare il segreto", r["build"] == "false" and "KLIPPEYE_CHIAVE_PASSWORD" in r["motivo"] and "C1" in r["motivo"], r)
prova("decidi: push con la password -> costruisce", ci.decidi(p, evento="push", password="x" * 20)["build"] == "true")
prova("decidi: avvio a mano senza password -> costruisce (poi il passo 'chiave' dice cosa manca)", ci.decidi(p, evento="workflow_dispatch", password="")["build"] == "true")
radice, p = repo("1.0.0", {"version": "1.0.0"})
prova("decidi: push senza password ma versione gia' pubblicata -> motivo della versione, non del segreto", "già pubblicata" in ci.decidi(p, evento="push", password="")["motivo"])
radice, p = repo("0.9.0", {"version": "1.0.0"})
prova("decidi: push senza password con versione piu' bassa -> resta l'errore della versione", lancia_errore(lambda: ci.decidi(p, evento="push", password=""), "più vecchia"))
radice, p = repo("boh")
prova("decidi: android/VERSION non valido -> errore", lancia_errore(lambda: ci.decidi(p), "tre numeri"))
radice, p = repo(None)
prova("decidi: android/VERSION manca -> errore", lancia_errore(lambda: ci.decidi(p), "manca"))

# ---- chiave (keytool vero) ----
radice, p = repo()
buona = "una frase lunga e segreta 2026"
prova("chiave: password assente", lancia_errore(lambda: ci.chiave(p, ""), "KLIPPEYE_CHIAVE_PASSWORD"))
prova("chiave: password troppo corta", lancia_errore(lambda: ci.chiave(p, "corta123"), "troppo corta"))
prova("chiave: password con a capo", lancia_errore(lambda: ci.chiave(p, buona + "\n"), "a capo"))
prova("chiave: nessun file creato dagli errori", not os.path.exists(p["chiave"]))
prova("chiave: creata la prima volta", ci.chiave(p, buona) == "creata" and os.path.isfile(p["chiave"]))
elenco = subprocess.run(["keytool", "-list", "-v", "-keystore", p["chiave"], "-storepass", buona], capture_output=True, text=True).stdout
prova("chiave: alias klippeye, PKCS12, RSA 4096", "Alias name: klippeye" in elenco and "PKCS12" in elenco and "4096-bit RSA" in elenco, elenco[:400])
valida = [riga for riga in elenco.splitlines() if riga.startswith("Valid from")]
prova("chiave: valida per piu' di 90 anni", bool(valida) and int(valida[0].split("until:")[1].split()[-1]) - int(valida[0].split("Valid from:")[1].split("until")[0].split()[-1]) >= 90, valida)
prima = open(p["chiave"], "rb").read()
prova("chiave: la seconda volta e' quella di prima", ci.chiave(p, buona) == "esistente" and open(p["chiave"], "rb").read() == prima)
prova("chiave: password sbagliata -> errore con le istruzioni", lancia_errore(lambda: ci.chiave(p, "un'altra frase molto lunga"), "non apre la chiave"))
open(p["chiave"], "wb").write(b"non e' un keystore")
prova("chiave: file rovinato -> errore", lancia_errore(lambda: ci.chiave(p, buona), "non apre la chiave"))

# ---- google ----
radice, p = repo()
os.makedirs(radice + "/android/app")
prova("google: segreto assente -> False, nessun file", ci.google(p, "") is False and ci.google(p, None) is False and not os.path.exists(p["google"]))
prova("google: JSON rotto", lancia_errore(lambda: ci.google(p, "{boh"), "non è un file google-services.json"))
prova("google: JSON di altro tipo", lancia_errore(lambda: ci.google(p, '{"a":1}'), "non è un file google-services.json"))
altro = {"client": [{"client_info": {"android_client_info": {"package_name": "com.altra.app"}}}]}
prova("google: app di un'altro pacchetto", lancia_errore(lambda: ci.google(p, json.dumps(altro)), "com.altra.app"))
giusto = {"project_info": {"project_id": "x"}, "client": [{"client_info": {"android_client_info": {"package_name": "com.klippeye.app"}}}]}
prova("google: file giusto scritto", ci.google(p, "  " + json.dumps(giusto) + "\n") is True and json.load(open(p["google"])) == giusto)

# ---- strumenti ----
sdk = tempfile.mkdtemp(prefix="sdk-")
for versione in ("9.0.0", "33.0.1", "34.0.0", "34.0.0-rc1"):
    cartella = "%s/build-tools/%s" % (sdk, versione)
    os.makedirs(cartella)
    for nome in ("aapt2", "apksigner"):
        open("%s/%s" % (cartella, nome), "w").write("#!/bin/sh\necho %s\n" % versione)
        os.chmod("%s/%s" % (cartella, nome), 0o755)
os.environ["ANDROID_HOME"] = sdk
trovato = ci.trova_strumento("aapt2")
prova("strumenti: sceglie le build-tools piu' recenti", "/34.0.0/" in trovato or "/34.0.0-rc1/" in trovato, trovato)
prova("strumenti: uno che non c'e' -> errore", lancia_errore(lambda: ci.trova_strumento("non-esiste-xyz"), "non trovo"))
del os.environ["ANDROID_HOME"]

# ---- pubblica (aapt2 e apksigner finti, con l'uscita di quelli veri) ----
strumenti = tempfile.mkdtemp(prefix="strumenti-")


def finto(nome, corpo):
    percorso = strumenti + "/" + nome
    open(percorso, "w").write("#!/bin/bash\n" + corpo)
    os.chmod(percorso, 0o755)
    return percorso


def aapt2(pacchetto="com.klippeye.app", codice="10000", nome="1.0.0", esce=0):
    return finto("aapt2", "echo \"package: name='%s' versionCode='%s' versionName='%s' platformBuildVersionName='14' platformBuildVersionCode='34' compileSdkVersion='34'\"\nexit %d\n" % (pacchetto, codice, nome, esce))


def apksigner(impronta="ab" * 32, esce=0):
    return finto("apksigner", "echo 'Signer #1 certificate DN: CN=KlippEye, O=KlippEye'\necho 'Signer #1 certificate SHA-256 digest: %s'\necho 'Signer #1 certificate SHA-1 digest: 0000'\nexit %d\n" % (impronta, esce))


def fai_apk(percorso, manifest=True, dex=True, grande=True):
    with zipfile.ZipFile(percorso, "w", zipfile.ZIP_STORED) as z:
        if manifest:
            z.writestr("AndroidManifest.xml", b"m")
        if dex:
            z.writestr("classes.dex", b"d")
        if grande:
            z.writestr("resources.arsc", os.urandom(200 * 1024))
    return percorso


radice, p = repo("1.0.0")
apk = fai_apk(radice + "/costruito.apk")
info = ci.pubblica(p, apk, aapt2(), apksigner(), sorgente="0123456789abcdef0123", adesso=__import__("datetime").datetime(2026, 10, 22, 21, 15, 7, 999))
prova("pubblica: apk/KlippEye.apk identico", open(p["apk"], "rb").read() == open(apk, "rb").read())
dati = json.load(open(p["info"]))
import hashlib
prova("pubblica: version.json corretto",
      dati == {"version": "1.0.0", "code": 10000, "size": os.path.getsize(apk), "sha256": hashlib.sha256(open(apk, "rb").read()).hexdigest(), "firma": "ab" * 32, "built": "2026-10-22T21:15:07Z", "source": "0123456789ab"}, dati)
prova("pubblica: nessun file a meta' rimasto", sorted(os.listdir(radice + "/apk")) == ["KlippEye.apk", "version.json"], os.listdir(radice + "/apk"))
prova("pubblica: dopo, decidi dice 'gia' pubblicata'", ci.decidi(p)["build"] == "false")

# stessa versione ricostruita con la stessa firma: ok; con firma diversa: errore (a meno che non lo si voglia)
apk2 = fai_apk(radice + "/costruito2.apk")
ci.pubblica(p, apk2, aapt2(), apksigner())
prova("pubblica: stessa firma di prima -> ok", True)
prova("pubblica: firma diversa -> rifiutato", lancia_errore(lambda: ci.pubblica(p, apk2, aapt2(), apksigner("cd" * 32)), "chiave DIVERSA"))
prova("pubblica: firma diversa non ha toccato i file pubblicati", json.load(open(p["info"]))["firma"] == "ab" * 32)
nuova = ci.pubblica(p, apk2, aapt2(), apksigner("cd" * 32), ammetti_nuova_firma=True)
prova("pubblica: firma diversa voluta -> ok", nuova["firma"] == "cd" * 32)

radice, p = repo("1.0.0")
apk = fai_apk(radice + "/c.apk")
prova("pubblica: l'APK ha un'altra versione di android/VERSION", lancia_errore(lambda: ci.pubblica(p, apk, aapt2(codice="10001", nome="1.0.1"), apksigner()), "android/VERSION"))
prova("pubblica: l'APK e' di un altro pacchetto", lancia_errore(lambda: ci.pubblica(p, apk, aapt2(pacchetto="com.altro"), apksigner()), "com.altro"))
prova("pubblica: aapt2 non risponde", lancia_errore(lambda: ci.pubblica(p, apk, aapt2(esce=1), apksigner()), "leggere"))
prova("pubblica: firma non valida (apksigner fallisce)", lancia_errore(lambda: ci.pubblica(p, apk, aapt2(), apksigner(esce=1)), "non è firmato"))
prova("pubblica: file mancante", lancia_errore(lambda: ci.pubblica(p, radice + "/non-c-e.apk", aapt2(), apksigner()), "non ha prodotto"))
open(radice + "/zip.apk", "wb").write(os.urandom(200 * 1024))
prova("pubblica: non e' uno zip", lancia_errore(lambda: ci.pubblica(p, radice + "/zip.apk", aapt2(), apksigner()), "non è un apk valido"))
prova("pubblica: zip senza manifest", lancia_errore(lambda: ci.pubblica(p, fai_apk(radice + "/nm.apk", manifest=False), aapt2(), apksigner()), "manifest"))
prova("pubblica: zip senza codice", lancia_errore(lambda: ci.pubblica(p, fai_apk(radice + "/nd.apk", dex=False), aapt2(), apksigner()), "manifest o il codice"))
prova("pubblica: file troppo piccolo", lancia_errore(lambda: ci.pubblica(p, fai_apk(radice + "/pic.apk", grande=False), aapt2(), apksigner()), "non ha prodotto"))
prova("pubblica: niente e' stato pubblicato dagli errori", not os.path.exists(p["apk"]) and not os.path.exists(p["info"]))

# ---- salva (git vero, con un server finto in una cartella) ----
def git(*a, cwd=None):
    r = subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


base = tempfile.mkdtemp(prefix="git-")
remoto = base + "/remoto.git"
git("init", "-q", "--bare", "-b", "main", remoto)
semina = base + "/semina"
git("clone", "-q", remoto, semina)
git("config", "user.email", "a@b.c", cwd=semina)
git("config", "user.name", "Seme", cwd=semina)
os.makedirs(semina + "/android")
open(semina + "/android/VERSION", "w").write("1.0.0\n")
open(semina + "/README.md", "w").write("ciao\n")
git("add", "-A", cwd=semina)
git("commit", "-q", "-m", "inizio", cwd=semina)
git("push", "-q", "origin", "HEAD:main", cwd=semina)

url = "file://" + remoto
corta = base + "/corta"
git("clone", "-q", "--depth", "1", "-b", "main", url, corta)  # come fa actions/checkout
os.makedirs(corta + "/apk")
open(corta + "/apk/KlippEye.apk", "wb").write(b"A" * 1000)
open(corta + "/apk/version.json", "w").write('{"version":"1.0.0"}\n')
os.makedirs(corta + "/android/chiave")
open(corta + "/android/chiave/klippeye.p12", "wb").write(b"chiave")
prova("salva: spedisce apk/ e chiave", ci.salva(corta, "main", "App 1.0.0 [skip ci]", ["apk", "android/chiave"]) is True)
prova("salva: sul server ci sono i file", git("--git-dir", remoto, "show", "main:apk/KlippEye.apk") == "A" * 1000 and "chiave" in git("--git-dir", remoto, "show", "main:android/chiave/klippeye.p12"))
prova("salva: il messaggio e' quello", git("--git-dir", remoto, "log", "-1", "--format=%s", "main") == "App 1.0.0 [skip ci]")
prova("salva: l'autore e' il robot di GitHub", "actions@users.noreply.github.com" in git("--git-dir", remoto, "log", "-1", "--format=%ae", "main"))
prova("salva: senza cambiamenti non spedisce niente", ci.salva(corta, "main", "niente", ["apk", "android/chiave"]) is False and git("--git-dir", remoto, "log", "-1", "--format=%s", "main") == "App 1.0.0 [skip ci]")
prova("salva: non tocca altro (il resto del repository non e' nel commit)", git("--git-dir", remoto, "show", "--stat", "--format=", "main").count("README") == 0)

# corsa: mentre il workflow costruisce, qualcuno spedisce altro
corta2 = base + "/corta2"
git("clone", "-q", "--depth", "1", "-b", "main", url, corta2)
altro = base + "/altro"
git("clone", "-q", url, altro)
git("config", "user.email", "x@y.z", cwd=altro)
git("config", "user.name", "Utente", cwd=altro)
open(altro + "/README.md", "w").write("ciao, modificato dall'utente\n")
os.makedirs(altro + "/brain", exist_ok=True)
open(altro + "/brain/nuovo.py", "w").write("print(1)\n")
git("add", "-A", cwd=altro)
git("commit", "-q", "-m", "modifica dell'utente", cwd=altro)
git("push", "-q", "origin", "HEAD:main", cwd=altro)
open(corta2 + "/apk/KlippEye.apk", "wb").write(b"B" * 2000)
open(corta2 + "/apk/version.json", "w").write('{"version":"1.0.1"}\n')
prova("salva: con un push arrivato nel frattempo riesce lo stesso", ci.salva(corta2, "main", "App 1.0.1 [skip ci]", ["apk", "android/chiave"]) is True)
prova("salva (corsa): il file nuovo e' sul server", git("--git-dir", remoto, "show", "main:apk/KlippEye.apk") == "B" * 2000)
prova("salva (corsa): la modifica dell'utente e' ancora li'", "modificato dall'utente" in git("--git-dir", remoto, "show", "main:README.md") and "print(1)" in git("--git-dir", remoto, "show", "main:brain/nuovo.py"))
prova("salva (corsa): la chiave non e' sparita", "chiave" in git("--git-dir", remoto, "show", "main:android/chiave/klippeye.p12"))
prova("salva (corsa): storia lineare con i due commit", git("--git-dir", remoto, "log", "--format=%s", "main").splitlines()[:3] == ["App 1.0.1 [skip ci]", "modifica dell'utente", "App 1.0.0 [skip ci]"], git("--git-dir", remoto, "log", "--format=%s", "main"))

# server che rifiuta sempre il push (per esempio ramo protetto): errore comprensibile e non infinito
rifiuta_tutto = base + "/chiuso.git"
git("clone", "-q", "--bare", remoto, rifiuta_tutto)
open(rifiuta_tutto + "/hooks/pre-receive", "w").write("#!/bin/sh\necho 'ramo protetto' >&2\nexit 1\n")
os.chmod(rifiuta_tutto + "/hooks/pre-receive", 0o755)
corta3 = base + "/corta3"
git("clone", "-q", "--depth", "1", "-b", "main", "file://" + rifiuta_tutto, corta3)
os.makedirs(corta3 + "/extra")
open(corta3 + "/extra/x", "w").write("x")
prova("salva: push sempre rifiutato -> errore chiaro dopo qualche tentativo", lancia_errore(lambda: ci.salva(corta3, "main", "x", ["extra"], tentativi=2), "ramo protetto"))

# ---- riga di comando ----
radice, p = repo("1.0.2", {"version": "1.0.1"})
uscita = radice + "/uscita.txt"
os.environ["GITHUB_OUTPUT"] = uscita
os.environ["KLIPPEYE_KEYSTORE_PASSWORD"] = "una frase molto lunga per il test"
buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    codice = ci.main(["--radice", radice, "decidi", "--evento", "push"])
scritto = open(uscita).read()
prova("cli decidi: codice 0 e uscite per GitHub", codice == 0 and "build=true\n" in scritto and "version=1.0.2\n" in scritto and "code=10002\n" in scritto, scritto)
radice, p = repo("1.0.0", {"version": "1.0.0"})
buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    codice = ci.main(["--radice", radice, "decidi"])
prova("cli decidi: stessa versione -> build=false e un avviso visibile", codice == 0 and "::notice" in buffer.getvalue(), buffer.getvalue())
radice, p = repo("1.0.0")
os.environ.pop("KLIPPEYE_KEYSTORE_PASSWORD")
buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    codice = ci.main(["--radice", radice, "decidi", "--evento", "push"])
prova("cli decidi: push senza segreto -> codice 0 (il giro resta verde) e un'annotazione gialla", codice == 0 and "::warning title=App non costruita::" in buffer.getvalue() and "build=false" in buffer.getvalue(), buffer.getvalue())
radice, p = repo("0.9.0", {"version": "1.0.0"})
buffer, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(err):
    codice = ci.main(["--radice", radice, "decidi"])
prova("cli decidi: versione piu' bassa -> codice 1 e annotazione rossa", codice == 1 and "::error title=App Android::" in buffer.getvalue(), buffer.getvalue())
os.environ.pop("GITHUB_OUTPUT")

print("ALL PASS" if errori == 0 else "FAILS: %d" % errori)
sys.exit(1 if errori else 0)
