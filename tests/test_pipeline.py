import sqlite3
from unittest.mock import patch

import pytest

from keeli.main import main
from keeli.pipeline.audit_trail import AuditTrail
from keeli.pipeline.persona_gate import PersonaGate
from keeli.pipeline.pipeline_runner import PipelineRunner


@pytest.fixture
def initialized_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["keeli", "init"]):
        main()
    return tmp_path


class TestPersonaGate:
    def test_blocks_out_of_order_transition(self):
        gate = PersonaGate()
        decision = gate.evaluate("Security", ["Analyst"])
        assert decision.ok is False
        assert "Expected: Architect" in decision.reason


class TestAuditTrail:
    def test_persists_gate_evidence_rows(self, initialized_dir):
        audit = AuditTrail()
        evidence_id = audit.record_gate_evidence(
            "T-9999",
            "Analyst",
            "passed",
            actor="developer",
            checksum="abc",
            payload={"note": "ok"},
        )
        assert isinstance(evidence_id, int)

        db_path = initialized_dir / "keeli_state.db"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT gate_name, status, actor FROM gate_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        assert row == ("Analyst", "passed", "developer")


class TestPipelineRunner:
    def test_runner_blocks_regression_for_unresolved_side_effects(self, initialized_dir):
        runner = PipelineRunner()
        # Seed prior gates as passed so Regression can be evaluated.
        for gate in ["Analyst", "Architect", "Security", "QA"]:
            result = runner.run_once(item_id="T-9001", requested_gate=gate, actor="developer")
            assert result["ok"] is True

        blocked = runner.run_once(
            item_id="T-9001",
            requested_gate="Regression",
            actor="qa",
            affects=["db/schema", "auth/login"],
            side_effects_resolved=False,
        )
        assert blocked["ok"] is False
        assert blocked["status"] == "blocked"
        assert "unresolved high-risk side effects" in blocked["reason"]

    def test_runner_records_passed_gate_event(self, initialized_dir):
        runner = PipelineRunner()
        result = runner.run_once(item_id="T-9002", requested_gate="Analyst", actor="architect")
        assert result["ok"] is True
        assert result["status"] == "passed"

        db_path = initialized_dir / "keeli_state.db"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT item_id, gate_name, status FROM gate_evidence WHERE evidence_id = ?",
                (result["event_id"],),
            ).fetchone()
        assert row == ("T-9002", "Analyst", "passed")
