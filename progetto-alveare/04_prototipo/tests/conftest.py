"""Fixture comuni: una rete locale completa simulata in memoria (nessuna porta aperta).

backend finto  <-  nodo-a (traduzione-it-en, riassunto-it)
backend finto  <-  nodo-b (traduzione-it-en, correzione-it)
orchestratore  ->  nodo-a, nodo-b
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from alveare.bundle import build_bundle
from alveare.config import ClientKey, NodeConfig, OrchestratorConfig, hash_key
from alveare.crypto import generate_keypair
from alveare.mock_backend import create_mock_backend
from alveare.node import create_node_app
from alveare.orchestrator import create_orchestrator_app
from alveare.registry import Registry

NODE_KEY = "chiave-orchestratore-di-test"
CLIENT_KEY = "chiave-client-di-test"

MANIFESTS = {
    "traduzione-it-en": {
        "description": "Traduzione italiano -> inglese",
        "system_prompt": "TRADUCI dall'italiano all'inglese mantenendo i termini tecnici.",
    },
    "riassunto-it": {
        "description": "Riassunto in italiano",
        "system_prompt": "RIASSUMI il testo in italiano in poche frasi.",
    },
    "correzione-it": {
        "description": "Correzione ortografica e di punteggiatura",
        "system_prompt": "CORREGGI ortografia e punteggiatura senza cambiare il senso.",
    },
}


def make_factory(mounts: dict):
    """Client HTTP che instrada gli host fittizi verso app ASGI in memoria."""

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            mounts={host: httpx.ASGITransport(app=app) for host, app in mounts.items()},
            timeout=30.0,
        )

    return factory


@pytest.fixture
def lab(tmp_path: Path):
    keys_dir = tmp_path / "chiavi"
    trusted = tmp_path / "fidate"
    trusted.mkdir()
    publisher = generate_keypair("progetto-alveare")
    _, pub = publisher.save(keys_dir)
    (trusted / pub.name).write_text(pub.read_text())

    model_file = tmp_path / "modello-finto.gguf"
    model_file.write_bytes(b"GGUF-DEMO" * 100)
    registry = Registry(tmp_path / "registro", trusted)
    for name, spec in MANIFESTS.items():
        mpath = tmp_path / f"{name}.yaml"
        mpath.write_text(yaml.safe_dump({
            "publisher": "alveare", "name": name, "version": "0.1.0", "license": "Apache-2.0",
            "description": spec["description"],
            "tasks": [{"name": name, "kind": "chat", "system_prompt": spec["system_prompt"]}],
            "runtime": {"engine": "llama.cpp", "quantization": "Q4_K_M"},
        }))
        bdir = build_bundle(mpath, [model_file], tmp_path / "build", publisher)
        registry.add(bdir)

    mounts: dict = {}
    factory = make_factory(mounts)

    def node_cfg(node_id: str, tasks: list[str], backend_host: str = "http://backend") -> NodeConfig:
        return NodeConfig(
            node_id=node_id,
            advertise_url=f"http://{node_id}",
            registry=str(tmp_path / "registro"),
            trusted_keys=str(trusted),
            clients=[ClientKey(id="orchestratore", api_key_sha256=hash_key(NODE_KEY))],
            tasks=[{"name": t, "bundle": f"alveare/{t}@0.1.0",
                    "backend": {"url": f"{backend_host}/v1", "model": "finto"}, "max_concurrency": 4}
                   for t in tasks],
        )

    mounts["http://backend"] = create_mock_backend(delay_s=0.05)
    mounts["http://backend-guasto"] = create_mock_backend(fail=True)

    def build_network(node_b_backend: str = "http://backend"):
        mounts["http://nodo-a"] = create_node_app(node_cfg("nodo-a", ["traduzione-it-en", "riassunto-it"]), factory)
        mounts["http://nodo-b"] = create_node_app(
            node_cfg("nodo-b", ["traduzione-it-en", "correzione-it"], node_b_backend), factory)
        ocfg = OrchestratorConfig(
            nodes=[{"url": "http://nodo-a", "api_key": NODE_KEY}, {"url": "http://nodo-b", "api_key": NODE_KEY}],
            recipes_dir=str(Path(__file__).resolve().parent.parent / "examples" / "recipes"),
            clients=[ClientKey(id="ufficio", api_key_sha256=hash_key(CLIENT_KEY))],
        )
        orch = create_orchestrator_app(ocfg, factory)
        mounts["http://orchestratore"] = orch
        return orch

    return {
        "tmp": tmp_path,
        "trusted": trusted,
        "publisher": publisher,
        "registry": registry,
        "factory": factory,
        "mounts": mounts,
        "node_cfg": node_cfg,
        "build_network": build_network,
    }


def client_for(app, base: str = "http://orchestratore", key: str | None = CLIENT_KEY) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base, headers=headers, timeout=30.0)
