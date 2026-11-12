# Il modello locale del monitor IA

Un piccolo modello che gira **sul Raspberry**, senza internet e senza costi, e dice quanto è probabile che una foto mostri
una stampa fallita (spaghetti, pezzo staccato…). Lo addestri **una volta** su un computer o su Google Colab con foto
pubbliche e, se vuoi, con le tue; poi lo misuri sulle tue stampe prima di usarlo.

Il modello è MobileNetV3-Small (licenza BSD), parte da ciò che sa già sulle immagini (ImageNet) e impara solo com'è una
stampa fallita. Sul Raspberry lo esegue OpenCV, già installato con KlippEye: non serve nient'altro.

## Il modo più semplice: Google Colab

Apri [il notebook su Colab](https://colab.research.google.com/github/BotuPotto/KlippEye/blob/main/ml/KlippEye_local_model.ipynb)
ed esegui le celle dall'alto in basso: scarica da solo **tutte** le raccolte pubbliche elencate in `ml/sources.json`
(serve solo una chiave Roboflow gratuita), aggiunge le tue stampe se carichi il loro zip, addestra con la GPU gratuita,
misura e ti fa scaricare il modello. I passaggi sotto sono gli stessi, per chi preferisce il proprio computer.

## 1. Le foto

Servono foto di **stampe fallite** e di **stampe andate bene**.

- **Raccolte pubbliche, tutte insieme**: `ROBOFLOW_API_KEY=… python ml/download.py` scarica ogni raccolta di
  `ml/sources.json` (una ventina, l'ultima versione di ciascuna) in `ml/data/` e scrive `ml/data/CREDITS.md` con la
  licenza di ognuna. La chiave è gratuita: [roboflow.com](https://roboflow.com) → Settings → API Keys. Le classi delle
  raccolte vengono lette dai nomi: i guasti che rovinano la stampa (spaghetti, distacco, layer spostati, blob…) contano
  come «fallita», le foto di stampe normali come «buona», i difetti di qualità (stringing, zits…) restano fuori.
- **Altre raccolte a mano**: su [Roboflow Universe](https://universe.roboflow.com) cerca «3D print failure», «spaghetti»,
  «print defects». Apri una raccolta → *Download Dataset* → formato **YOLOv8** → scarica lo zip ed estrailo. Controlla la
  licenza di ogni raccolta (molte sono CC BY 4.0: va bene, citando l'autore). Alcune da cui partire:
  [FDM Failures – Spaghetti](https://universe.roboflow.com/bu-engme500-vision-project/fdm-failures-spaghetti),
  [3D Printing Defects](https://universe.roboflow.com/3d-printing-monitoring-system-team-129-spring-2024-survm/3d-printing-defects-e2fsz),
  [3D Print Failure Detection](https://universe.roboflow.com/om-sakharkar-d0y3z/3d-print-failure-detection-pbxw5).
- **Le tue stampe** (consigliato: è la tua telecamera, la tua luce): copia la cartella dei dati di KlippEye dal Raspberry.
  Contiene le registrazioni giudicate e le risposte a «Com'è andata la stampa?».
  ```
  scp -r pi@INDIRIZZO-DEL-RASPBERRY:~/printer_data/klippeye ./klippeye-data
  ```
- **Foto tue già divise**: una cartella con dentro `ok/` e `fail/`.

## 2. L'elenco delle foto

```
pip install -r ml/requirements.txt
python ml/datasets.py --auto ml/data --klippeye ./klippeye-data --out ml/work
```
Dice quante foto ha trovato, fallite e buone. Le foto della stessa stampa restano insieme: una parte viene tenuta da parte
per misurare il modello su foto che non ha mai visto.

Le raccolte pubbliche hanno quasi solo stampe fallite: come esempi di stampa che va bene vengono presi pezzi delle stesse
foto lontani dai riquadri del difetto; la foto intera resta solo se il difetto ne copre almeno un quinto. Da ogni
raccolta al massimo 3000 foto (`--max-per-dataset`), così nessuna pesa troppo e l'addestramento resta rapido.

Opzioni utili: `--fail-classes spaghetti,detached` per dire quali classi di una raccolta sono guasti (in automatico: tutte
tranne quelle che si chiamano come ok / print / nozzle…); `--empty-is-ok` se nella raccolta le foto senza riquadri sono
stampe andate bene.

## 3. L'addestramento

```
python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model
```
Su un computer senza scheda video ci vuole da qualche minuto a un'ora, secondo quante foto hai; su
[Google Colab](https://colab.research.google.com) con la GPU gratuita (Runtime → Cambia tipo di runtime → GPU) molto
meno:
```
!git clone https://github.com/BotuPotto/KlippEye && cd KlippEye && pip install -r ml/requirements.txt
# carica i tuoi zip nel pannello File, estraili, poi gli stessi comandi di sopra con ! davanti
```
A ogni giro stampa come va sulle foto tenute da parte. Alla fine scrive `ml/out/model/` con `model.onnx` e `model.json`
(la soglia scelta: la più bassa che tiene giusti almeno 9 allarmi su 10) e controlla che OpenCV dia la stessa risposta
di PyTorch, come farà il Raspberry.

## 4. La misura sulle tue stampe

```
python ml/evaluate.py --model ml/out/model --data ./klippeye-data
```
Per diverse soglie dice quanti **falsi allarmi all'ora** avrebbe dato sulle stampe andate bene e quante **stampe fallite
avrebbe preso**, e dopo quanto. Più stampe hai giudicato, più la misura è affidabile. `--consecutive 2` conta un allarme
solo con due foto di fila sopra la soglia.

Si può lanciare anche sul Raspberry (serve solo OpenCV, già presente):
```
cd ~/klippeye && python3 ml/evaluate.py --model ~/modello --data ~/printer_data/klippeye
```

Il passo successivo di KlippEye userà questo modello nel monitor, accanto a OpenCV e all'IA online.
