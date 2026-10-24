"""Configurazioni di nodo e orchestratore, autenticazione e politica di rete.

Politica di rete: in modalità offline ogni URL configurato deve puntare alla
rete locale (IP privati, loopback, link-local, nomi a etichetta singola o
domini .local/.lan/.internal/.home.arpa). Un URL pubblico blocca l'avvio,
salvo `allow_public_urls: true` esplicito.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

import yaml
from fastapi import HTTPException
from pydantic import BaseModel, Field

LAN_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa")


# --------------------------------------------------------------------------- rete

def is_lan_url(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    host = host.lower()
    if host == "localhost" or "." not in host:
        return True
    return host.endswith(LAN_SUFFIXES)


def check_urls(urls: list[str], allow_public: bool = False) -> list[str]:
    """Restituisce l'elenco delle violazioni (vuoto se tutto è in LAN)."""
    if allow_public:
        return []
    return [u for u in urls if not is_lan_url(u)]


# --------------------------------------------------------------------- autenticazione

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ClientKey(BaseModel):
    id: str
    api_key_sha256: str


def authenticate(authorization: str | None, clients: list[ClientKey]) -> str:
    """Restituisce l'id del client. Senza client configurati la rete è aperta (solo sviluppo)."""
    if not clients:
        return "anonimo"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="chiave API mancante")
    digest = hash_key(authorization.split(" ", 1)[1].strip())
    for c in clients:
        if c.api_key_sha256 == digest:
            return c.id
    raise HTTPException(status_code=401, detail="chiave API non valida")


def resolve_secret(value: str | None, env: str | None) -> str | None:
    if env:
        return os.environ.get(env)
    return value


# ------------------------------------------------------------------------- nodo

class BackendSpec(BaseModel):
    url: str  # base OpenAI-compatibile, es. http://127.0.0.1:8080/v1 (llama-swap o llama-server)
    model: str
    api_key_env: str | None = None
    timeout_s: float = 180.0


class NodeTask(BaseModel):
    name: str
    description: str = ""
    bundle: str | None = None  # es. "alveare/riassunto-it@0.1.0"; None = backend senza bundle (solo sviluppo)
    backend: BackendSpec
    system_prompt: str | None = None  # se assente si usa quello del manifest
    max_tokens: int = 1024
    temperature: float = 0.2
    allowed_clients: list[str] = Field(default_factory=lambda: ["*"])
    max_concurrency: int = 2


class NodeConfig(BaseModel):
    node_id: str
    advertise_url: str
    listen_host: str = "0.0.0.0"
    listen_port: int = 8101
    registry: str | None = None
    trusted_keys: str | None = None
    require_signed_bundles: bool = True
    allow_public_urls: bool = False
    clients: list[ClientKey] = Field(default_factory=list)
    tasks: list[NodeTask]

    def urls(self) -> list[str]:
        return [self.advertise_url] + [t.backend.url for t in self.tasks]


# ---------------------------------------------------------------- orchestratore

class NodeRef(BaseModel):
    url: str
    api_key: str | None = None  # solo sviluppo; in produzione usare api_key_env
    api_key_env: str | None = None


class OrchestratorConfig(BaseModel):
    orchestrator_id: str = "orchestratore"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8100
    nodes: list[NodeRef]
    recipes_dir: str | None = None
    clients: list[ClientKey] = Field(default_factory=list)
    max_attempts: int = 2
    card_ttl_s: float = 30.0
    request_timeout_s: float = 300.0
    allow_public_urls: bool = False

    def urls(self) -> list[str]:
        return [n.url for n in self.nodes]


# --------------------------------------------------------------------- caricamento

def _resolve_paths(data: dict, base: Path, keys: tuple[str, ...]) -> dict:
    for k in keys:
        if data.get(k) and not Path(data[k]).is_absolute():
            data[k] = str((base / data[k]).resolve())
    return data


def load_node_config(path: Path) -> NodeConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    data = _resolve_paths(data, path.parent, ("registry", "trusted_keys"))
    return NodeConfig.model_validate(data)


def load_orchestrator_config(path: Path) -> OrchestratorConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    data = _resolve_paths(data, path.parent, ("recipes_dir",))
    return OrchestratorConfig.model_validate(data)
