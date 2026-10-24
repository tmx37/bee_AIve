# Alveare – prototipo della rete locale offline

Alveare (nome di lavoro) è il prototipo della parte **locale e offline** del progetto:
una rete di nodi, client e orchestratore che usa modelli aperti e specializzati, distribuiti
come **bundle firmati**, senza alcuna connessione a internet.

Questa è la fase 1 del piano di azione: la rete locale ha valore anche da sola e fa da base
per la piattaforma condivisa di training e validazione (fasi successive).

## Cosa fa già (verificato da test e demo)

| Funzione | Stato | Dove |
|---|---|---|
| Chiavi Ed25519, firma e verifica offline | funzionante | `src/alveare/crypto.py` |
| Bundle di modello firmati (manifest + hash + firma), solo licenze OSI | funzionante | `src/alveare/bundle.py` |
| Registro locale che accetta solo bundle verificati | funzionante | `src/alveare/registry.py` |
| Nodo: un compito = un modello + un'API, agent card ispirata ad A2A | funzionante | `src/alveare/node.py` |
| Politica di rete solo LAN (blocca URL pubblici) | funzionante | `src/alveare/config.py` |
| Orchestratore: ricette a grafo, passi in parallelo, scelta del nodo meno carico, nuovo tentativo su altro nodo | funzionante | `src/alveare/orchestrator.py`, `recipes.py` |
| Validazione locale con test privati e rapporto di punteggio firmato, aggregazione con mediana | funzionante | `src/alveare/validate.py` |
| Backend finto OpenAI-compatibile per provare tutto senza modelli | funzionante | `src/alveare/mock_backend.py` |
| Modelli veri via llama-server / llama-swap | da collegare (configurazione d'esempio pronta) | `examples/llama-swap.yaml` |

Test: `pytest` → 28 test superati. Demo: `bash scripts/demo.sh`.

## Avvio rapido

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # 28 test
bash scripts/demo.sh        # chiavi, bundle, registro, 2 nodi, orchestratore, ricette, validazione
```

La demo usa le porte 8080 (backend finto), 8100 (orchestratore), 8101 e 8102 (nodi).

## Architettura in breve

```
postazione (client) ──► orchestratore ──► nodo-a ──► backend (llama-swap / llama-server)
                              │            └─ compiti: traduzione-it-en, riassunto-it
                              └──────────► nodo-b ──► backend
                                           └─ compiti: traduzione-it-en, correzione-it

registro locale  ◄── bundle firmati importati da supporto rimovibile (nessuna rete)
```

- **Client**: invia una ricetta o un singolo compito all'orchestratore (`alveare run`, `alveare task`).
- **Orchestratore**: legge le agent card dei nodi, esegue la ricetta come grafo e manda i passi
  indipendenti in parallelo ai nodi che offrono quel compito.

- **Nodo**: espone uno o più compiti; ogni compito usa un bundle verificato del registro e un backend
  OpenAI-compatibile sulla stessa macchina.

- **Bundle**: pesi + manifest + firma. Il nodo disabilita il compito se la firma, gli hash o la
  licenza non sono validi.

Le specifiche dei formati (bundle, configurazioni, agent card, ricette, rapporto di punteggio, API)
sono in [`docs/SPECIFICHE.md`](docs/SPECIFICHE.md).

## Usare modelli veri

1. Installa llama.cpp (`llama-server`) e llama-swap sul nodo.
2. Crea il bundle con il vero file `.gguf` (`alveare bundle build ...`) e importalo nel registro.
3. Adatta `examples/llama-swap.yaml` ai percorsi del registro e avvia llama-swap su `127.0.0.1:8080`.
4. Lascia invariati i file `nodo-*.yaml`: il campo `backend.model` corrisponde al nome del modello in llama-swap.

## Lavorare con Claude Code

Il file [`CLAUDE.md`](CLAUDE.md) contiene contesto, regole e comandi del progetto. In `.claude/commands/`
ci sono comandi pronti (`/fase`, `/verifica`, `/nuova-ricetta`, `/nuovo-compito`) e in `.claude/agents/`
un subagente per la revisione di sicurezza offline. Il piano di azione completo è nella cartella
`01_piano_di_azione` del pacchetto.

## Licenza

Apache-2.0 (vedi `LICENSE`).
