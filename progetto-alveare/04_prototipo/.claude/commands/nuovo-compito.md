---
description: Aggiunge un nuovo compito (modello specialistico) alla rete locale
argument-hint: "[nome-compito, es. estrazione-scadenze-it]"
---
Aggiungi il compito `$ARGUMENTS` alla rete di esempio:

1. Crea examples/bundles-src/$ARGUMENTS/manifest.yaml (licenza OSI, prompt di sistema, runtime, classi di dispositivo).
2. Aggiungilo a un nodo di esempio (examples/nodo-*.yaml) e alla demo (scripts/demo.sh).
3. Se il backend finto non sa simulare il compito, estendi mock_backend.py con una trasformazione deterministica
   riconoscibile dal prompt di sistema.
4. Prepara 5 casi di validazione in examples/validazione/casi_$ARGUMENTS.jsonl.
5. Aggiungi i test e lancia /verifica.
