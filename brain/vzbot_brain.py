"""
Compatibilita' con il vecchio nome (fino alla 1.0.x KlippEye si chiamava VzBot).

Il servizio "vzbot" che hai installato con la 1.0.x avvia ancora QUESTO file. Qui non c'e' piu' il programma: questo file lancia
il backend nuovo (backend/klippeye_backend.py), cosi' dopo l'aggiornamento tutto continua a funzionare senza spostare niente.

Per passare davvero al nuovo nome (cartella ~/klippeye, servizio "klippeye"): dashboard -> Impostazioni -> Aggiornamenti ->
"Passa a KlippEye", oppure da terminale:  bash ~/vzbot/scripts/passa-a-klippeye.sh
Dopo il passaggio questo file (e la cartella brain/) non servono piu': l'aggiornamento successivo li toglie.
"""
import os
import runpy
import sys

_target = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "klippeye_backend.py")
sys.path.insert(0, os.path.dirname(_target))
runpy.run_path(_target, run_name="__main__")
