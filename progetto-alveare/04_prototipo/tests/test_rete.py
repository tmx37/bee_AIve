import json
from pathlib import Path

from alveare.crypto import generate_keypair
from alveare.validate import aggregate_reports, chrf, make_score_report, run_validation, verify_score_report

from conftest import CLIENT_KEY, client_for

TESTO = "\n\n".join(
    f"Articolo {i}. Il fornitore si impegna a consegnare i beni entro trenta giorni dalla data dell'ordine. "
    "In caso di ritardo si applica una penale pari all'uno per cento del valore per ogni settimana."
    for i in range(1, 7)
)


async def test_ricetta_parallela_su_due_nodi(lab):
    orch = lab["build_network"]()
    async with client_for(orch) as c:
        r = await c.post("/v1/run", json={"recipe": "traduci-e-riassumi", "inputs": {"testo": TESTO}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["outputs"]["traduzione_en"].count("[EN]") >= 2
    assert data["outputs"]["riassunto_it"].endswith("[...]")
    nodi_traduzione = {e["node"] for e in data["trace"] if e["step"] == "traduzioni"}
    assert nodi_traduzione == {"nodo-a", "nodo-b"}, "le parti devono essere distribuite su entrambi i nodi"
    assert all(e["bundle"].startswith("alveare/") for e in data["trace"])


async def test_ricetta_sequenziale(lab):
    orch = lab["build_network"]()
    async with client_for(orch) as c:
        r = await c.post("/v1/run", json={"recipe": "correggi-e-riassumi",
                                          "inputs": {"testo": "il  contratto ,  firmato ieri . Vale due anni."}})
    assert r.status_code == 200, r.text
    out = r.json()["outputs"]
    assert out["testo_corretto"].startswith("Il contratto, firmato ieri.")


async def test_capacita_annunciate(lab):
    orch = lab["build_network"]()
    async with client_for(orch) as c:
        r = await c.get("/nodes")
    caps = r.json()["capabilities"]
    assert set(caps["traduzione-it-en"]) == {"http://nodo-a", "http://nodo-b"}
    assert caps["riassunto-it"] == ["http://nodo-a"]


async def test_client_senza_chiave_rifiutato(lab):
    orch = lab["build_network"]()
    async with client_for(orch, key=None) as c:
        r = await c.post("/v1/tasks/riassunto-it", json={"input": "Testo."})
    assert r.status_code == 401


async def test_nodo_rifiuta_chiave_sbagliata(lab):
    lab["build_network"]()
    nodo = lab["mounts"]["http://nodo-a"]
    async with client_for(nodo, base="http://nodo-a", key="chiave-sbagliata") as c:
        r = await c.post("/v1/tasks/riassunto-it", json={"input": "Testo."})
    assert r.status_code == 401


async def test_failover_su_nodo_guasto(lab):
    orch = lab["build_network"](node_b_backend="http://backend-guasto")
    async with client_for(orch) as c:
        r = await c.post("/v1/run", json={"recipe": "traduci-e-riassumi", "inputs": {"testo": TESTO}})
    assert r.status_code == 200, r.text
    trace = r.json()["trace"]
    assert all(e["node"] == "nodo-a" for e in trace if e["step"] == "traduzioni")
    assert any(e["attempt"] == 2 for e in trace), "almeno una parte deve essere stata ritentata"


async def test_compito_senza_bundle_valido_disabilitato(lab):
    from alveare.node import create_node_app

    cfg = lab["node_cfg"]("nodo-c", ["riassunto-it"])
    cfg.tasks[0].bundle = "alveare/inesistente@9.9.9"
    app = create_node_app(cfg, lab["factory"])
    async with client_for(app, base="http://nodo-c", key="chiave-orchestratore-di-test") as c:
        card = (await c.get("/.well-known/agent.json")).json()
        r = await c.post("/v1/tasks/riassunto-it", json={"input": "Testo."})
    assert card["skills"][0]["enabled"] is False
    assert r.status_code == 503


async def test_validazione_privata_e_rapporto_firmato(lab, tmp_path: Path):
    lab["build_network"]()
    casi = tmp_path / "casi.jsonl"
    casi.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in [
        {"input": "Il prezzo è fisso. Il resto è variabile.", "expected": "Il prezzo è fisso.", "metric": "contains"},
        {"input": "Consegna in trenta giorni. Penale dell'uno per cento.", "expected": "Consegna in trenta giorni.",
         "metric": "chrf"},
    ]))
    result = await run_validation("http://orchestratore", "riassunto-it", casi, CLIENT_KEY, lab["factory"])
    assert result["n_cases"] == 2 and result["failures"] == 0
    assert result["score_mean"] > 50

    validatori = [generate_keypair(f"validatore-{i}") for i in range(3)]
    trusted = {v.key_id: v.public for v in validatori}
    reports = [make_score_report(result, "riassunto-it", "alveare/riassunto-it@0.1.0", casi, v) for v in validatori]
    assert all(verify_score_report(r, trusted) for r in reports)
    assert "casi" not in json.dumps(reports[0]["payload"]["result"])  # i casi non escono dalla rete

    falso = json.loads(json.dumps(reports[0]))
    falso["payload"]["result"]["score_mean"] = 99.9
    assert not verify_score_report(falso, trusted)
    agg = aggregate_reports(reports + [falso], trusted)
    assert agg["n_valid"] == 3 and agg["n_rejected"] == 1


def test_chrf():
    assert chrf("la penale è dell'uno per cento", "la penale è dell'uno per cento") > 99.9
    assert chrf("testo completamente diverso", "la penale è dell'uno per cento") < 40
