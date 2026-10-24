"""Riga di comando `alveare`.

Comandi principali:
  alveare keys gen --owner NOME --out DIR
  alveare bundle build --manifest M --files F... --key K --out DIR
  alveare bundle verify DIR --trusted DIR
  alveare registry add BUNDLE --registry DIR --trusted DIR
  alveare registry list --registry DIR --trusted DIR
  alveare mock-backend --port 8080 [--delay 0.5]
  alveare node serve --config node.yaml
  alveare orchestrator serve --config orchestrator.yaml
  alveare nodes --orchestrator URL
  alveare run RICETTA --orchestrator URL --input nome=@file.txt
  alveare task COMPITO --orchestrator URL --text "..."
  alveare validate --url URL --task T --cases casi.jsonl --signing-key K --bundle ID --out score.json
  alveare score verify score.json --trusted DIR
  alveare score aggregate score1.json score2.json ... --trusted DIR
  alveare doctor [--node node.yaml] [--orchestrator orchestrator.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx


def _api_headers(env_name: str | None) -> dict:
    key = os.environ.get(env_name) if env_name else None
    return {"Authorization": f"Bearer {key}"} if key else {}


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_keys_gen(a) -> int:
    from .crypto import generate_keypair

    kp = generate_keypair(a.owner)
    priv, pub = kp.save(Path(a.out))
    print(f"chiave privata: {priv}\nchiave pubblica: {pub}\nkey_id: {kp.key_id}")
    return 0


def cmd_bundle_build(a) -> int:
    from .bundle import build_bundle
    from .crypto import load_private

    out = build_bundle(Path(a.manifest), [Path(f) for f in a.files], Path(a.out), load_private(Path(a.key)))
    print(f"bundle creato e firmato: {out}")
    return 0


def cmd_bundle_verify(a) -> int:
    from .bundle import VerificationError, verify_bundle
    from .crypto import load_trusted_keys

    try:
        m = verify_bundle(Path(a.bundle), load_trusted_keys(Path(a.trusted)))
    except VerificationError as e:
        print(f"VERIFICA FALLITA: {e}")
        return 1
    print(f"OK: {m.bundle_id} (licenza {m.license}, {len(m.files)} file)")
    return 0


def cmd_registry_add(a) -> int:
    from .registry import Registry

    m = Registry(Path(a.registry), Path(a.trusted)).add(Path(a.bundle), replace=a.replace)
    print(f"aggiunto al registro: {m.bundle_id}")
    return 0


def cmd_registry_list(a) -> int:
    from .registry import Registry

    for e in Registry(Path(a.registry), Path(a.trusted)).entries():
        status = "OK " if e.valid else "ERR"
        detail = ", ".join(t.name for t in e.manifest.tasks) if e.manifest else e.error
        print(f"[{status}] {e.bundle_id}  ->  {detail}")
    return 0


def cmd_mock_backend(a) -> int:
    import uvicorn

    from .mock_backend import create_mock_backend

    uvicorn.run(create_mock_backend(delay_s=a.delay), host=a.host, port=a.port, log_level="warning")
    return 0


def cmd_node_serve(a) -> int:
    import uvicorn

    from .config import load_node_config
    from .node import create_node_app

    cfg = load_node_config(Path(a.config))
    uvicorn.run(create_node_app(cfg), host=a.host or cfg.listen_host, port=a.port or cfg.listen_port,
                log_level="warning")
    return 0


def cmd_orchestrator_serve(a) -> int:
    import uvicorn

    from .config import load_orchestrator_config
    from .orchestrator import create_orchestrator_app

    cfg = load_orchestrator_config(Path(a.config))
    uvicorn.run(create_orchestrator_app(cfg), host=a.host or cfg.listen_host,
                port=a.port or cfg.listen_port, log_level="warning")
    return 0


def _parse_inputs(pairs: list[str]) -> dict:
    inputs = {}
    for p in pairs or []:
        name, _, value = p.partition("=")
        if value.startswith("@"):
            value = Path(value[1:]).read_text()
        inputs[name] = value
    return inputs


def cmd_nodes(a) -> int:
    r = httpx.get(f"{a.orchestrator.rstrip('/')}/nodes", headers=_api_headers(a.api_key_env), timeout=30)
    r.raise_for_status()
    _print(r.json())
    return 0


def cmd_run(a) -> int:
    r = httpx.post(
        f"{a.orchestrator.rstrip('/')}/v1/run",
        json={"recipe": a.recipe, "inputs": _parse_inputs(a.input)},
        headers=_api_headers(a.api_key_env),
        timeout=600,
    )
    if r.status_code >= 400:
        print(f"ERRORE {r.status_code}: {r.text}")
        return 1
    data = r.json()
    if a.json:
        _print(data)
        return 0
    for name, value in data["outputs"].items():
        print(f"\n=== {name} ===")
        print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    print(f"\n--- traccia ({data['elapsed_ms']} ms totali) ---")
    for e in data["trace"]:
        label = e["step"] + ("" if e.get("index") is None else f"[{e['index']}]")
        print(f"  {label:16} {e['task']:18} nodo={e['node']:10} {e['ms']:6} ms  tentativo {e['attempt']}")
    somma = sum(e["ms"] for e in data["trace"])
    if data["elapsed_ms"]:
        print(f"  somma dei tempi delle chiamate: {somma} ms -> guadagno dal parallelismo "
              f"x{somma / data['elapsed_ms']:.1f}")
    return 0


def cmd_task(a) -> int:
    r = httpx.post(
        f"{a.orchestrator.rstrip('/')}/v1/tasks/{a.task}",
        json={"input": a.text}, headers=_api_headers(a.api_key_env), timeout=300,
    )
    if r.status_code >= 400:
        print(f"ERRORE {r.status_code}: {r.text}")
        return 1
    _print(r.json())
    return 0


def cmd_validate(a) -> int:
    from .crypto import load_private
    from .validate import make_score_report, run_validation

    key = os.environ.get(a.api_key_env) if a.api_key_env else None
    result = asyncio.run(run_validation(a.url, a.task, Path(a.cases), key))
    report = make_score_report(result, a.task, a.bundle, Path(a.cases), load_private(Path(a.signing_key)))
    Path(a.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"punteggio medio {result['score_mean']} su {result['n_cases']} casi -> {a.out}")
    return 0


def cmd_score_verify(a) -> int:
    from .crypto import load_trusted_keys
    from .validate import verify_score_report

    ok = verify_score_report(json.loads(Path(a.report).read_text()), load_trusted_keys(Path(a.trusted)))
    print("firma valida" if ok else "FIRMA NON VALIDA")
    return 0 if ok else 1


def cmd_score_aggregate(a) -> int:
    from .crypto import load_trusted_keys
    from .validate import aggregate_reports

    reports = [json.loads(Path(p).read_text()) for p in a.reports]
    _print(aggregate_reports(reports, load_trusted_keys(Path(a.trusted))))
    return 0


def cmd_doctor(a) -> int:
    from .config import check_urls, load_node_config, load_orchestrator_config

    problems = []
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if os.environ.get(var):
            problems.append(f"variabile {var} impostata: il traffico potrebbe uscire dalla rete locale")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        problems.append("HF_HUB_OFFLINE non vale 1: le librerie Hugging Face potrebbero tentare download")
    if a.node:
        cfg = load_node_config(Path(a.node))
        for u in check_urls(cfg.urls(), cfg.allow_public_urls):
            problems.append(f"nodo {cfg.node_id}: URL fuori LAN {u}")
        if not cfg.clients:
            problems.append(f"nodo {cfg.node_id}: nessun client configurato, API aperta a chiunque in LAN")
    if a.orchestrator:
        cfg = load_orchestrator_config(Path(a.orchestrator))
        for u in check_urls(cfg.urls(), cfg.allow_public_urls):
            problems.append(f"orchestratore: URL fuori LAN {u}")
        if not cfg.clients:
            problems.append("orchestratore: nessun client configurato, API aperta a chiunque in LAN")
    if problems:
        print("Controlli offline: attenzione")
        for p in problems:
            print(f" - {p}")
        return 1
    print("Controlli offline: tutto in ordine")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alveare", description="Rete locale offline di modelli IA aperti")
    sub = p.add_subparsers(dest="cmd", required=True)

    keys = sub.add_parser("keys").add_subparsers(dest="sub", required=True)
    k = keys.add_parser("gen")
    k.add_argument("--owner", required=True)
    k.add_argument("--out", required=True)
    k.set_defaults(func=cmd_keys_gen)

    bundle = sub.add_parser("bundle").add_subparsers(dest="sub", required=True)
    b = bundle.add_parser("build")
    b.add_argument("--manifest", required=True)
    b.add_argument("--files", nargs="+", required=True)
    b.add_argument("--key", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_bundle_build)
    b = bundle.add_parser("verify")
    b.add_argument("bundle")
    b.add_argument("--trusted", required=True)
    b.set_defaults(func=cmd_bundle_verify)

    reg = sub.add_parser("registry").add_subparsers(dest="sub", required=True)
    r = reg.add_parser("add")
    r.add_argument("bundle")
    r.add_argument("--registry", required=True)
    r.add_argument("--trusted", required=True)
    r.add_argument("--replace", action="store_true")
    r.set_defaults(func=cmd_registry_add)
    r = reg.add_parser("list")
    r.add_argument("--registry", required=True)
    r.add_argument("--trusted", required=True)
    r.set_defaults(func=cmd_registry_list)

    m = sub.add_parser("mock-backend")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8080)
    m.add_argument("--delay", type=float, default=0.0)
    m.set_defaults(func=cmd_mock_backend)

    for name, func in (("node", cmd_node_serve), ("orchestrator", cmd_orchestrator_serve)):
        s = sub.add_parser(name).add_subparsers(dest="sub", required=True)
        sv = s.add_parser("serve")
        sv.add_argument("--config", required=True)
        sv.add_argument("--host")
        sv.add_argument("--port", type=int)
        sv.set_defaults(func=func)

    for name, func in (("nodes", cmd_nodes),):
        n = sub.add_parser(name)
        n.add_argument("--orchestrator", default="http://127.0.0.1:8100")
        n.add_argument("--api-key-env", default="ALVEARE_CLIENT_KEY")
        n.set_defaults(func=func)

    rr = sub.add_parser("run")
    rr.add_argument("recipe")
    rr.add_argument("--orchestrator", default="http://127.0.0.1:8100")
    rr.add_argument("--input", action="append", help="nome=valore oppure nome=@file.txt")
    rr.add_argument("--api-key-env", default="ALVEARE_CLIENT_KEY")
    rr.add_argument("--json", action="store_true")
    rr.set_defaults(func=cmd_run)

    t = sub.add_parser("task")
    t.add_argument("task")
    t.add_argument("--text", required=True)
    t.add_argument("--orchestrator", default="http://127.0.0.1:8100")
    t.add_argument("--api-key-env", default="ALVEARE_CLIENT_KEY")
    t.set_defaults(func=cmd_task)

    v = sub.add_parser("validate")
    v.add_argument("--url", required=True, help="URL di un nodo o dell'orchestratore")
    v.add_argument("--task", required=True)
    v.add_argument("--cases", required=True)
    v.add_argument("--signing-key", required=True)
    v.add_argument("--bundle", required=True, help="etichetta del candidato, es. alveare/riassunto-it@0.1.0")
    v.add_argument("--out", required=True)
    v.add_argument("--api-key-env", default="ALVEARE_CLIENT_KEY")
    v.set_defaults(func=cmd_validate)

    sc = sub.add_parser("score").add_subparsers(dest="sub", required=True)
    s1 = sc.add_parser("verify")
    s1.add_argument("report")
    s1.add_argument("--trusted", required=True)
    s1.set_defaults(func=cmd_score_verify)
    s2 = sc.add_parser("aggregate")
    s2.add_argument("reports", nargs="+")
    s2.add_argument("--trusted", required=True)
    s2.set_defaults(func=cmd_score_aggregate)

    d = sub.add_parser("doctor")
    d.add_argument("--node")
    d.add_argument("--orchestrator")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
