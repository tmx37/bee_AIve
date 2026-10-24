# CLAUDE.md – Alveare

Questo file dà a Claude Code il contesto del progetto. Va tenuto aggiornato a ogni fase.

## Il progetto in una frase

Un sistema aperto in due livelli: una **piattaforma condivisa** dove la community specializza e
comprime modelli open source per compiti precisi (training a torneo + validazione distribuita), e una
**rete locale completamente offline** (orchestratore, nodi, client) dove quei modelli vengono usati
tramite API, scaricati come bundle firmati.

Questo repository contiene il **prototipo della rete locale** (fase 1) e i primi pezzi del ponte verso
la piattaforma (validazione locale con rapporto firmato).

## Comandi

```bash
pip install -e ".[dev]"      # installazione in modalità sviluppo
pytest                       # tutti i test (devono passare sempre)
pytest tests/test_rete.py -k failover   # un singolo test
bash scripts/demo.sh         # demo end-to-end con processi reali su localhost
alveare doctor --node examples/nodo-a.yaml --orchestrator examples/orchestratore.yaml
```

## Mappa del codice

- `src/alveare/crypto.py` – chiavi Ed25519, JSON canonico, hash. Tutto ciò che si firma passa da `canonical_json`.
- `src/alveare/bundle.py` – manifest (pydantic), `build_bundle`, `verify_bundle`, licenze ammesse `OSI_LICENSES`.
- `src/alveare/registry.py` – registro locale; accetta solo bundle verificati e riverifica dopo la copia.
- `src/alveare/config.py` – configurazioni nodo/orchestratore, politica di rete solo LAN, autenticazione a chiave.
- `src/alveare/node.py` – app FastAPI del nodo: `/health`, `/.well-known/agent.json`, `POST /v1/tasks/{task}`.
- `src/alveare/recipes.py` – ricette YAML, grafo di dipendenze, esecuzione parallela con asyncio.
- `src/alveare/orchestrator.py` – `NodePool` (agent card, scelta del nodo, tentativi) e API `/v1/run`, `/v1/tasks/{task}`.
- `src/alveare/validate.py` – chrF, punteggi, rapporto firmato, aggregazione con mediana.
- `src/alveare/mock_backend.py` – backend finto OpenAI-compatibile per test e demo.
- `src/alveare/cli.py` – comando `alveare`.
- `tests/conftest.py` – rete completa simulata in memoria con `httpx.ASGITransport` (nessuna porta aperta).

## Invarianti da non rompere mai

1. **Offline per costruzione.** Nessun codice deve fare richieste verso internet. Ogni URL configurato passa da
   `check_urls`; un nuovo client HTTP va creato tramite `client_factory` iniettabile (serve ai test).
   Niente telemetria, niente download automatici, niente dipendenze che chiamano casa all'import.

2. **Nessun modello senza verifica.** Un compito si abilita solo se il suo bundle supera `verify_bundle`
   (chiave fidata, firma, hash, dimensioni, nessun file extra, licenza in `OSI_LICENSES`).

3. **Solo licenze OSI.** Non aggiungere licenze non commerciali o "community" all'elenco ammesso.
4. **Segreti mai in chiaro su disco.** Le configurazioni contengono solo lo SHA-256 delle chiavi API;
   le chiavi vere arrivano da variabili d'ambiente (`api_key_env`).

5. **I casi di test dei validatori restano privati.** Il rapporto di punteggio contiene solo l'hash del file dei casi.
6. **Compatibilità OpenAI verso i backend.** I nodi parlano con i backend solo via `/v1/chat/completions`
   (e in futuro gli altri endpoint standard), così llama-server, llama-swap e vLLM restano intercambiabili.

## Convenzioni

- Python ≥ 3.10, tipi annotati, pydantic v2, FastAPI, httpx asincrono.
- Messaggi per l'utente, documentazione e commenti in italiano; nomi di variabili e funzioni possono restare in inglese.
- Ogni nuova funzione arriva con i suoi test in `tests/`; i test di rete usano la fixture `lab` di `conftest.py`.
- Le modifiche ai formati (manifest, agent card, ricette, rapporto di punteggio) vanno riportate in `docs/SPECIFICHE.md`
  con un numero di versione dello schema.

## Come lavorare su questo repository

- Per ogni fase del piano: entra in plan mode, leggi `docs/SPECIFICHE.md` e il file della fase, proponi il piano,
  poi implementa a piccoli passi con i test.

- Prima di dichiarare finito un compito: `pytest` verde, `bash scripts/demo.sh` senza errori, `alveare doctor` pulito.
- Per modifiche a rete, firme o autenticazione chiedi una revisione al subagente `revisore-offline`.
