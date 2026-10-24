"""Orchestratore della rete locale.

- legge le agent card dei nodi configurati e costruisce la mappa compito -> nodi;
- esegue ricette (grafo di passi) inviando i passi ai nodi in parallelo;
- sceglie il nodo meno carico che offre il compito e riprova su un altro nodo
  in caso di errore;
- espone anche il singolo compito come API (/v1/tasks/{task}).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .config import OrchestratorConfig, authenticate, check_urls, resolve_secret
from .recipes import Recipe, RecipeError, load_recipes, run_recipe

log = logging.getLogger("alveare.orchestrator")

ClientFactory = Callable[[], httpx.AsyncClient]


class NoNodeForTask(Exception):
    pass


@dataclass
class NodeState:
    url: str
    api_key: str | None
    card: dict | None = None
    tasks: set[str] = field(default_factory=set)
    inflight: int = 0
    failures: int = 0
    healthy: bool = False
    last_refresh: float = 0.0
    last_error: str | None = None

    def summary(self) -> dict:
        return {
            "url": self.url,
            "name": (self.card or {}).get("name"),
            "healthy": self.healthy,
            "tasks": sorted(self.tasks),
            "inflight": self.inflight,
            "failures": self.failures,
            "last_error": self.last_error,
        }


class NodePool:
    def __init__(self, cfg: OrchestratorConfig, client_factory: ClientFactory):
        self.cfg = cfg
        self.client_factory = client_factory
        self.nodes = [NodeState(n.url.rstrip("/"), resolve_secret(n.api_key, n.api_key_env)) for n in cfg.nodes]
        self._lock = asyncio.Lock()

    async def _fetch_card(self, client: httpx.AsyncClient, node: NodeState) -> None:
        try:
            r = await client.get(f"{node.url}/.well-known/agent.json", timeout=10.0)
            r.raise_for_status()
            card = r.json()
            node.card = card
            node.tasks = {s["id"] for s in card.get("skills", []) if s.get("enabled", True)}
            node.healthy = True
            node.last_error = None
        except (httpx.HTTPError, ValueError, KeyError) as e:
            node.healthy = False
            node.tasks = set()
            node.last_error = f"agent card non raggiungibile: {e}"
        node.last_refresh = time.monotonic()

    async def refresh(self, force: bool = False) -> None:
        async with self._lock:
            now = time.monotonic()
            stale = [n for n in self.nodes if force or now - n.last_refresh > self.cfg.card_ttl_s]
            if not stale:
                return
            async with self.client_factory() as client:
                await asyncio.gather(*(self._fetch_card(client, n) for n in stale))

    def capabilities(self) -> dict[str, list[str]]:
        caps: dict[str, list[str]] = {}
        for n in self.nodes:
            if n.healthy:
                for t in n.tasks:
                    caps.setdefault(t, []).append(n.url)
        return caps

    def candidates(self, task: str, exclude: set[str]) -> list[NodeState]:
        nodes = [n for n in self.nodes if n.healthy and task in n.tasks and n.url not in exclude]
        return sorted(nodes, key=lambda n: (n.inflight, n.failures))

    async def call(self, task: str, text: str, params: dict) -> tuple[str, dict]:
        await self.refresh()
        tried: set[str] = set()
        errors: list[str] = []
        for attempt in range(1, self.cfg.max_attempts + 1):
            cands = self.candidates(task, tried)
            if not cands:
                break
            node = cands[0]
            tried.add(node.url)
            headers = {"Authorization": f"Bearer {node.api_key}"} if node.api_key else {}
            node.inflight += 1
            t0 = time.perf_counter()
            try:
                async with self.client_factory() as client:
                    r = await client.post(
                        f"{node.url}/v1/tasks/{task}",
                        json={"input": text, "params": params},
                        headers=headers,
                        timeout=self.cfg.request_timeout_s,
                    )
                if r.status_code >= 400:
                    raise httpx.HTTPStatusError(f"{r.status_code}: {r.text[:200]}", request=r.request, response=r)
                data = r.json()
                entry = {
                    "task": task,
                    "node": (node.card or {}).get("name", node.url),
                    "attempt": attempt,
                    "ms": int((time.perf_counter() - t0) * 1000),
                    "ok": True,
                    "bundle": data.get("bundle"),
                }
                return data["output"], entry
            except (httpx.HTTPError, ValueError, KeyError) as e:
                node.failures += 1
                node.last_error = str(e)
                errors.append(f"{node.url}: {e}")
                log.warning("tentativo %d per '%s' fallito su %s: %s", attempt, task, node.url, e)
                if isinstance(e, httpx.TransportError):
                    node.healthy = False  # sarà ricontrollato al prossimo refresh
            finally:
                node.inflight -= 1
        if not errors:
            raise NoNodeForTask(f"nessun nodo disponibile offre il compito '{task}'")
        raise NoNodeForTask(f"compito '{task}' fallito su tutti i nodi provati: {errors}")


class RunRequest(BaseModel):
    recipe: str | dict
    inputs: dict = Field(default_factory=dict)


class TaskRequest(BaseModel):
    input: str
    params: dict = Field(default_factory=dict)


def _default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(300.0))


def create_orchestrator_app(cfg: OrchestratorConfig, client_factory: ClientFactory | None = None) -> FastAPI:
    violations = check_urls(cfg.urls(), cfg.allow_public_urls)
    if violations:
        raise RuntimeError(f"URL fuori dalla rete locale: {violations} (modalità offline)")
    pool = NodePool(cfg, client_factory or _default_client_factory)
    recipes: dict[str, Recipe] = load_recipes(cfg.recipes_dir)
    app = FastAPI(title=f"Alveare - {cfg.orchestrator_id}", version=__version__)
    app.state.pool = pool
    app.state.recipes = recipes

    @app.get("/health")
    async def health():
        return {"status": "ok", "orchestrator_id": cfg.orchestrator_id}

    @app.get("/nodes")
    async def nodes(authorization: str | None = Header(default=None)):
        authenticate(authorization, cfg.clients)
        await pool.refresh()
        return {"nodes": [n.summary() for n in pool.nodes], "capabilities": pool.capabilities()}

    @app.post("/nodes/refresh")
    async def refresh_nodes(authorization: str | None = Header(default=None)):
        authenticate(authorization, cfg.clients)
        await pool.refresh(force=True)
        return {"capabilities": pool.capabilities()}

    @app.get("/recipes")
    async def list_recipes(authorization: str | None = Header(default=None)):
        authenticate(authorization, cfg.clients)
        await pool.refresh()
        caps = pool.capabilities()
        return {
            "recipes": [
                {
                    "name": r.name,
                    "description": r.description,
                    "inputs": r.inputs,
                    "missing_tasks": sorted(t for t in r.task_names() if t not in caps),
                }
                for r in recipes.values()
            ]
        }

    @app.post("/v1/run")
    async def run(req: RunRequest, authorization: str | None = Header(default=None)):
        authenticate(authorization, cfg.clients)
        if isinstance(req.recipe, str):
            recipe = recipes.get(req.recipe)
            if recipe is None:
                raise HTTPException(status_code=404, detail=f"ricetta '{req.recipe}' non trovata")
        else:
            try:
                recipe = Recipe.model_validate(req.recipe)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        try:
            result = await run_recipe(recipe, req.inputs, pool)
        except (RecipeError, NoNodeForTask) as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return result.model_dump()

    @app.post("/v1/tasks/{task}")
    async def task(task: str, req: TaskRequest, authorization: str | None = Header(default=None)):
        authenticate(authorization, cfg.clients)
        try:
            output, entry = await pool.call(task, req.input, req.params)
        except NoNodeForTask as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"output": output, "trace": [entry]}

    return app
