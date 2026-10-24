# Progetto Alveare – cartella di avvio

Questa cartella contiene tutto il necessario per portare su un piano reale il progetto discusso:
una piattaforma condivisa dove la community specializza e comprime modelli IA aperti, e reti locali
completamente offline (orchestratore, nodi, client) dove quei modelli vengono usati tramite API.
"Alveare" è un nome di lavoro.

## Contenuto

| Cartella | Contenuto | Formato |
|---|---|---|
| `01_piano_di_azione/` | Piano di azione in 7 fasi (16 settimane) con criteri di accettazione, rischi e prompt pronti per Claude Code | `.md` (per Claude Code) + `.pdf` |
| `02_documento_riassuntivo/` | Sintesi dell'idea, architettura, potenzialità con i calcoli ed esempio d'uso in uno studio professionale | `.pdf` |
| `03_fonti_e_stato_tecnologie/` | Fonti con link, valutazione di maturità di ogni tecnologia, dati di mercato, lacune da colmare | `.md` + `.pdf` |
| `04_prototipo/` | Prototipo funzionante della rete locale offline (Python, Apache-2.0), pronto da aprire con Claude Code | repository |

Ordine di lettura consigliato: 02 → 01 → 03, poi 04.

## Il prototipo (04_prototipo)

Già funzionante e verificato:

- bundle di modello firmati (Ed25519) con verifica offline di firma, hash, file e licenza (solo OSI);
- registro locale che accetta solo bundle verificati;
- nodi che espongono compiti come API con agent card ispirata ad A2A e chiavi API salvate solo come hash;
- orchestratore che esegue ricette a grafo con passi in parallelo, sceglie il nodo meno carico e riprova
  su un altro nodo in caso di guasto;
- politica di rete solo LAN (un URL pubblico impedisce l'avvio) e comando `alveare doctor`;
- validazione locale con test privati e rapporto di punteggio firmato, aggregazione con mediana;
- backend finto per provare tutto senza scaricare modelli.

Verifica eseguita: **28 test superati**; demo completa con processi reali su localhost (2 nodi,
orchestratore, ricetta parallela con guadagno di circa 3,8 volte rispetto all'esecuzione in sequenza
con il backend simulato, validazione con rapporto firmato).

## Come iniziare con Claude Code

```bash
cd 04_prototipo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # 28 test
bash scripts/demo.sh      # demo end-to-end (porte 8080, 8100, 8101, 8102)
claude                    # apri Claude Code nella cartella
```

In Claude Code:

1. il file `CLAUDE.md` viene caricato automaticamente (contesto, comandi, invarianti di sicurezza);
2. lancia `/fase 0` e poi `/fase 1` seguendo il piano: Claude propone un piano prima di scrivere codice;
3. chiudi ogni lavoro con `/verifica` e, per modifiche a rete o firme, chiedi la revisione al subagente
   `revisore-offline`.

## Note importanti

- I numeri delle potenzialità sono **stime d'ordine di grandezza** basate su dati pubblici (fonti nel
  documento 03); le ipotesi sono dichiarate nel documento 02.
- I modelli reali da usare nella fase 1 vanno scelti **verificando la licenza al momento della scelta**:
  alcune famiglie hanno cambiato licenza tra una versione e l'altra.
- Il prototipo non contiene pesi di modelli: la demo usa un backend simulato. Per i modelli veri segui
  `04_prototipo/examples/llama-swap.yaml` e la fase 1 del piano.
