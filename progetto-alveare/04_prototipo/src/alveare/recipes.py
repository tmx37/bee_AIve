"""Ricette: flussi di lavoro dichiarativi eseguiti come grafo di dipendenze.

Esempio (YAML):

    name: traduci-e-riassumi
    inputs: [testo]
    steps:
      - id: parti
        op: split
        input: "{{ inputs.testo }}"
        max_chars: 1200
      - id: traduzioni
        task: traduzione-it-en
        map: parti            # un'esecuzione per ogni parte, in parallelo
        input: "{{ item }}"
      - id: traduzione
        op: join
        from: traduzioni
      - id: sintesi
        task: riassunto-it
        input: "{{ inputs.testo }}"   # non dipende dalla traduzione: parte subito
    outputs:
      traduzione: traduzione
      sintesi: sintesi

Ogni passo parte appena sono pronti i passi da cui dipende, quindi rami
indipendenti e le esecuzioni di un `map` girano in parallelo.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

REF_RE = re.compile(r"\{\{\s*([A-Za-z_][\w\.\-]*)\s*\}\}")


class RecipeError(Exception):
    pass


class Step(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task: str | None = None
    op: Literal["split", "join"] | None = None
    input: str | None = None
    map: str | None = None
    from_: str | None = Field(default=None, alias="from")
    max_chars: int = 1500
    separator: str = "\n\n"
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.task is None) == (self.op is None):
            raise ValueError(f"passo '{self.id}': indica esattamente uno tra 'task' e 'op'")
        if self.op == "join" and not self.from_:
            raise ValueError(f"passo '{self.id}': 'join' richiede 'from'")
        if self.op == "split" and not self.input:
            raise ValueError(f"passo '{self.id}': 'split' richiede 'input'")
        if self.task and not self.input:
            raise ValueError(f"passo '{self.id}': un passo con 'task' richiede 'input'")
        return self


class Recipe(BaseModel):
    name: str
    description: str = ""
    inputs: list[str] = Field(default_factory=list)
    steps: list[Step]
    outputs: dict[str, str]

    @model_validator(mode="after")
    def _validate_graph(self):
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("id dei passi duplicati")
        known = set(ids)
        for s in self.steps:
            for dep in step_dependencies(s):
                if dep not in known:
                    raise ValueError(f"passo '{s.id}' fa riferimento a un passo inesistente: '{dep}'")
            for ref in _template_refs(s.input or ""):
                if ref.startswith("inputs.") and ref.split(".", 1)[1] not in self.inputs:
                    raise ValueError(f"passo '{s.id}' usa un input non dichiarato: '{ref}'")
        for out, sid in self.outputs.items():
            if sid not in known:
                raise ValueError(f"output '{out}' punta a un passo inesistente: '{sid}'")
        topological_order(self)  # solleva se c'è un ciclo
        return self

    def task_names(self) -> set[str]:
        return {s.task for s in self.steps if s.task}


def _template_refs(template: str) -> list[str]:
    return REF_RE.findall(template)


def step_dependencies(step: Step) -> set[str]:
    deps: set[str] = set()
    for ref in _template_refs(step.input or ""):
        if ref.startswith("steps."):
            deps.add(ref.split(".", 1)[1])
    if step.map:
        deps.add(step.map)
    if step.from_:
        deps.add(step.from_)
    return deps


def topological_order(recipe: Recipe) -> list[str]:
    deps = {s.id: step_dependencies(s) for s in recipe.steps}
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(deps):
        ready = [sid for sid, d in deps.items() if sid not in done and d <= done]
        if not ready:
            raise ValueError("la ricetta contiene un ciclo di dipendenze")
        for sid in ready:
            order.append(sid)
            done.add(sid)
    return order


def _as_text(value) -> str:
    if isinstance(value, list):
        return "\n\n".join(str(v) for v in value)
    return str(value)


def render(template: str, inputs: dict, results: dict, item=None, index: int | None = None) -> str:
    def repl(m: re.Match) -> str:
        ref = m.group(1)
        if ref == "item":
            return _as_text(item)
        if ref == "index":
            return str(index)
        scope, _, key = ref.partition(".")
        if scope == "inputs":
            return _as_text(inputs[key])
        if scope == "steps":
            return _as_text(results[key])
        raise RecipeError(f"riferimento sconosciuto: {ref}")

    return REF_RE.sub(repl, template)


def split_text(text: str, max_chars: int) -> list[str]:
    """Divide per paragrafi senza superare max_chars (salvo paragrafi più lunghi del limite)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(p) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[\.\!\?])\s+", p)
            buf = ""
            for s in sentences:
                if buf and len(buf) + 1 + len(s) > max_chars:
                    chunks.append(buf)
                    buf = s
                else:
                    buf = f"{buf} {s}".strip()
            if buf:
                chunks.append(buf)
            continue
        if current and len(current) + 2 + len(p) > max_chars:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


class Dispatcher(Protocol):
    async def call(self, task: str, text: str, params: dict) -> tuple[str, dict]:
        """Esegue un compito e restituisce (output, voce di traccia)."""


class RunResult(BaseModel):
    recipe: str
    outputs: dict
    trace: list[dict]
    elapsed_ms: int


async def run_recipe(recipe: Recipe, inputs: dict, dispatcher: Dispatcher) -> RunResult:
    missing = [k for k in recipe.inputs if k not in inputs]
    if missing:
        raise RecipeError(f"input mancanti: {missing}")
    loop = asyncio.get_running_loop()
    futures: dict[str, asyncio.Future] = {s.id: loop.create_future() for s in recipe.steps}
    results: dict = {}
    trace: list[dict] = []
    t0 = time.perf_counter()

    async def call(step: Step, text: str, index: int | None):
        out, entry = await dispatcher.call(step.task, text, step.params)
        entry = {"step": step.id, "index": index, **entry}
        trace.append(entry)
        return out

    async def run_step(step: Step):
        try:
            for dep in step_dependencies(step):
                await futures[dep]
            if step.op == "split":
                value = split_text(render(step.input, inputs, results), step.max_chars)
            elif step.op == "join":
                src = results[step.from_]
                value = step.separator.join(src) if isinstance(src, list) else str(src)
            elif step.map:
                items = results[step.map]
                if not isinstance(items, list):
                    items = [items]
                value = await asyncio.gather(*[
                    call(step, render(step.input, inputs, results, item=it, index=i), i)
                    for i, it in enumerate(items)
                ])
                value = list(value)
            else:
                value = await call(step, render(step.input, inputs, results), None)
            results[step.id] = value
            futures[step.id].set_result(True)
        except BaseException as e:  # propaga il fallimento ai passi dipendenti
            if not futures[step.id].done():
                futures[step.id].set_exception(e)
            raise

    outcomes = await asyncio.gather(*(run_step(s) for s in recipe.steps), return_exceptions=True)
    for f in futures.values():  # evita avvisi su eccezioni non lette
        if f.done() and not f.cancelled():
            f.exception()
    errors = [o for o in outcomes if isinstance(o, BaseException)]
    if errors:
        root = errors[0]
        raise RecipeError(f"ricetta '{recipe.name}' fallita: {root}") from root
    return RunResult(
        recipe=recipe.name,
        outputs={k: results[v] for k, v in recipe.outputs.items()},
        trace=sorted(trace, key=lambda e: (e["step"], e["index"] if e["index"] is not None else -1)),
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


def load_recipe(path: Path) -> Recipe:
    return Recipe.model_validate(yaml.safe_load(Path(path).read_text()))


def load_recipes(directory: Path | None) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    if directory is None or not Path(directory).exists():
        return recipes
    for p in sorted(Path(directory).glob("*.y*ml")):
        r = load_recipe(p)
        recipes[r.name] = r
    return recipes
