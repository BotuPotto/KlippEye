# Loghi della stampante

In **Impostazioni → Stampante** la dashboard può mostrare nella barra in alto, e come icona della scheda del browser,
il logo di **KlippEye** (predefinito), **VzBot**, **Voron** o **RatRig**.

Il logo di KlippEye e quello di VzBot sono già dentro la dashboard. Per **Voron** e **RatRig** (e per cambiare quello di VzBot)
metti qui, in questa cartella, il file del logo **ufficiale**, con uno di questi nomi esatti (tutto minuscolo):

| Marca  | Nomi accettati                          |
|--------|-----------------------------------------|
| VzBot  | `vzbot.svg`  `vzbot.png`  `vzbot.webp`  |
| Voron  | `voron.svg`  `voron.png`  `voron.webp`  |
| RatRig | `ratrig.svg` `ratrig.png` `ratrig.webp` |

* Il formato migliore è **SVG**; con un PNG o un WebP usa un file con sfondo trasparente e almeno 256 pixel di larghezza.
* Al massimo 2 MB per file. Se per una marca ci sono più formati vince nell'ordine svg, png, webp.
* I file si prendono dalle pagine ufficiali di ciascun progetto (sito o repository del progetto) e vanno usati come sono,
  senza ridisegnarli.
* Dopo aver caricato il file su GitHub: dashboard → Impostazioni → Aggiornamenti → Controlla → Aggiorna. Il logo compare subito
  nella pagina Stampante (non serve ricostruire niente). Finché un file manca, per quella marca la barra mostra solo il nome.
