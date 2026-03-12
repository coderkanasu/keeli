"""Deterministic persona gate transition rules."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_GATE_ORDER: tuple[str, ...] = (
    "Analyst",
    "Architect",
    "Security",
    "QA",
    "Regression",
)


@dataclass(frozen=True)
class GateDecision:
    """Represents a gate transition decision."""

    ok: bool
    gate: str
    reason: str


class PersonaGate:
    """Validate ordered persona gate progression."""

    def __init__(self, gate_order: tuple[str, ...] = DEFAULT_GATE_ORDER):
        self.gate_order = gate_order
        self._gate_index = {gate.lower(): idx for idx, gate in enumerate(gate_order)}

    def next_gate(self, completed_gates: list[str]) -> str | None:
        """Return the next expected gate from completed gates."""
        completed = {gate.lower() for gate in completed_gates}
        for gate in self.gate_order:
            if gate.lower() not in completed:
                return gate
        return None

    def evaluate(self, requested_gate: str, completed_gates: list[str]) -> GateDecision:
        """Evaluate whether requested_gate can run given completed_gates."""
        gate = (requested_gate or "").strip()
        gate_key = gate.lower()
        if gate_key not in self._gate_index:
            return GateDecision(False, gate, f"Unknown gate: {requested_gate}")

        if gate_key in {g.lower() for g in completed_gates}:
            canonical = self.gate_order[self._gate_index[gate_key]]
            return GateDecision(True, canonical, "Gate already completed")

        expected = self.next_gate(completed_gates)
        if expected is None:
            canonical = self.gate_order[self._gate_index[gate_key]]
            return GateDecision(True, canonical, "All gates already completed")

        if expected.lower() != gate_key:
            canonical = self.gate_order[self._gate_index[gate_key]]
            return GateDecision(False, canonical, f"Out-of-order gate. Expected: {expected}")

        return GateDecision(True, expected, "Gate order satisfied")
