"""Tests for the Keeli MCP server tool handlers (call_tool).

Covers:
- All tool handlers: keeli_next, keeli_start, keeli_complete, keeli_analyze,
  keeli_log, keeli_find, keeli_history, keeli_digest, keeli_archive_task
- Error / edge cases (missing args, not-found, unknown tool, not-a-project)
- Streaming notifications (S-1/S-2/S-3):
    - _mcp_log  — silent no-op when no session; calls send_log_message when session active
    - _emit_progress — silent no-op when no token; calls send_progress_notification
      when session + progressToken present
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import keeli.mcp_server as mcp_mod
from keeli.mcp_server import call_tool
from keeli.main import main


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def keeli_dir(tmp_path, monkeypatch):
    """Initialise a Keeli project in a temp dir and make it the cwd."""
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["keeli", "init"]):
        main()
    return tmp_path


@pytest.fixture
def mock_session():
    """A fake MCP session with async send helpers."""
    session = MagicMock()
    session.send_log_message = AsyncMock()
    session.send_progress_notification = AsyncMock()
    return session


# ── Helpers ────────────────────────────────────────────────────────────────────

def _text(result) -> str:
    """Extract the text from the first TextContent in a call_tool result."""
    return result[0].text


def _task_id_from_file(task_file: Path) -> str:
    """Parse **ID:** from a task markdown file."""
    for line in task_file.read_text().splitlines():
        if "**ID:**" in line:
            return line.split("**ID:**")[1].strip()
    return ""


# ── Infrastructure ─────────────────────────────────────────────────────────────

class TestInfrastructure:
    async def test_not_a_keeli_project(self, tmp_path, monkeypatch):
        """When docs/ is absent call_tool returns a helpful error."""
        monkeypatch.chdir(tmp_path)
        result = await call_tool("keeli_next", {})
        assert "Not a Keeli project" in _text(result)

    async def test_unknown_tool_returns_error(self, keeli_dir):
        result = await call_tool("keeli_garbage", {})
        assert "Unknown tool" in _text(result)


# ── keeli_next ─────────────────────────────────────────────────────────────────

class TestKeeliNext:
    async def test_no_tasks_returns_message(self, keeli_dir):
        result = await call_tool("keeli_next", {})
        assert "No tasks available" in _text(result)

    async def test_returns_next_task_content(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Next Task"]):
            main()
        result = await call_tool("keeli_next", {})
        text = _text(result)
        assert "next-task" in text
        assert "Next Task" in text


# ── keeli_start ────────────────────────────────────────────────────────────────

class TestKeeliStart:
    async def test_creates_task_file(self, keeli_dir):
        result = await call_tool("keeli_start", {"title": "My Feature", "priority": "P0"})
        assert "my-feature" in _text(result)
        assert (keeli_dir / "docs" / "tasks" / "my-feature.md").exists()

    async def test_task_file_has_correct_priority(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Priority Task", "priority": "P0"})
        content = (keeli_dir / "docs" / "tasks" / "priority-task.md").read_text()
        assert "P0" in content

    async def test_duplicate_returns_error(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Dup Task"})
        result = await call_tool("keeli_start", {"title": "Dup Task"})
        assert "already exists" in _text(result)

    async def test_persona_stored_in_file(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Dev Task", "persona": "developer"})
        content = (keeli_dir / "docs" / "tasks" / "dev-task.md").read_text()
        assert "@developer" in content

    async def test_sends_log_message_when_session_active(self, keeli_dir, mock_session):
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_start", {"title": "Logged Task"})
        mock_session.send_log_message.assert_called_once()
        # Verify correct level
        kwargs = mock_session.send_log_message.call_args.kwargs
        assert kwargs.get("level") == "info"

    async def test_no_log_message_without_session(self, keeli_dir):
        """Default test path: LookupError → _session=None → no notifications."""
        # Just confirm it completes without raising
        result = await call_tool("keeli_start", {"title": "Silent Task"})
        assert "Successfully created" in _text(result)


# ── keeli_complete ─────────────────────────────────────────────────────────────

class TestKeeliComplete:
    async def test_missing_slug_returns_error(self, keeli_dir):
        result = await call_tool("keeli_complete", {})
        assert "task_slug is required" in _text(result)

    async def test_not_found_returns_error(self, keeli_dir):
        result = await call_tool("keeli_complete", {"task_slug": "no-such-task"})
        assert "not found" in _text(result)

    async def test_completes_and_archives(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Archive Me"]):
            main()
        result = await call_tool("keeli_complete", {"task_slug": "archive-me"})
        assert "Marked" in _text(result) or "Completed" in _text(result)
        assert not (keeli_dir / "docs" / "tasks" / "archive-me.md").exists()
        assert (keeli_dir / "docs" / "tasks" / "archive" / "archive-me.md").exists()

    async def test_archived_file_has_completed_status(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Status Check"]):
            main()
        await call_tool("keeli_complete", {"task_slug": "status-check"})
        content = (keeli_dir / "docs" / "tasks" / "archive" / "status-check.md").read_text()
        assert "**Status:** Completed" in content

    async def test_sends_log_message_when_session_active(self, keeli_dir, mock_session):
        with patch("sys.argv", ["keeli", "start", "To Complete"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_complete", {"task_slug": "to-complete"})
        mock_session.send_log_message.assert_called_once()


# ── keeli_analyze ──────────────────────────────────────────────────────────────

class TestKeeliAnalyze:
    async def test_missing_slug_returns_error(self, keeli_dir):
        result = await call_tool("keeli_analyze", {})
        assert "task_slug is required" in _text(result)

    async def test_not_found_returns_error(self, keeli_dir):
        result = await call_tool("keeli_analyze", {"task_slug": "ghost-task"})
        assert "No task matching" in _text(result)

    async def test_dry_run_returns_analysis(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Analyze Me"]):
            main()
        result = await call_tool("keeli_analyze", {"task_slug": "analyze-me", "dry_run": True})
        text = _text(result)
        assert "analyze-me" in text or "Analysis" in text

    async def test_dry_run_does_not_modify_file(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Read Only"]):
            main()
        task_file = keeli_dir / "docs" / "tasks" / "read-only.md"
        before = task_file.read_text()
        await call_tool("keeli_analyze", {"task_slug": "read-only", "dry_run": True})
        after = task_file.read_text()
        assert before == after

    async def test_inject_mode_writes_hints_block(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Inject Task"]):
            main()
        await call_tool("keeli_analyze", {"task_slug": "inject-task", "dry_run": False})
        content = (keeli_dir / "docs" / "tasks" / "inject-task.md").read_text()
        assert "KEELI_HINTS" in content

    async def test_emits_progress_with_token(self, keeli_dir, mock_session):
        """When _meta.progressToken is present, send_progress_notification fires."""
        with patch("sys.argv", ["keeli", "start", "Progress Task"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_analyze", {
                "task_slug": "progress-task",
                "dry_run": True,
                "_meta": {"progressToken": "tok-1"},
            })
        mock_session.send_progress_notification.assert_called()
        # Should have emitted at least steps 0, 1, 2, 3, 4 (dry-run path = 5 calls)
        assert mock_session.send_progress_notification.call_count >= 4

    async def test_no_progress_without_token(self, keeli_dir, mock_session):
        """Without _meta.progressToken, send_progress_notification is never called."""
        with patch("sys.argv", ["keeli", "start", "Token-less Task"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_analyze", {"task_slug": "token-less-task", "dry_run": True})
        mock_session.send_progress_notification.assert_not_called()

    async def test_no_progress_without_session(self, keeli_dir):
        """Outside a request context no progress/log calls happen → no crash."""
        with patch("sys.argv", ["keeli", "start", "No Session Task"]):
            main()
        result = await call_tool("keeli_analyze", {
            "task_slug": "no-session-task",
            "dry_run": True,
            "_meta": {"progressToken": "tok-2"},
        })
        # Just verify it completed successfully
        assert "no-session-task" in _text(result) or "Analysis" in _text(result)


# ── keeli_log ──────────────────────────────────────────────────────────────────

class TestKeeliLog:
    async def test_appends_message_to_log(self, keeli_dir):
        result = await call_tool("keeli_log", {"message": "hello from test", "persona": "developer"})
        assert "appended" in _text(result).lower()
        log = (keeli_dir / "docs" / "ai_log.md").read_text()
        assert "hello from test" in log

    async def test_missing_log_file_returns_error(self, keeli_dir):
        (keeli_dir / "docs" / "ai_log.md").unlink()
        result = await call_tool("keeli_log", {"message": "should fail"})
        assert "not found" in _text(result).lower()


# ── keeli_find ─────────────────────────────────────────────────────────────────

class TestKeeliFind:
    async def test_no_index_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "project.md").write_text("# Project\n")
        result = await call_tool("keeli_find", {"query": "anything"})
        assert "Index not found" in _text(result)

    async def test_id_match(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Find By ID"})
        task_file = keeli_dir / "docs" / "tasks" / "find-by-id.md"
        task_id = _task_id_from_file(task_file)
        result = await call_tool("keeli_find", {"query": task_id})
        assert "ID match" in _text(result)
        assert task_id in _text(result)

    async def test_keyword_match(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Unique Keyword Fuzz"})
        result = await call_tool("keeli_find", {"query": "unique-keyword-fuzz"})
        assert "unique-keyword-fuzz" in _text(result)

    async def test_no_results(self, keeli_dir):
        # Seed the index so we get a proper "No results" response
        await call_tool("keeli_start", {"title": "Seed Task For Find"})
        result = await call_tool("keeli_find", {"query": "xyzzy-no-such-thing-886"})
        assert "No results" in _text(result)

    async def test_status_filter_match(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Status Match Task"})
        result = await call_tool("keeli_find", {"query": "status-match-task", "status": "backlog"})
        assert "status-match-task" in _text(result)

    async def test_status_filter_no_match(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Status Mismatch Task"})
        result = await call_tool("keeli_find", {"query": "status-mismatch-task", "status": "completed"})
        assert "No results" in _text(result)


# ── keeli_history ──────────────────────────────────────────────────────────────

class TestKeeliHistory:
    async def test_no_log_file_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "project.md").write_text("# Project\n")
        result = await call_tool("keeli_history", {"task_id": "T-001"})
        assert "not found" in _text(result).lower()

    async def test_found_entries_for_task(self, keeli_dir):
        await call_tool("keeli_start", {"title": "History Test"})
        task_file = keeli_dir / "docs" / "tasks" / "history-test.md"
        task_id = _task_id_from_file(task_file)
        result = await call_tool("keeli_history", {"task_id": task_id})
        assert "entries" in _text(result)
        assert task_id in _text(result)

    async def test_no_entries_for_unknown_id(self, keeli_dir):
        result = await call_tool("keeli_history", {"task_id": "T-99999"})
        assert "No log entries" in _text(result)


# ── keeli_digest ───────────────────────────────────────────────────────────────

class TestKeeliDigest:
    async def test_returns_output_with_token_count(self, keeli_dir):
        result = await call_tool("keeli_digest", {"budget": 2000})
        assert "tokens" in _text(result)

    async def test_tiny_budget_still_returns(self, keeli_dir):
        await call_tool("keeli_start", {"title": "Budget Task"})
        result = await call_tool("keeli_digest", {"budget": 5})
        assert "tokens" in _text(result)

    async def test_active_task_appears_in_digest(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Active Work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Active Work"]):
            main()
        result = await call_tool("keeli_digest", {"budget": 2000})
        assert "active-work" in _text(result).lower() or "Active" in _text(result)

    async def test_sends_log_messages_with_session(self, keeli_dir, mock_session):
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_digest", {"budget": 2000})
        # At minimum the final "[digest] Complete" line is logged
        mock_session.send_log_message.assert_called()
        logged_msgs = [c.kwargs.get("data", "") for c in mock_session.send_log_message.call_args_list]
        assert any("[digest]" in msg for msg in logged_msgs)


# ── keeli_archive_task ─────────────────────────────────────────────────────────

class TestKeeliArchiveTask:
    async def test_missing_slug_returns_error(self, keeli_dir):
        result = await call_tool("keeli_archive_task", {})
        assert "task_slug is required" in _text(result)

    async def test_not_found_returns_error(self, keeli_dir):
        result = await call_tool("keeli_archive_task", {"task_slug": "ghost"})
        assert "not found" in _text(result)

    async def test_successful_archive(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "To Archive"]):
            main()
        result = await call_tool("keeli_archive_task", {"task_slug": "to-archive"})
        assert "Archived" in _text(result) or "archived" in _text(result)
        assert not (keeli_dir / "docs" / "tasks" / "to-archive.md").exists()
        assert (keeli_dir / "docs" / "tasks" / "archive" / "to-archive.md").exists()

    async def test_already_archived_returns_error(self, keeli_dir):
        with patch("sys.argv", ["keeli", "start", "Already Done"]):
            main()
        await call_tool("keeli_archive_task", {"task_slug": "already-done"})
        result = await call_tool("keeli_archive_task", {"task_slug": "already-done"})
        assert "already archived" in _text(result)

    async def test_sends_log_message_when_session_active(self, keeli_dir, mock_session):
        with patch("sys.argv", ["keeli", "start", "Log Archive"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_archive_task", {"task_slug": "log-archive"})
        mock_session.send_log_message.assert_called_once()
        kwargs = mock_session.send_log_message.call_args.kwargs
        assert kwargs.get("level") == "info"
        assert "log-archive" in kwargs.get("data", "")


# ── Streaming: notification behaviour ─────────────────────────────────────────

class TestStreamingNotifications:
    async def test_mcp_log_is_no_op_without_session(self, keeli_dir):
        """All mutating tools complete without error when no MCP session is present."""
        result = await call_tool("keeli_start", {"title": "Quiet Tool"})
        assert "Successfully created" in _text(result)

    async def test_emit_progress_is_no_op_without_session(self, keeli_dir):
        """Progress notifications are silently skipped outside a request context."""
        with patch("sys.argv", ["keeli", "start", "Quiet Analyze"]):
            main()
        result = await call_tool("keeli_analyze", {
            "task_slug": "quiet-analyze",
            "dry_run": True,
            "_meta": {"progressToken": "tok-x"},
        })
        # Completed without error; no assertion on mock needed (no session means no-op)
        assert "quiet-analyze" in _text(result) or "Analysis" in _text(result)

    async def test_emit_progress_is_no_op_without_token(self, keeli_dir, mock_session):
        """Session present but no progressToken → send_progress_notification never called."""
        with patch("sys.argv", ["keeli", "start", "No Token"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_analyze", {"task_slug": "no-token", "dry_run": True})
        mock_session.send_progress_notification.assert_not_called()

    async def test_progress_notification_args_are_correct(self, keeli_dir, mock_session):
        """Verify progress_token and monotonic progress values are forwarded correctly."""
        with patch("sys.argv", ["keeli", "start", "Check Args"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_analyze", {
                "task_slug": "check-args",
                "dry_run": True,
                "_meta": {"progressToken": "my-token"},
            })
        calls = mock_session.send_progress_notification.call_args_list
        assert len(calls) >= 4
        tokens = [c.kwargs.get("progress_token") for c in calls]
        assert all(t == "my-token" for t in tokens)
        # Verify progress values are non-decreasing
        progresses = [c.kwargs.get("progress", 0) for c in calls]
        assert progresses == sorted(progresses)

    async def test_log_message_args_are_correct(self, keeli_dir, mock_session):
        """Verify level='info' and data contains task slug on keeli_complete."""
        with patch("sys.argv", ["keeli", "start", "Log Args Task"]):
            main()
        with patch.object(type(mcp_mod.app), "request_context", new_callable=PropertyMock) as mock_rc:
            mock_rc.return_value.session = mock_session
            await call_tool("keeli_complete", {"task_slug": "log-args-task"})
        mock_session.send_log_message.assert_called_once()
        kwargs = mock_session.send_log_message.call_args.kwargs
        assert kwargs["level"] == "info"
        assert "log-args-task" in kwargs["data"]
