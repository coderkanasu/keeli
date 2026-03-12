"""Deterministic regression scope derivation from affects metadata."""

from __future__ import annotations

import re


_HIGH_RISK_KEYWORDS: tuple[str, ...] = (
    "db",
    "schema",
    "migration",
    "auth",
    "security",
    "payment",
)


class RegressionScope:
    """Build deterministic module/test scope from affects metadata."""

    def parse_affects(self, affects: str | list[str] | None) -> list[str]:
        if affects is None:
            return []
        if isinstance(affects, list):
            values = [str(v).strip() for v in affects]
        else:
            values = [chunk.strip() for chunk in str(affects).split(",")]
        unique = sorted({v for v in values if v})
        return unique

    def derive(self, affects: str | list[str] | None) -> dict[str, object]:
        modules = self.parse_affects(affects)
        tests: list[str] = []
        for module in modules:
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", module).strip("_").lower()
            if slug:
                tests.append(f"tests/test_scope_{slug}.py")
        high_risk = any(any(keyword in module.lower() for keyword in _HIGH_RISK_KEYWORDS) for module in modules)
        return {
            "modules": modules,
            "tests": tests,
            "high_risk_side_effects": high_risk,
        }
