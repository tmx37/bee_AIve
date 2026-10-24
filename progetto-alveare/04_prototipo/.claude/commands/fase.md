---
description: Pianifica e implementa una fase del piano di azione di Alveare
argument-hint: "[numero della fase, es. 2]"
---
Lavoriamo sulla fase $ARGUMENTS del piano di azione di Alveare.

1. Leggi CLAUDE.md, docs/SPECIFICHE.md e la sezione della fase $ARGUMENTS in docs/PIANO_DI_AZIONE.md.
2. Esplora il codice coinvolto senza modificarlo e proponi un piano a passi piccoli, ciascuno con i test che lo verificano.
3. Elenca le decisioni aperte e le domande per me prima di scrivere codice.
4. Dopo la mia approvazione implementa un passo alla volta: test prima, poi codice, poi `pytest`.
5. Alla fine aggiorna docs/SPECIFICHE.md se hai cambiato un formato o un'API, e riassumi cosa è stato fatto,
   cosa resta aperto e come verificarlo a mano.

Rispetta sempre gli invarianti di CLAUDE.md (offline, bundle verificati, solo licenze OSI, segreti mai in chiaro).
