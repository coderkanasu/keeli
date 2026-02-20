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
        assert "**Priority:** P1" in content  # default priority

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

    def test_priority_flag(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Critical Fix", "-p", "P0"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "critical-fix.md"
        content = task.read_text()
        assert "**Priority:** P0" in content


# ── persona complete ───────────────────────────────────────────────────────

class TestComplete:
    def test_marks_task_completed(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "My Task"]):
            main()
        with patch("sys.argv", ["persona", "complete", "My Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "my-task.md"
        content = task.read_text()
        assert "**Status:** Completed" in content
        assert "**Completed:** 20" in content  # timestamp starts with year

    def test_logs_completion(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Log Test"]):
            main()
        with patch("sys.argv", ["persona", "complete", "Log Test"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task completed: Log Test" in log

    def test_suggests_next_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "First Task", "-p", "P0"]):
            main()
        with patch("sys.argv", ["persona", "start", "Second Task", "-p", "P1"]):
            main()
        with patch("sys.argv", ["persona", "complete", "First Task"]):
            main()

        output = capsys.readouterr().out
        assert "Next task:" in output
        assert "second-task" in output

    def test_all_done_message(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "Only Task"]):
            main()
        with patch("sys.argv", ["persona", "complete", "Only Task"]):
            main()

        output = capsys.readouterr().out
        assert "All tasks are complete" in output

    def test_already_completed(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "Done Task"]):
            main()
        with patch("sys.argv", ["persona", "complete", "Done Task"]):
            main()
        with patch("sys.argv", ["persona", "complete", "Done Task"]):
            main()

        output = capsys.readouterr().out
        assert "already marked as Completed" in output


# ── persona next ───────────────────────────────────────────────────────────

class TestNext:
    def test_shows_highest_priority_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "Low Prio", "-p", "P2"]):
            main()
        with patch("sys.argv", ["persona", "start", "High Prio", "-p", "P0"]):
            main()
        with patch("sys.argv", ["persona", "next", "-q"]):
            main()

        output = capsys.readouterr().out
        assert "high-prio" in output

    def test_no_tasks_remaining(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "next"]):
            main()

        output = capsys.readouterr().out
        assert "All tasks are complete" in output


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


# ── persona progress ───────────────────────────────────────────────────────

class TestProgress:
    def test_marks_task_in_progress(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "My Task"]):
            main()
        with patch("sys.argv", ["persona", "progress", "My Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "my-task.md"
        content = task.read_text()
        assert "**Status:** In Progress" in content

    def test_logs_event(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Log Progress"]):
            main()
        with patch("sys.argv", ["persona", "progress", "Log Progress"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task started: Log Progress" in log

    def test_already_in_progress(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "start", "WIP Task"]):
            main()
        with patch("sys.argv", ["persona", "progress", "WIP Task"]):
            main()
        with patch("sys.argv", ["persona", "progress", "WIP Task"]):
            main()

        output = capsys.readouterr().out
        assert "already In Progress" in output

    def test_not_found(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "progress", "Nonexistent"]):
            main()

        output = capsys.readouterr().out
        assert "not found" in output


# ── persona block ──────────────────────────────────────────────────────────

class TestBlock:
    def test_marks_task_blocked(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Blocked Task"]):
            main()
        with patch("sys.argv", ["persona", "block", "Blocked Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "blocked-task.md"
        content = task.read_text()
        assert "**Status:** Blocked" in content

    def test_logs_event(self, initialized_dir):
        with patch("sys.argv", ["persona", "start", "Block Log"]):
            main()
        with patch("sys.argv", ["persona", "block", "Block Log"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task blocked: Block Log" in log


# ── persona update ─────────────────────────────────────────────────────────

class TestUpdate:
    def test_updates_instructions(self, initialized_dir, capsys):
        # Tamper with version to simulate old template
        instructions = initialized_dir / ".github" / "copilot-instructions.md"
        instructions.write_text("# Old template v0.1.0\nStale content.")

        with patch("sys.argv", ["persona", "update"]):
            main()

        output = capsys.readouterr().out
        assert "Updated" in output
        content = instructions.read_text()
        assert "Three-Persona Architecture" in content

    def test_skip_if_same_version(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "update"]):
            main()

        output = capsys.readouterr().out
        assert "Already at" in output

    def test_force_regenerate(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "update", "--force"]):
            main()

        output = capsys.readouterr().out
        assert "Updated" in output

    def test_preserves_user_files(self, initialized_dir):
        # Write custom content to project.md
        project = initialized_dir / "docs" / "project.md"
        project.write_text("# My Custom Project")

        with patch("sys.argv", ["persona", "update", "--force"]):
            main()

        # project.md should be untouched
        assert project.read_text() == "# My Custom Project"


# ── persona resume token estimate ──────────────────────────────────────────

class TestResumeTokenEstimate:
    def test_shows_token_estimate(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "resume"]):
            main()

        output = capsys.readouterr().out
        assert "~" in output and "tokens" in output
        assert "default mode" in output

    def test_brief_mode_label(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "resume", "--brief"]):
            main()

        output = capsys.readouterr().out
        assert "brief mode" in output

    def test_full_mode_label(self, initialized_dir, capsys):
        with patch("sys.argv", ["persona", "resume", "--full"]):
            main()

        output = capsys.readouterr().out
        assert "full mode" in output


# ── persona init .gitkeep ──────────────────────────────────────────────────

class TestInitGitkeep:
    def test_creates_gitkeep_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["persona", "init"]):
            main()

        assert (tmp_path / "docs" / "tasks" / ".gitkeep").exists()
        assert (tmp_path / "docs" / "requirements" / ".gitkeep").exists()
