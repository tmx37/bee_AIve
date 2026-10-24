"""Registro locale: la cartella da cui i nodi della rete offline caricano i modelli.

Un bundle entra nel registro solo dopo aver superato la verifica.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .bundle import Manifest, VerificationError, bundle_dirname, verify_bundle
from .crypto import load_trusted_keys


@dataclass
class RegistryEntry:
    bundle_id: str
    path: Path
    manifest: Manifest | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.error is None


class Registry:
    def __init__(self, root: Path, trusted_keys_dir: Path | None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.trusted = load_trusted_keys(trusted_keys_dir)

    def path_for(self, bundle_id: str) -> Path:
        return self.root / bundle_dirname(bundle_id)

    def add(self, bundle_dir: Path, replace: bool = False) -> Manifest:
        manifest = verify_bundle(bundle_dir, self.trusted)
        dst = self.path_for(manifest.bundle_id)
        if dst.exists():
            if not replace:
                raise FileExistsError(f"{manifest.bundle_id} è già nel registro (usa --replace)")
            shutil.rmtree(dst)
        shutil.copytree(bundle_dir, dst)
        # Riverifica la copia: protegge da errori di copia su supporti rimovibili.
        verify_bundle(dst, self.trusted)
        return manifest

    def get(self, bundle_id: str) -> Manifest:
        path = self.path_for(bundle_id)
        if not path.exists():
            raise VerificationError(f"{bundle_id} non è presente nel registro {self.root}")
        return verify_bundle(path, self.trusted)

    def entries(self) -> list[RegistryEntry]:
        out: list[RegistryEntry] = []
        for p in sorted(self.root.iterdir()):
            if not p.is_dir():
                continue
            try:
                m = verify_bundle(p, self.trusted)
                out.append(RegistryEntry(m.bundle_id, p, m))
            except (VerificationError, ValueError) as e:
                out.append(RegistryEntry(p.name, p, None, str(e)))
        return out
