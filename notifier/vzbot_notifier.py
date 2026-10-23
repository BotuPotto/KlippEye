"""
Compatibilita' con il vecchio nome (fino alla 1.0.x KlippEye si chiamava VzBot): il servizio "vzbot-notifier" della 1.0.x avvia
ancora questo file, che lancia il servizio delle notifiche nuovo (klippeye_notifier.py) con gli stessi argomenti.
Dopo il passaggio a KlippEye (dashboard -> Impostazioni -> Aggiornamenti -> "Passa a KlippEye") non serve piu'.
"""
import os
import runpy
import sys

_target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klippeye_notifier.py")
sys.path.insert(0, os.path.dirname(_target))
runpy.run_path(_target, run_name="__main__")
