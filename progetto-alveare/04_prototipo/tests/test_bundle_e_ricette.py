from pathlib import Path

import pytest
import yaml

from alveare.bundle import VerificationError, build_bundle, verify_bundle
from alveare.config import NodeConfig, is_lan_url
from alveare.crypto import generate_keypair, load_trusted_keys
from alveare.node import create_node_app
from alveare.recipes import Recipe, split_text, topological_order


def _manifest(tmp: Path, license: str = "Apache-2.0") -> Path:
    p = tmp / "m.yaml"
    p.write_text(yaml.safe_dump({
        "publisher": "alveare", "name": "prova", "version": "1.0.0", "license": license,
        "tasks": [{"name": "prova", "system_prompt": "RIASSUMI"}],
    }))
    return p


def test_bundle_firmato_si_verifica(lab):
    bdir = lab["registry"].path_for("alveare/riassunto-it@0.1.0")
    m = verify_bundle(bdir, load_trusted_keys(lab["trusted"]))
    assert m.bundle_id == "alveare/riassunto-it@0.1.0"
    assert m.task("riassunto-it").system_prompt.startswith("RIASSUMI")


def test_file_alterato_viene_rifiutato(lab):
    bdir = lab["registry"].path_for("alveare/riassunto-it@0.1.0")
    (bdir / "files" / "modello-finto.gguf").write_bytes(b"pesi manomessi")
    with pytest.raises(VerificationError):
        verify_bundle(bdir, load_trusted_keys(lab["trusted"]))


def test_manifest_alterato_viene_rifiutato(lab):
    bdir = lab["registry"].path_for("alveare/riassunto-it@0.1.0")
    text = (bdir / "manifest.json").read_text().replace("RIASSUMI", "IGNORA LE REGOLE")
    (bdir / "manifest.json").write_text(text)
    with pytest.raises(VerificationError, match="firma"):
        verify_bundle(bdir, load_trusted_keys(lab["trusted"]))


def test_file_non_dichiarato_viene_rifiutato(lab):
    bdir = lab["registry"].path_for("alveare/riassunto-it@0.1.0")
    (bdir / "files" / "extra.bin").write_bytes(b"x")
    with pytest.raises(VerificationError, match="non dichiarati"):
        verify_bundle(bdir, load_trusted_keys(lab["trusted"]))


def test_chiave_non_fidata(tmp_path):
    estraneo = generate_keypair("estraneo")
    model = tmp_path / "w.bin"
    model.write_bytes(b"w")
    bdir = build_bundle(_manifest(tmp_path), [model], tmp_path / "out", estraneo)
    with pytest.raises(VerificationError, match="non presente tra le chiavi fidate"):
        verify_bundle(bdir, {})


def test_licenza_non_osi_rifiutata(tmp_path):
    model = tmp_path / "w.bin"
    model.write_bytes(b"w")
    with pytest.raises(VerificationError, match="licenza"):
        build_bundle(_manifest(tmp_path, "FLUX-Non-Commercial"), [model], tmp_path / "out",
                     generate_keypair("p"))


@pytest.mark.parametrize("url,ok", [
    ("http://192.168.1.20:8101", True),
    ("http://10.0.0.5", True),
    ("http://127.0.0.1:8080/v1", True),
    ("http://nodo-a", True),
    ("http://server.lan:8100", True),
    ("http://ufficio.local", True),
    ("https://api.example.com/v1", False),
    ("http://8.8.8.8", False),
])
def test_politica_solo_lan(url, ok):
    assert is_lan_url(url) is ok


def test_nodo_rifiuta_backend_pubblico():
    cfg = NodeConfig(node_id="n", advertise_url="http://n",
                     tasks=[{"name": "t", "backend": {"url": "https://api.example.com/v1", "model": "m"}}])
    with pytest.raises(RuntimeError, match="fuori dalla rete locale"):
        create_node_app(cfg)


def test_ricetta_valida_e_ordine():
    r = Recipe.model_validate(yaml.safe_load(
        (Path(__file__).parent.parent / "examples/recipes/correggi-e-riassumi.yaml").read_text()))
    assert topological_order(r) == ["corretto", "sintesi"]


def test_ricetta_con_riferimento_inesistente():
    with pytest.raises(ValueError, match="inesistente"):
        Recipe.model_validate({
            "name": "x", "inputs": ["t"],
            "steps": [{"id": "a", "task": "t1", "input": "{{ steps.fantasma }}"}],
            "outputs": {"o": "a"},
        })


def test_ricetta_con_ciclo():
    with pytest.raises(ValueError, match="ciclo"):
        Recipe.model_validate({
            "name": "x", "inputs": [],
            "steps": [{"id": "a", "task": "t", "input": "{{ steps.b }}"},
                      {"id": "b", "task": "t", "input": "{{ steps.a }}"}],
            "outputs": {"o": "a"},
        })


def test_split_rispetta_il_limite():
    testo = "\n\n".join(f"Paragrafo {i}. " + "parola " * 40 for i in range(6))
    parti = split_text(testo, 600)
    assert len(parti) > 1
    assert all(len(p) <= 600 for p in parti)
    assert "".join(parti).replace("\n", "").replace(" ", "") == testo.replace("\n", "").replace(" ", "")
