"""Bundle di modello firmati.

Struttura di un bundle (una cartella):

    <publisher>__<name>__<version>/
        manifest.json     # metadati + hash SHA-256 di ogni file
        signature.json    # firma Ed25519 del manifest in forma canonica
        files/            # pesi del modello e file accessori

La verifica controlla: chiave fidata, firma, licenza ammessa, hash e
dimensione di ogni file, assenza di file non dichiarati.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from .crypto import KeyPair, PublicKey, canonical_json, sha256_file

# Licenze approvate OSI ammesse di default per pesi e codice.
OSI_LICENSES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "ISC"}

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([\-+][0-9A-Za-z\.\-]+)?$")


class VerificationError(Exception):
    """Il bundle non supera la verifica e non deve essere caricato."""


class TaskSpec(BaseModel):
    name: str
    kind: Literal["chat", "completion", "embedding", "image", "speech-to-text", "text-to-speech"] = "chat"
    description: str = ""
    system_prompt: str = ""
    tags: list[str] = Field(default_factory=list)


class RuntimeSpec(BaseModel):
    engine: str = "llama.cpp"
    model_alias: str | None = None
    quantization: str | None = None
    min_ram_gb: float | None = None
    device_classes: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    schema_version: int = 1
    publisher: str
    name: str
    version: str
    license: str
    description: str = ""
    base_model: str | None = None
    tasks: list[TaskSpec]
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)
    eval: dict = Field(default_factory=dict)
    files: dict[str, dict] = Field(default_factory=dict)

    @field_validator("publisher", "name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("usa solo minuscole, cifre e trattini (max 64 caratteri)")
        return v

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if not _VERSION_RE.match(v):
            raise ValueError("versione non in formato semver (es. 0.1.0)")
        return v

    @property
    def bundle_id(self) -> str:
        return f"{self.publisher}/{self.name}@{self.version}"

    def task(self, name: str) -> TaskSpec | None:
        for t in self.tasks:
            if t.name == name:
                return t
        return None


def bundle_dirname(bundle_id: str) -> str:
    return bundle_id.replace("/", "__").replace("@", "__")


def load_manifest_source(path: Path) -> Manifest:
    text = Path(path).read_text()
    data = yaml.safe_load(text) if str(path).endswith((".yaml", ".yml")) else json.loads(text)
    return Manifest.model_validate(data)


def build_bundle(
    manifest_path: Path,
    files: list[Path],
    out_dir: Path,
    key: KeyPair,
    allowed_licenses: set[str] = OSI_LICENSES,
) -> Path:
    manifest = load_manifest_source(manifest_path)
    if manifest.license not in allowed_licenses:
        raise VerificationError(
            f"licenza '{manifest.license}' non ammessa; consentite: {sorted(allowed_licenses)}"
        )
    target = Path(out_dir) / bundle_dirname(manifest.bundle_id)
    if target.exists():
        shutil.rmtree(target)
    (target / "files").mkdir(parents=True)
    entries: dict[str, dict] = {}
    for src in files:
        src = Path(src)
        if not src.is_file():
            raise FileNotFoundError(src)
        dst = target / "files" / src.name
        shutil.copy2(src, dst)
        entries[src.name] = {"sha256": sha256_file(dst), "size": dst.stat().st_size}
    manifest.files = entries
    data = manifest.model_dump()
    (target / "manifest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    signature = {
        "alg": "ed25519",
        "key_id": key.key_id,
        "signer": key.owner,
        "signed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signature": key.sign(canonical_json(data)),
    }
    (target / "signature.json").write_text(json.dumps(signature, indent=2))
    return target


def verify_bundle(
    bundle_dir: Path,
    trusted: dict[str, PublicKey],
    allowed_licenses: set[str] = OSI_LICENSES,
) -> Manifest:
    bundle_dir = Path(bundle_dir)
    try:
        data = json.loads((bundle_dir / "manifest.json").read_text())
        sig = json.loads((bundle_dir / "signature.json").read_text())
    except FileNotFoundError as e:
        raise VerificationError(f"file mancante nel bundle: {e.filename}") from e
    if sig.get("alg") != "ed25519":
        raise VerificationError("algoritmo di firma non supportato")
    pub = trusted.get(sig.get("key_id", ""))
    if pub is None:
        raise VerificationError(f"chiave {sig.get('key_id')} non presente tra le chiavi fidate")
    if not pub.verify(canonical_json(data), sig.get("signature", "")):
        raise VerificationError("firma non valida: il manifest è stato alterato o firmato da altri")
    manifest = Manifest.model_validate(data)
    if manifest.license not in allowed_licenses:
        raise VerificationError(f"licenza '{manifest.license}' non ammessa")
    files_dir = bundle_dir / "files"
    present = {p.name for p in files_dir.iterdir()} if files_dir.exists() else set()
    declared = set(manifest.files)
    extra = present - declared
    if extra:
        raise VerificationError(f"file non dichiarati nel bundle: {sorted(extra)}")
    for name, meta in manifest.files.items():
        path = files_dir / name
        if not path.is_file():
            raise VerificationError(f"file dichiarato ma assente: {name}")
        if path.stat().st_size != meta.get("size"):
            raise VerificationError(f"dimensione errata per {name}")
        if sha256_file(path) != meta.get("sha256"):
            raise VerificationError(f"hash errato per {name}: file alterato")
    return manifest
