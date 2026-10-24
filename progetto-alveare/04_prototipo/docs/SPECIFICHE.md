# Specifiche tecniche – Alveare v0.1

Versione dei formati: bundle `schema_version: 1`, rapporto di punteggio `alveare.score/1`,
agent card `alveare/0.1`.

## 1. Bundle di modello

Cartella `<publisher>__<name>__<version>/`:

| File | Contenuto |
|---|---|
| `manifest.json` | metadati del modello e hash di ogni file |
| `signature.json` | firma Ed25519 del manifest in forma canonica |
| `files/` | pesi (`.gguf`, `.safetensors`...) e file accessori |

### Manifest

```json
{
  "schema_version": 1,
  "publisher": "alveare",
  "name": "riassunto-it",
  "version": "0.1.0",
  "license": "Apache-2.0",
  "description": "Riassunto di documenti in italiano.",
  "base_model": "…",
  "tasks": [
    {"name": "riassunto-it", "kind": "chat", "description": "…",
     "system_prompt": "RIASSUMI …", "tags": ["riassunto", "it"]}
  ],
  "runtime": {"engine": "llama.cpp", "model_alias": "riassunto-it", "quantization": "Q4_K_M",
              "min_ram_gb": 4, "device_classes": ["laptop", "mini-pc", "server"]},
  "eval": {},
  "files": {"modello.gguf": {"sha256": "…", "size": 123456}}
}
```

Regole: `publisher` e `name` in minuscolo con trattini; `version` semver; `license` deve appartenere
all'elenco ammesso (`Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `MPL-2.0`, `ISC`).
`kind` ∈ `chat | completion | embedding | image | speech-to-text | text-to-speech`.

### Firma

```json
{"alg": "ed25519", "key_id": "2dab8fa0433e9af6", "signer": "progetto-alveare",
 "signed_at": "2026-10-24T16:00:00+00:00", "signature": "<base64>"}
```

Il messaggio firmato è `canonical_json(manifest)`: JSON con chiavi ordinate, separatori compatti, UTF-8.
`key_id` = primi 16 caratteri esadecimali dello SHA-256 della chiave pubblica grezza.

### Verifica (in quest'ordine)

1. `key_id` presente tra le chiavi fidate (`*.pub.json` nella cartella configurata);
2. firma valida sul manifest canonico;
3. licenza ammessa;
4. nessun file in `files/` non dichiarato;
5. ogni file dichiarato esiste, ha la dimensione e lo SHA-256 attesi.

Evoluzione prevista: firma compatibile con lo standard OpenSSF Model Signing (OMS), usando coppie di chiavi
per la verifica offline.

## 2. Chiavi

- privata: `{"kty": "Ed25519", "key_id", "owner", "private": base64}` (permessi 0600)
- pubblica: `{"kty": "Ed25519", "key_id", "owner", "public": base64}`

## 3. Configurazione del nodo (`nodo.yaml`)

| Campo | Significato |
|---|---|
| `node_id` | nome univoco del nodo |
| `advertise_url` | URL con cui l'orchestratore raggiunge il nodo (IP LAN) |
| `listen_host`, `listen_port` | indirizzo di ascolto |
| `registry`, `trusted_keys` | cartelle del registro e delle chiavi fidate (relative al file) |
| `require_signed_bundles` | se `true` (default) un compito senza bundle valido è disabilitato |
| `allow_public_urls` | default `false`: blocca l'avvio se un URL esce dalla LAN |
| `clients[]` | `{id, api_key_sha256}` dei chiamanti ammessi |
| `tasks[]` | `{name, description, bundle, backend{url, model, api_key_env, timeout_s}, system_prompt, max_tokens, temperature, allowed_clients, max_concurrency}` |

## 4. Configurazione dell'orchestratore (`orchestratore.yaml`)

| Campo | Significato |
|---|---|
| `nodes[]` | `{url, api_key_env}` (o `api_key` solo in sviluppo) |
| `recipes_dir` | cartella delle ricette YAML |
| `clients[]` | `{id, api_key_sha256}` delle postazioni ammesse |
| `max_attempts` | tentativi su nodi diversi per ogni chiamata (default 2) |
| `card_ttl_s` | ogni quanto rileggere le agent card (default 30 s) |
| `request_timeout_s` | timeout di una chiamata a un nodo |

## 5. Agent card del nodo (`GET /.well-known/agent.json`)

Ispirata alle agent card del protocollo A2A (non è ancora un'implementazione conforme: vedi fase 2).

```json
{
  "name": "nodo-a", "url": "http://192.168.1.21:8101", "version": "0.1.0",
  "protocol": "alveare/0.1 (agent card ispirata ad A2A)",
  "capabilities": {"streaming": false},
  "authentication": {"schemes": ["bearer"]},
  "skills": [{"id": "riassunto-it", "kind": "chat", "tags": ["riassunto", "it"],
              "bundle": "alveare/riassunto-it@0.1.0", "enabled": true, "reason": "",
              "max_concurrency": 2}]
}
```

## 6. API

### Nodo

| Metodo | Percorso | Note |
|---|---|---|
| GET | `/health` | stato e compiti abilitati |
| GET | `/.well-known/agent.json` | capacità del nodo |
| POST | `/v1/tasks/{task}` | corpo `{input, params}`; risposta `{task, node_id, output, model, bundle, latency_ms, usage}` |

Errori: 401 chiave mancante o errata, 403 client non autorizzato per il compito, 404 compito non offerto,
503 compito disabilitato (bundle non valido), 502 errore del backend.

### Orchestratore

| Metodo | Percorso | Note |
|---|---|---|
| GET | `/health` | |
| GET | `/nodes` | stato dei nodi e mappa compito → nodi |
| POST | `/nodes/refresh` | rilegge subito le agent card |
| GET | `/recipes` | ricette disponibili e compiti mancanti nella rete |
| POST | `/v1/run` | `{recipe: nome | ricetta inline, inputs}` → `{recipe, outputs, trace, elapsed_ms}` |
| POST | `/v1/tasks/{task}` | singolo compito instradato al nodo migliore |

Autenticazione: intestazione `Authorization: Bearer <chiave>`. Senza `clients` configurati l'API è aperta
(solo sviluppo: `alveare doctor` lo segnala).

## 7. Ricette

```yaml
name: traduci-e-riassumi
inputs: [testo]
steps:
  - {id: parti, op: split, input: "{{ inputs.testo }}", max_chars: 600}
  - {id: traduzioni, task: traduzione-it-en, map: parti, input: "{{ item }}"}
  - {id: traduzione, op: join, from: traduzioni}
  - {id: sintesi, task: riassunto-it, input: "{{ inputs.testo }}"}
outputs: {traduzione_en: traduzione, riassunto_it: sintesi}
```

- Un passo ha **o** `task` (eseguito da un nodo) **o** `op` (operazione locale: `split`, `join`).
- Riferimenti nei template: `{{ inputs.x }}`, `{{ steps.id }}`, `{{ item }}`, `{{ index }}`.
- Le dipendenze si ricavano dai riferimenti, da `map` e da `from`. Ogni passo parte appena le sue
  dipendenze sono pronte; le esecuzioni di un `map` sono parallele.

- Validazione al caricamento: id unici, riferimenti esistenti, input dichiarati, nessun ciclo.

## 8. Validazione e rapporto di punteggio

Casi di test (JSONL, privati, non escono dalla rete):

```json
{"input": "…", "expected": "…", "metric": "chrf"}
{"input": "…", "expected": ["termine1", "termine2"], "metric": "contains"}
```

Metriche: `exact`, `contains` (quota di termini attesi presenti), `chrf` (0–100, caratteri, β=2).

Rapporto firmato (`alveare.score/1`):

```json
{
  "payload": {
    "schema": "alveare.score/1", "task": "riassunto-it", "bundle": "alveare/riassunto-it@0.1.0",
    "result": {"n_cases": 3, "failures": 0, "score_mean": 99.48, "by_metric": {"contains": 100.0, "chrf": 98.4}},
    "cases_sha256": "…", "device": {"system": "Linux", "machine": "aarch64", "python": "3.12.3"},
    "tool_version": "0.1.0", "created_at": "…", "validator_key_id": "…"
  },
  "signature": "<base64>"
}
```

Aggregazione: si scartano i rapporti con firma non valida o di validatori non fidati e si usa la mediana
(robusta a pochi valori anomali). Evoluzione prevista: peso per reputazione del validatore e riesecuzione
a campione (fase 5).
