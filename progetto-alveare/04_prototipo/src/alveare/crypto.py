"""Chiavi Ed25519, firma e verifica offline.

Le chiavi sono salvate come piccoli file JSON:
- privata:  {"kty": "Ed25519", "key_id": ..., "owner": ..., "private": base64}
- pubblica: {"kty": "Ed25519", "key_id": ..., "owner": ..., "public": base64}

La verifica non richiede rete: basta la chiave pubblica del progetto,
distribuita insieme al launcher o copiata nella cartella delle chiavi fidate.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json(obj) -> bytes:
    """Serializzazione deterministica usata per tutto ciò che viene firmato."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def key_id_for(public_raw: bytes) -> str:
    return hashlib.sha256(public_raw).hexdigest()[:16]


def _raw_public(pub: Ed25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


@dataclass
class PublicKey:
    key_id: str
    owner: str
    raw: bytes

    def verify(self, data: bytes, signature_b64: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(self.raw).verify(_b64d(signature_b64), data)
            return True
        except (InvalidSignature, ValueError):
            return False

    def to_dict(self) -> dict:
        return {"kty": "Ed25519", "key_id": self.key_id, "owner": self.owner, "public": _b64e(self.raw)}


@dataclass
class KeyPair:
    key_id: str
    owner: str
    private: Ed25519PrivateKey

    @property
    def public(self) -> PublicKey:
        return PublicKey(self.key_id, self.owner, _raw_public(self.private.public_key()))

    def sign(self, data: bytes) -> str:
        return _b64e(self.private.sign(data))

    def save(self, directory: Path, name: str | None = None) -> tuple[Path, Path]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stem = name or self.owner
        priv_path = directory / f"{stem}.key.json"
        pub_path = directory / f"{stem}.pub.json"
        raw_priv = self.private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        priv_path.write_text(
            json.dumps(
                {"kty": "Ed25519", "key_id": self.key_id, "owner": self.owner, "private": _b64e(raw_priv)},
                indent=2,
            )
        )
        try:
            os.chmod(priv_path, 0o600)
        except OSError:
            pass
        pub_path.write_text(json.dumps(self.public.to_dict(), indent=2))
        return priv_path, pub_path


def generate_keypair(owner: str) -> KeyPair:
    priv = Ed25519PrivateKey.generate()
    return KeyPair(key_id_for(_raw_public(priv.public_key())), owner, priv)


def load_private(path: Path) -> KeyPair:
    data = json.loads(Path(path).read_text())
    priv = Ed25519PrivateKey.from_private_bytes(_b64d(data["private"]))
    kid = key_id_for(_raw_public(priv.public_key()))
    if data.get("key_id") and data["key_id"] != kid:
        raise ValueError(f"key_id incoerente nel file {path}")
    return KeyPair(kid, data.get("owner", "sconosciuto"), priv)


def load_public(path: Path) -> PublicKey:
    data = json.loads(Path(path).read_text())
    raw = _b64d(data["public"])
    kid = key_id_for(raw)
    if data.get("key_id") and data["key_id"] != kid:
        raise ValueError(f"key_id incoerente nel file {path}")
    return PublicKey(kid, data.get("owner", "sconosciuto"), raw)


def load_trusted_keys(directory: Path | None) -> dict[str, PublicKey]:
    """Carica tutte le chiavi pubbliche *.pub.json di una cartella."""
    keys: dict[str, PublicKey] = {}
    if directory is None:
        return keys
    directory = Path(directory)
    if not directory.exists():
        return keys
    for p in sorted(directory.glob("*.pub.json")):
        k = load_public(p)
        keys[k.key_id] = k
    return keys
