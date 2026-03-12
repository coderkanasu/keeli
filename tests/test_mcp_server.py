import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

import keeli.mcp_server as mcp_mod
from keeli.main import main
from keeli.mcp_server import call_tool


def _text(result) -> str:
    return result[0].text


def _add_completion_evidence(task_path: Path) -> None:
    text = task_path.read_text()
    text = text.replace(
        "<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->",
        "- Commit: abcdef123456\n- Artifact: docs/ai_log.md",
    )
    text = text.replace(
        "<!-- Link validation artifacts (tests, checks, commands with outcomes). -->",
        "- Test: pytest -q (pass)\n- Report: tests/test_mcp_server.py",
    )
    task_path.write_text(text)


@pytest.fixture
def keeli_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["keeli", "init"]):
        main()
    return tmp_path


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.send_log_message = AsyncMock()
    session.send_progress_notification = AsyncMock()
    return session


@pytest.mark.asyncio
class TestMcpServer:
    async def test_not_a_project_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = await call_tool("keeli_next", {})
        assert "Not a Keeli project" in _text(result)

    async def test_keeli_start_creates_task_and_db_row(self, keeli_dir):
        result = await call_tool("keeli_start", {"title": "OAuth Setup", "persona": "developer", "priority": "P0", "objective": "Implement OAuth bootstrap"})
        assert "oauth-setup" in _text(result)

        task = keeli_dir / "docs" / "tasks" / "oauth-setup.md"
        assert task.exists()
        assert "**Persona:** @developer" in task.read_text()

        with sqlite3.connect(keeli_dir / "keeli_state.db") as conn:
            row = conn.execute("SELECT status, persona FROM work_items WHERE slug = ?", ("oauth-setup",)).fetchone()
        assert row == ("Backlog", "@developer")

    async def test_keeli_next_includes_persona_hint(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Design API", "persona": "architect"})
        result = await call_tool("keeli_next", {})
        text = _text(result)
        assert "**Persona:** @architect" in text
        assert "Load persona rules from docs/personas.md" in text

    async def test_keeli_progress_updates_task_and_db(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Build schema"})
        result = await call_tool("keeli_progress", {"task_slug": "build-schema"})
        assert "In Progress" in _text(result)

        task = keeli_dir / "docs" / "tasks" / "build-schema.md"
        assert "**Status:** In Progress" in task.read_text()

        with sqlite3.connect(keeli_dir / "keeli_state.db") as conn:
            row = conn.execute("SELECT status FROM work_items WHERE slug = ?", ("build-schema",)).fetchone()
        assert row == ("In Progress",)

    async def test_keeli_complete_archives_and_updates_db(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Finalize schema"})
        _add_completion_evidence(keeli_dir / "docs" / "tasks" / "finalize-schema.md")
        await call_tool("keeli_complete", {"task_slug": "finalize-schema"})

        archived = keeli_dir / "docs" / "tasks" / "archive" / "finalize-schema.md"
        assert archived.exists()
        assert "**Status:** Completed" in archived.read_text()

        with sqlite3.connect(keeli_dir / "keeli_state.db") as conn:
            row = conn.execute("SELECT status, archived FROM work_items WHERE slug = ?", ("finalize-schema",)).fetchone()
        assert row == ("Completed", 1)

    async def test_keeli_start_emits_log_message_when_session_exists(self, keeli_dir, mock_session):
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_start", {"title": "Logged Task"})
        mock_session.send_log_message.assert_called_once()

    async def test_keeli_transition_from_commit_returns_structured_events(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Transition MCP", "objective": "Do work"})
        await call_tool("keeli_progress", {"task_slug": "transition-mcp"})

        task_text = (keeli_dir / "docs" / "tasks" / "transition-mcp.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        result = await call_tool("keeli_transition_from_commit", {"subject": f"feat: closes {task_id}"})
        payload = json.loads(_text(result))

        assert "evaluation" in payload
        actions = payload["evaluation"]["actions"]
        review_action = next(a for a in actions if a["type"] == "review_ids")
        assert task_id in review_action["ids"]

    async def test_keeli_capture_commit_state_returns_correlated_payload(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Capture MCP", "objective": "Do work"})
        await call_tool("keeli_progress", {"task_slug": "capture-mcp"})
        _add_completion_evidence(keeli_dir / "docs" / "tasks" / "capture-mcp.md")

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "abcdef1234567890\n"
            elif cmd[1:] == ["log", "-1", "--pretty=%s"]:
                result.stdout = "keeli:complete\n"
            else:
                result.stdout = "\n"
            return result

        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            result = await call_tool("keeli_capture_commit_state", {})

        payload = json.loads(_text(result))
        assert payload["ok"] is True
        assert isinstance(payload["commit_event_id"], int)
        assert payload["active_item"]["slug"] == "capture-mcp"

    async def test_keeli_transition_from_commit_honors_target_id(self, keeli_dir):
        await call_tool("keeli_start", {"title": "MCP A", "objective": "A"})
        await call_tool("keeli_start", {"title": "MCP B", "objective": "B"})
        await call_tool("keeli_progress", {"task_slug": "mcp-a"})
        await call_tool("keeli_progress", {"task_slug": "mcp-b"})
        _add_completion_evidence(keeli_dir / "docs" / "tasks" / "mcp-b.md")

        task_text = (keeli_dir / "docs" / "tasks" / "mcp-b.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        result = await call_tool(
            "keeli_transition_from_commit",
            {"subject": "keeli:complete", "target_id": task_id, "apply": True},
        )

        payload = json.loads(_text(result))
        assert payload["applied"]
        assert any(task_id in line for line in payload["applied"])
