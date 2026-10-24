"""Validazione locale e privata.

Un validatore esegue i propri casi di test (che non lascia mai la rete
locale) contro un compito, calcola il punteggio e produce un rapporto
firmato. Il rapporto contiene solo l'hash del file dei casi, non i casi:
così i test restano privati ma il validatore si impegna su un insieme preciso.

Formato dei casi (JSONL, una riga per caso):
    {"input": "...", "expected": "...", "metric": "chrf"}
    {"input": "...", "expected": ["parola1", "parola2"], "metric": "contains"}
Metriche: exact, contains, chrf.
"""

from __future__ import annotations

import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from . import __version__
from .crypto import KeyPair, PublicKey, canonical_json, sha256_file


def _ngrams(text: str, n: int) -> Counter:
    text = " ".join(text.split())
    return Counter(text[i:i + n] for i in range(max(len(text) - n + 1, 0)))


def chrf(hypothesis: str, reference: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF a caratteri (0-100), implementazione semplice senza dipendenze."""
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        h, r = _ngrams(hypothesis, n), _ngrams(reference, n)
        if not h or not r:
            continue
        overlap = sum((h & r).values())
        precisions.append(overlap / sum(h.values()))
        recalls.append(overlap / sum(r.values()))
    if not precisions:
        return 0.0
    p = sum(precisions) / len(precisions)
    rc = sum(recalls) / len(recalls)
    if p == 0 and rc == 0:
        return 0.0
    b2 = beta * beta
    return 100.0 * (1 + b2) * p * rc / (b2 * p + rc)


def score_case(output: str, expected, metric: str) -> float:
    if metric == "exact":
        return 100.0 if output.strip() == str(expected).strip() else 0.0
    if metric == "contains":
        needles = expected if isinstance(expected, list) else [expected]
        hits = sum(1 for n in needles if str(n).lower() in output.lower())
        return 100.0 * hits / len(needles)
    if metric == "chrf":
        return chrf(output, str(expected))
    raise ValueError(f"metrica sconosciuta: {metric}")


def load_cases(path: Path) -> list[dict]:
    cases = []
    for i, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        if "input" not in c or "expected" not in c:
            raise ValueError(f"riga {i}: servono i campi 'input' ed 'expected'")
        c.setdefault("metric", "chrf")
        cases.append(c)
    return cases


async def run_validation(
    base_url: str,
    task: str,
    cases_path: Path,
    api_key: str | None,
    client_factory: Callable[[], httpx.AsyncClient] | None = None,
) -> dict:
    cases = load_cases(cases_path)
    factory = client_factory or (lambda: httpx.AsyncClient(timeout=300.0))
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    scores: list[float] = []
    by_metric: dict[str, list[float]] = {}
    failures = 0
    async with factory() as client:
        for c in cases:
            try:
                r = await client.post(f"{base_url.rstrip('/')}/v1/tasks/{task}",
                                      json={"input": c["input"], "params": c.get("params", {})},
                                      headers=headers)
                r.raise_for_status()
                out = r.json()["output"]
                s = score_case(out, c["expected"], c["metric"])
            except (httpx.HTTPError, KeyError, ValueError):
                failures += 1
                s = 0.0
            scores.append(s)
            by_metric.setdefault(c["metric"], []).append(s)
    return {
        "n_cases": len(cases),
        "failures": failures,
        "score_mean": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "by_metric": {m: round(sum(v) / len(v), 2) for m, v in by_metric.items()},
    }


def make_score_report(result: dict, task: str, bundle_label: str, cases_path: Path, key: KeyPair) -> dict:
    payload = {
        "schema": "alveare.score/1",
        "task": task,
        "bundle": bundle_label,
        "result": result,
        "cases_sha256": sha256_file(Path(cases_path)),
        "device": {"system": platform.system(), "machine": platform.machine(),
                   "python": platform.python_version()},
        "tool_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validator_key_id": key.key_id,
    }
    return {"payload": payload, "signature": key.sign(canonical_json(payload))}


def verify_score_report(report: dict, trusted: dict[str, PublicKey]) -> bool:
    payload = report.get("payload", {})
    pub = trusted.get(payload.get("validator_key_id", ""))
    return bool(pub and pub.verify(canonical_json(payload), report.get("signature", "")))


def aggregate_reports(reports: list[dict], trusted: dict[str, PublicKey]) -> dict:
    """Aggregazione robusta: scarta i rapporti non firmati e usa la mediana."""
    valid = [r for r in reports if verify_score_report(r, trusted)]
    values = sorted(r["payload"]["result"]["score_mean"] for r in valid)
    if not values:
        return {"n_valid": 0, "n_rejected": len(reports), "median": None}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"n_valid": len(valid), "n_rejected": len(reports) - len(valid), "median": round(median, 2),
            "min": values[0], "max": values[-1]}
