"""Backend finto, compatibile con l'API OpenAI /v1/chat/completions.

Serve per provare la rete senza scaricare modelli. Il comportamento dipende
dal prompt di sistema del compito:
- contiene "TRADUCI"  -> restituisce "[EN] " + testo
- contiene "RIASSUMI" -> prima frase del testo + " [...]"
- contiene "CORREGGI" -> testo con spazi normalizzati e iniziale maiuscola
- altrimenti          -> eco del testo

Per usare modelli veri basta puntare i nodi a llama-server o llama-swap.
"""

from __future__ import annotations

import asyncio
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _transform(system: str, text: str) -> str:
    s = system.upper()
    if "TRADUCI" in s:
        return "[EN] " + text.strip()
    if "RIASSUMI" in s:
        first = re.split(r"(?<=[\.\!\?])\s+", text.strip(), maxsplit=1)[0]
        return first + " [...]"
    if "CORREGGI" in s:
        fixed = re.sub(r"[ \t]+", " ", text.strip())
        fixed = re.sub(r"\s+([,\.;:\!\?])", r"\1", fixed)
        return fixed[:1].upper() + fixed[1:]
    return text


def create_mock_backend(delay_s: float = 0.0, fail: bool = False) -> FastAPI:
    app = FastAPI(title="Alveare - backend finto")

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": "finto", "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        if fail:
            return JSONResponse({"error": "guasto simulato"}, status_code=500)
        if delay_s:
            await asyncio.sleep(delay_s)
        messages = body.get("messages", [])
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        out = _transform(system, user)
        return {
            "id": f"finto-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "model": body.get("model", "finto"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": out}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(user.split()), "completion_tokens": len(out.split())},
        }

    return app
