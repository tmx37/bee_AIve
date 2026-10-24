"""Nodo della rete locale.

Un nodo espone uno o più *compiti* (es. "riassunto-it"). Ogni compito è legato
a un bundle verificato del registro locale e a un backend OpenAI-compatibile
(llama-server, llama-swap, vLLM...). Il nodo pubblica le proprie capacità in
una agent card ispirata ad A2A su /.well-known/agent.json.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .bundle import VerificationError
from .config import NodeConfig, authenticate, check_urls, resolve_secret
from .registry import Registry

log = logging.getLogger("alveare.node")

ClientFactory = Callable[[], httpx.AsyncClient]


class TaskRequest(BaseModel):
    input: str
    params: dict = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task: str
    node_id: str
    output: str
    model: str
    bundle: str | None
    latency_ms: int
    usage: dict = Field(default_factory=dict)


class TaskState(BaseModel):
    enabled: bool
    reason: str = ""
    system_prompt: str = ""
    tags: list[str] = Field(default_factory=list)
    kind: str = "chat"


def _default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(300.0))


def _prepare_tasks(cfg: NodeConfig) -> dict[str, TaskState]:
    states: dict[str, TaskState] = {}
    registry = Registry(cfg.registry, cfg.trusted_keys) if cfg.registry else None
    for t in cfg.tasks:
        if t.bundle is None:
            if cfg.require_signed_bundles:
                states[t.name] = TaskState(enabled=False, reason="nessun bundle firmato associato")
            else:
                states[t.name] = TaskState(enabled=True, system_prompt=t.system_prompt or "",
                                           reason="modalità sviluppo: nessun bundle")
            continue
        if registry is None:
            states[t.name] = TaskState(enabled=False, reason="registro locale non configurato")
            continue
        try:
            manifest = registry.get(t.bundle)
        except VerificationError as e:
            states[t.name] = TaskState(enabled=False, reason=f"bundle non valido: {e}")
            continue
        spec = manifest.task(t.name) or (manifest.tasks[0] if manifest.tasks else None)
        states[t.name] = TaskState(
            enabled=True,
            system_prompt=t.system_prompt or (spec.system_prompt if spec else ""),
            tags=spec.tags if spec else [],
            kind=spec.kind if spec else "chat",
        )
    return states


def create_node_app(cfg: NodeConfig, client_factory: ClientFactory | None = None) -> FastAPI:
    violations = check_urls(cfg.urls(), cfg.allow_public_urls)
    if violations:
        raise RuntimeError(f"URL fuori dalla rete locale: {violations} (modalità offline)")
    client_factory = client_factory or _default_client_factory
    tasks = {t.name: t for t in cfg.tasks}
    states = _prepare_tasks(cfg)
    semaphores = {t.name: asyncio.Semaphore(t.max_concurrency) for t in cfg.tasks}
    for name, st in states.items():
        if not st.enabled:
            log.warning("compito %s disabilitato: %s", name, st.reason)

    app = FastAPI(title=f"Alveare - nodo {cfg.node_id}", version=__version__)

    @app.get("/health")
    async def health():
        return {"status": "ok", "node_id": cfg.node_id,
                "tasks": {k: v.enabled for k, v in states.items()}}

    @app.get("/.well-known/agent.json")
    async def agent_card():
        return {
            "name": cfg.node_id,
            "description": f"Nodo Alveare {cfg.node_id}",
            "url": cfg.advertise_url,
            "version": __version__,
            "protocol": "alveare/0.1 (agent card ispirata ad A2A)",
            "capabilities": {"streaming": False},
            "authentication": {"schemes": ["bearer"] if cfg.clients else []},
            "skills": [
                {
                    "id": t.name,
                    "name": t.name,
                    "description": t.description,
                    "kind": states[t.name].kind,
                    "tags": states[t.name].tags,
                    "bundle": t.bundle,
                    "enabled": states[t.name].enabled,
                    "reason": states[t.name].reason,
                    "max_concurrency": t.max_concurrency,
                }
                for t in cfg.tasks
            ],
        }

    @app.post("/v1/tasks/{task}", response_model=TaskResponse)
    async def run_task(task: str, req: TaskRequest, authorization: str | None = Header(default=None)):
        client_id = authenticate(authorization, cfg.clients)
        spec = tasks.get(task)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"compito '{task}' non offerto da questo nodo")
        if "*" not in spec.allowed_clients and client_id not in spec.allowed_clients:
            raise HTTPException(status_code=403, detail=f"client '{client_id}' non autorizzato per '{task}'")
        state = states[task]
        if not state.enabled:
            raise HTTPException(status_code=503, detail=f"compito disabilitato: {state.reason}")
        messages = []
        if state.system_prompt:
            messages.append({"role": "system", "content": state.system_prompt})
        messages.append({"role": "user", "content": req.input})
        body = {
            "model": spec.backend.model,
            "messages": messages,
            "max_tokens": int(req.params.get("max_tokens", spec.max_tokens)),
            "temperature": float(req.params.get("temperature", spec.temperature)),
        }
        headers = {}
        backend_key = resolve_secret(None, spec.backend.api_key_env)
        if backend_key:
            headers["Authorization"] = f"Bearer {backend_key}"
        url = spec.backend.url.rstrip("/") + "/chat/completions"
        t0 = time.perf_counter()
        async with semaphores[task]:
            try:
                async with client_factory() as client:
                    r = await client.post(url, json=body, headers=headers, timeout=spec.backend.timeout_s)
                r.raise_for_status()
                data = r.json()
                output = data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                raise HTTPException(status_code=502, detail=f"errore del backend: {e}") from e
        return TaskResponse(
            task=task,
            node_id=cfg.node_id,
            output=output,
            model=data.get("model", spec.backend.model),
            bundle=spec.bundle,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            usage=data.get("usage", {}),
        )

    return app
