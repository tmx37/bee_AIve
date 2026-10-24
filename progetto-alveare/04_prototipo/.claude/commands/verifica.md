---
description: Verifica completa prima di chiudere un lavoro
---
Esegui in ordine e riporta l'esito di ciascun punto:

1. `pytest -q` (tutti i test devono passare).
2. `bash scripts/demo.sh` (deve arrivare a "Fine demo" senza errori).
3. `alveare doctor --node examples/nodo-a.yaml --orchestrator examples/orchestratore.yaml`.
4. Cerca nel codice nuove chiamate di rete (`httpx.`, `requests`, `urllib`, `socket`) e controlla che passino
   tutte da URL validati con `check_urls` e da una `client_factory` iniettabile.
5. Controlla che nessun file di configurazione o di test contenga chiavi API in chiaro (solo SHA-256).

Se qualcosa fallisce, proponi la correzione minima e non procedere oltre finché non è risolto.
