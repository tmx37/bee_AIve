#!/usr/bin/env bash
# Demo completa della rete locale offline, senza modelli veri (backend finto).
# Avvia: backend finto (8080), nodo-a (8101), nodo-b (8102), orchestratore (8100).
# Uso: bash scripts/demo.sh   (dalla radice del prototipo, dopo `pip install -e .`)
set -euo pipefail
cd "$(dirname "$0")/.."

RUN=demo-run
rm -rf "$RUN"
mkdir -p "$RUN/chiavi" "$RUN/chiavi-fidate" "$RUN/build" "$RUN/registro" "$RUN/log"

export HF_HUB_OFFLINE=1
export ALVEARE_NODE_KEY=demo-chiave-orchestratore   # orchestratore -> nodi
export ALVEARE_CLIENT_KEY=demo-chiave-client         # postazione -> orchestratore

titolo() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

attendi() {  # attende che un servizio risponda su /health o /v1/models
  local url=$1
  for _ in $(seq 1 50); do
    if python3 -c "import httpx,sys; sys.exit(0 if httpx.get('$url', timeout=1).status_code==200 else 1)" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  echo "servizio non raggiungibile: $url" >&2
  return 1
}

titolo "1) Chiavi: firma del progetto e firma del validatore"
alveare keys gen --owner progetto-alveare --out "$RUN/chiavi"
alveare keys gen --owner validatore-ufficio --out "$RUN/chiavi"
cp "$RUN/chiavi/progetto-alveare.pub.json" "$RUN/chiavi/validatore-ufficio.pub.json" "$RUN/chiavi-fidate/"

titolo "2) Bundle firmati e registro locale (pesi finti al posto dei .gguf)"
head -c 4096 /dev/urandom > "$RUN/modello-demo.gguf"
for t in traduzione-it-en riassunto-it correzione-it; do
  alveare bundle build --manifest "examples/bundles-src/$t/manifest.yaml" \
    --files "$RUN/modello-demo.gguf" --key "$RUN/chiavi/progetto-alveare.key.json" --out "$RUN/build"
  alveare registry add "$RUN/build/alveare__${t}__0.1.0" --registry "$RUN/registro" --trusted "$RUN/chiavi-fidate"
done
alveare registry list --registry "$RUN/registro" --trusted "$RUN/chiavi-fidate"

titolo "3) Avvio backend finto, due nodi e orchestratore"
alveare mock-backend --port 8080 --delay 0.4 > "$RUN/log/backend.log" 2>&1 &
attendi http://127.0.0.1:8080/v1/models
alveare node serve --config examples/nodo-a.yaml > "$RUN/log/nodo-a.log" 2>&1 &
alveare node serve --config examples/nodo-b.yaml > "$RUN/log/nodo-b.log" 2>&1 &
alveare orchestrator serve --config examples/orchestratore.yaml > "$RUN/log/orchestratore.log" 2>&1 &
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT
attendi http://127.0.0.1:8101/health
attendi http://127.0.0.1:8102/health
attendi http://127.0.0.1:8100/health
echo "servizi avviati"

titolo "4) Controlli offline"
alveare doctor --node examples/nodo-a.yaml --orchestrator examples/orchestratore.yaml || true

titolo "5) Capacità annunciate dai nodi"
python3 - <<'PY'
import httpx, os
r = httpx.get("http://127.0.0.1:8100/nodes", headers={"Authorization": f"Bearer {os.environ['ALVEARE_CLIENT_KEY']}"})
for task, nodes in sorted(r.json()["capabilities"].items()):
    print(f"  {task:18} -> {', '.join(nodes)}")
PY

titolo "6) Ricetta parallela: traduzione a pezzi su due nodi + riassunto in contemporanea"
alveare run traduci-e-riassumi --input testo=@examples/testi/contratto_esempio.txt

titolo "7) Ricetta sequenziale: correzione -> riassunto"
alveare run correggi-e-riassumi --input "testo=il  fornitore consegna entro trenta giorni . la penale è dell'uno per cento."

titolo "8) Validazione locale privata con rapporto firmato"
alveare validate --url http://127.0.0.1:8100 --task riassunto-it \
  --cases examples/validazione/casi_riassunto.jsonl \
  --signing-key "$RUN/chiavi/validatore-ufficio.key.json" \
  --bundle alveare/riassunto-it@0.1.0 --out "$RUN/punteggio-riassunto.json"
alveare score verify "$RUN/punteggio-riassunto.json" --trusted "$RUN/chiavi-fidate"

titolo "Fine demo"
echo "File generati in $RUN/ (chiavi, bundle, registro, log, rapporto di punteggio)."
