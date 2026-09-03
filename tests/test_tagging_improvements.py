import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.keeli.engine import KeeliEngine
from src.keeli.llm_interface import LLMInterface
from src.keeli.mcp_server import _normalize_and_validate_tags


def test_normalize_and_validate_tags_accepts_schema_tags():
    tags = ["Domain:Data", "area:data-integrity", "risk:critical", "state:blocked"]

    normalized = _normalize_and_validate_tags(tags)

    assert normalized == [
        "domain:data",
        "area:data-integrity",
        "risk:critical",
        "state:blocked",
    ]


def test_normalize_and_validate_tags_rejects_invalid_tags():
    invalid = ["ui", "owner:team-a", "risk:sev-1!"]

    try:
        _normalize_and_validate_tags(invalid)
        assert False, "Expected ValueError for invalid tags"
    except ValueError as exc:
        message = str(exc)
        assert "Invalid tag(s)" in message
        assert "area" in message
        assert "domain" in message
        assert "risk" in message
        assert "state" in message


def test_engine_list_tasks_filters_by_tags(tmp_path):
    engine = KeeliEngine(root_dir=tmp_path)
    t1 = engine.start("Fix auth bug", tags=["domain:backend", "area:auth", "risk:high"])
    t2 = engine.start("Cleanup dashboard", tags=["domain:frontend", "area:dashboard", "risk:low"])
    engine.sync()

    auth_tasks = engine.list_tasks(tags=["area:auth"], tag_match="any")
    strict_tasks = engine.list_tasks(tags=["domain:backend", "area:auth"], tag_match="all")
    no_match = engine.list_tasks(tags=["state:blocked"], tag_match="any")

    assert any(task["id"] == t1 for task in auth_tasks)
    assert all(task["id"] != t2 for task in auth_tasks)
    assert len(strict_tasks) == 1 and strict_tasks[0]["id"] == t1
    assert no_match == []


def test_extract_task_details_infers_structured_tags():
    interface = LLMInterface.__new__(LLMInterface)

    details = interface._extract_task_details(
        "Create urgent task to fix auth dashboard data integrity issue blocked in MCP session"
    )

    tags = set(details["tags"])
    assert "risk:critical" in tags
    assert "area:auth" in tags
    assert "area:dashboard" in tags
    assert "area:data-integrity" in tags
    assert "area:state-management" in tags
    assert "state:blocked" in tags