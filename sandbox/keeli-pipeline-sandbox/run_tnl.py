import json
import sqlite3
from pathlib import Path

from keeli.pipeline.pipeline_runner import PipelineRunner


def read_task_id(task_file: Path) -> str:
    for line in task_file.read_text().splitlines():
        if line.startswith("**ID:**"):
            return line.split()[-1]
    raise RuntimeError("Task ID not found")


def main() -> None:
    task_file = Path("docs/tasks/sandbox-gate-trial.md")
    task_id = read_task_id(task_file)

    runner = PipelineRunner()
    events = []

    for gate in ["Analyst", "Architect", "Security", "QA"]:
        events.append(runner.run_once(item_id=task_id, requested_gate=gate, actor="sandbox"))

    blocked = runner.run_once(
        item_id=task_id,
        requested_gate="Regression",
        actor="sandbox",
        affects=["db/schema", "auth/login"],
        side_effects_resolved=False,
    )
    events.append(blocked)

    passed = runner.run_once(
        item_id=task_id,
        requested_gate="Regression",
        actor="sandbox",
        affects=["db/schema", "auth/login"],
        side_effects_resolved=True,
    )
    events.append(passed)

    with sqlite3.connect("keeli_state.db") as conn:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM gate_evidence WHERE item_id = ?",
            (task_id,),
        ).fetchone()[0]

    output = {
        "task_id": task_id,
        "events": events,
        "gate_evidence_count": evidence_count,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
