"""Single-shot pipeline execution for gate transitions."""

from __future__ import annotations

import hashlib
import json

from keeli.pipeline.audit_trail import AuditTrail
from keeli.pipeline.persona_gate import GateDecision, PersonaGate
from keeli.pipeline.regression_scope import RegressionScope


class PipelineRunner:
    """Run one gate transition with deterministic validation and evidence writes."""

    def __init__(self, audit: AuditTrail | None = None):
        self.audit = audit or AuditTrail()
        self.gates = PersonaGate()
        self.regression = RegressionScope()

    def _checksum(self, payload: dict[str, object]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def run_once(
        self,
        *,
        item_id: str,
        requested_gate: str,
        actor: str,
        affects: str | list[str] | None = None,
        side_effects_resolved: bool = False,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Run a single gate step and persist evidence for pass/block outcomes."""
        completed = self.audit.completed_gates(item_id)
        decision: GateDecision = self.gates.evaluate(requested_gate, completed)
        data: dict[str, object] = {
            "item_id": item_id,
            "gate": decision.gate,
            "completed_gates": completed,
            "reason": decision.reason,
        }

        if not decision.ok:
            evidence_payload = {**(payload or {}), **data, "status": "blocked"}
            event_id = self.audit.record_gate_evidence(
                item_id,
                decision.gate,
                "blocked",
                actor=actor,
                checksum=self._checksum(evidence_payload),
                payload=evidence_payload,
            )
            return {"ok": False, "status": "blocked", "event_id": event_id, **data}

        if decision.gate.lower() == "regression":
            scope = self.regression.derive(affects)
            data["regression_scope"] = scope
            if bool(scope.get("high_risk_side_effects")) and not side_effects_resolved:
                reason = "Regression gate blocked: unresolved high-risk side effects"
                evidence_payload = {**(payload or {}), **data, "status": "blocked", "reason": reason}
                event_id = self.audit.record_gate_evidence(
                    item_id,
                    decision.gate,
                    "blocked",
                    actor=actor,
                    checksum=self._checksum(evidence_payload),
                    payload=evidence_payload,
                )
                return {"ok": False, "status": "blocked", "event_id": event_id, **data, "reason": reason}

        evidence_payload = {**(payload or {}), **data, "status": "passed"}
        event_id = self.audit.record_gate_evidence(
            item_id,
            decision.gate,
            "passed",
            actor=actor,
            checksum=self._checksum(evidence_payload),
            payload=evidence_payload,
        )
        return {"ok": True, "status": "passed", "event_id": event_id, **data}
