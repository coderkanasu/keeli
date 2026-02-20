"""Tests for `persona start`, `persona log`, `persona resume`, `persona status`, `persona clear-log`."""

import pytest
from pathlib import Path
from unittest.mock import patch

from persona_cli.main import main


@pytest.fixture
def initialized_dir(tmp_path, monkeypatch):
    """Run `persona init` in a temp dir and return the path."""
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["persona", "init"]):
        main()
    return tmp_path


# ── persona start ──────────────────────────────────────────────────────────

class TestStart:
    def test_creates_task_file(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Implement Auth"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "implement-auth.md"
        assert task.exists()
        content = task.read_text()
        assert "Implement Auth" in content
        assert "- [ ] Create tests" in content

    def test_slugifies_name(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Fix Bug #42!!"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "fix-bug-42.md"
        assert task.exists()

    def test_links_context_file(self, initialized_dir):
        ctx = initialized_dir / "docs" / "requirements" / "auth-spec.md"
        ctx.write_text("# Auth Spec\nDetails here.")

        with patch("sys.argv", ["persona", "start", "Auth Feature", "-c", str(ctx)]):
            main()

        task = initialized_dir / "docs" / "tasks" / "auth-feature.md"
        content = task.read_text()
        assert "auth-spec.md" in content

    def test_does_not_overwrite_without_force(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "My Task"]):
            main()
        marker = "ORIGINAL"
        (initialized_dir / "docs" / "tasks" / "my-task.md").write_text(marker)

        with patch("sys.argv", ["persona", "start", "My Task"]):
            main()

        content = (initialized_dir / "docs" / "tasks" / "my-task.md").read_text()
        assert content == marker

    def test_auto_logs_creation(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "New Feature"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task created: New Feature" in log


# ── persona log ────────────────────────────────────────────────────────────

class TestLog:
    def test_appends_timestamped_entry(self, initialized_dir):
        with patch("sys.argv", ["persona", "log", "Fixed auth bug"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Fixed auth bug" in log
        # Check ISO timestamp format (YYYY-MM-DDT)
        assert "T" in log.splitlines()[-1]

    def test_multiple_entries(self, initialized_dir):
        for msg in ["First entry", "Second entry", "Third entry"]:
            with patch("sys.argv", ["persona", "log", msg]):
                main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "First entry" in log
        assert "Third entry" in log


# ── persona resume ─────────────────────────────────────────────────────────

class TestResume:
    def test_brief_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "Active Task"]):
            main()

        with patch("sys.argv", ["persona", "resume", "--brief"]):
            main()

        output = capsys.readouterr().out
        assert "Project" in output or "Active Tasks" in output

    def test_full_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "resume", "--full"]):
            main()

        output = capsys.readouterr().out
        assert "Persona Framework" in output

    def test_default_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "resume"]):
            main()

        output = capsys.readouterr().out
        assert "Persona Framework" in output


# ── persona status ─────────────────────────────────────────────────────────

class TestStatus:
    def test_healthy_after_init(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "status"]):
            main()

        output = capsys.readouterr().out
        assert "Healthy" in output

    def test_unhealthy_when_file_missing(self, initialized_dir, capsys):
        (initialized_dir / "docs" / "decision.md").unlink()

        with patch("sys.argv", ["persona", "status"]):
            main()

        output = capsys.readouterr().out
        assert "Incomplete" in output


# ── persona clear-log ──────────────────────────────────────────────────────

class TestClearLog:
    def test_clears_log(self, initialized_dir):
        with patch("sys.argv", ["persona", "log", "Some noise"]):
            main()
        with patch("sys.argv", ["persona", "clear-log"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Some noise" not in log
        assert "AI Audit Log" in log
