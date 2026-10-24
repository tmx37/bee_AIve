---
description: Crea una nuova ricetta (flusso di lavoro) per l'orchestratore
argument-hint: "[descrizione del flusso, es. 'estrai le scadenze da un contratto e traducile']"
---
Crea una nuova ricetta in examples/recipes/ per questo flusso: $ARGUMENTS

- Usa solo compiti già offerti dai nodi di esempio, oppure elenca i compiti nuovi che servirebbero
  (con nome, descrizione e prompt di sistema proposto) senza inventare nodi che non esistono.
- Massimizza il parallelismo: passi indipendenti non devono dipendere l'uno dall'altro; usa `split` + `map`
  per documenti lunghi.
- Aggiungi un test in tests/test_rete.py che esegue la ricetta sulla rete simulata (fixture `lab`).
- Mostra il grafo dei passi in forma testuale e spiega quali passi girano in parallelo.
