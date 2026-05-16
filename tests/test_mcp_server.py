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
        assert "**Persona:**" not in task.read_text()

        with sqlite3.connect(keeli_dir / "keeli_state.db") as conn:
            row = conn.execute("SELECT status, persona FROM work_items WHERE slug = ?", ("oauth-setup",)).fetchone()
        assert row[0] == "Backlog"
        assert row[1] in (None, "")

    async def test_keeli_next_does_not_include_persona_hint(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Design API", "persona": "architect"})
        result = await call_tool("keeli_next", {})
        text = _text(result)
        assert "Next task:" in text
        assert "**Persona:**" not in text

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
