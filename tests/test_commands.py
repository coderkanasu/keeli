"""Tests for `keeli start`, `keeli log`, `keeli resume`, `keeli status`, `keeli clear-log`."""

import pytest
from pathlib import Path
from unittest.mock import patch

from keeli.main import main


@pytest.fixture
def initialized_dir(tmp_path, monkeypatch):
    """Run `persona init` in a temp dir and return the path."""
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["keeli", "init"]):
        main()
    return tmp_path


# ── persona start ──────────────────────────────────────────────────────────

class TestStart:
    def test_creates_task_file(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Implement Auth"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "implement-auth.md"
        assert task.exists()
        content = task.read_text()
        assert "Implement Auth" in content
        # default persona is @architect
        assert "- [ ] Define the interfaces and contracts first" in content
        assert "**Persona:** @architect" in content
        assert "**Priority:** P1" in content  # default priority

    def test_persona_developer_checklist(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Build Route", "-k", "developer"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "build-route.md"
        content = task.read_text()
        assert "**Persona:** @developer" in content
        assert "- [ ] Write the failing test first (red), then implement (green), then refactor" in content

    def test_persona_security_checklist(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Audit Login", "-k", "security"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "audit-login.md"
        content = task.read_text()
        assert "**Persona:** @security" in content
        assert "- [ ] Threat model: enumerate attack surfaces for this change" in content

    def test_persona_author_checklist(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Write Docs", "-k", "author"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "write-docs.md"
        content = task.read_text()
        assert "**Persona:** @author" in content
        assert "- [ ] Write from the user's perspective, not the implementer's" in content

    def test_slugifies_name(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Fix Bug #42!!"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "fix-bug-42.md"
        assert task.exists()

    def test_links_context_file(self, initialized_dir):
        ctx = initialized_dir / "docs" / "requirements" / "auth-spec.md"
        ctx.write_text("# Auth Spec\nDetails here.")

        with patch("sys.argv", ["keeli", "start", "Auth Feature", "-c", str(ctx)]):
            main()

        task = initialized_dir / "docs" / "tasks" / "auth-feature.md"
        content = task.read_text()
        assert "auth-spec.md" in content

    def test_does_not_overwrite_without_force(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "My Task"]):
            main()
        marker = "ORIGINAL"
        (initialized_dir / "docs" / "tasks" / "my-task.md").write_text(marker)

        with patch("sys.argv", ["keeli", "start", "My Task"]):
            main()

        content = (initialized_dir / "docs" / "tasks" / "my-task.md").read_text()
        assert content == marker

    def test_auto_logs_creation(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "New Feature"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task created: New Feature" in log

    def test_priority_flag(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Critical Fix", "-p", "P0"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "critical-fix.md"
        content = task.read_text()
        assert "**Priority:** P0" in content


# ── persona complete ───────────────────────────────────────────────────────

class TestComplete:
    def test_marks_task_completed(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "My Task"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "My Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "archive" / "my-task.md"
        content = task.read_text()
        assert "**Status:** Completed" in content
        assert "**Completed:** 20" in content  # timestamp starts with year

    def test_logs_completion(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Log Test"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Log Test"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task completed: Log Test" in log

    def test_suggests_next_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "First Task", "-p", "P0"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Second Task", "-p", "P1"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "First Task"]):
            main()

        output = capsys.readouterr().out
        assert "Next task:" in output
        assert "second-task" in output

    def test_all_done_message(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Only Task"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Only Task"]):
            main()

        output = capsys.readouterr().out
        assert "All tasks are complete" in output

    def test_already_completed(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Done Task"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Done Task"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Done Task"]):
            main()

        output = capsys.readouterr().out
        assert "already marked as Completed" in output


# ── persona next ───────────────────────────────────────────────────────────

class TestNext:
    def test_shows_highest_priority_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Low Prio", "-p", "P2"]):
            main()
        with patch("sys.argv", ["keeli", "start", "High Prio", "-p", "P0"]):
            main()
        with patch("sys.argv", ["keeli", "next", "-q"]):
            main()

        output = capsys.readouterr().out
        assert "high-prio" in output

    def test_no_tasks_remaining(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "next"]):
            main()

        output = capsys.readouterr().out
        assert "All tasks are complete" in output


# ── persona log ────────────────────────────────────────────────────────────

class TestLog:
    def test_appends_timestamped_entry(self, initialized_dir):
        with patch("sys.argv", ["keeli", "log", "Fixed auth bug"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Fixed auth bug" in log
        # Check ISO timestamp format (YYYY-MM-DDT)
        assert "T" in log.splitlines()[-1]

    def test_multiple_entries(self, initialized_dir):
        for msg in ["First entry", "Second entry", "Third entry"]:
            with patch("sys.argv", ["keeli", "log", msg]):
                main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "First entry" in log
        assert "Third entry" in log


# ── persona resume ─────────────────────────────────────────────────────────

class TestResume:
    def test_brief_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Active Task"]):
            main()

        with patch("sys.argv", ["keeli", "resume", "--brief"]):
            main()

        output = capsys.readouterr().out
        assert "Project" in output or "Active Tasks" in output

    def test_full_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "resume", "--full"]):
            main()

        output = capsys.readouterr().out
        assert "Keeli Framework" in output

    def test_default_mode(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "resume"]):
            main()

        output = capsys.readouterr().out
        assert "Keeli Framework" in output


# ── persona status ─────────────────────────────────────────────────────────

class TestStatus:
    def test_healthy_after_init(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "status"]):
            main()

        output = capsys.readouterr().out
        assert "Healthy" in output

    def test_unhealthy_when_file_missing(self, initialized_dir, capsys):
        (initialized_dir / "docs" / "decision.md").unlink()

        with patch("sys.argv", ["keeli", "status"]):
            main()

        output = capsys.readouterr().out
        assert "Incomplete" in output


# ── persona clear-log ──────────────────────────────────────────────────────

class TestClearLog:
    def test_clears_log(self, initialized_dir):
        with patch("sys.argv", ["keeli", "log", "Some noise"]):
            main()
        with patch("sys.argv", ["keeli", "clear-log"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Some noise" not in log
        assert "AI Audit Log" in log


# ── persona progress ───────────────────────────────────────────────────────

class TestProgress:
    def test_marks_task_in_progress(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "My Task"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "My Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "my-task.md"
        content = task.read_text()
        assert "**Status:** In Progress" in content

    def test_logs_event(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Log Progress"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Log Progress"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task started: Log Progress" in log

    def test_already_in_progress(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "WIP Task"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "WIP Task"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "WIP Task"]):
            main()

        output = capsys.readouterr().out
        assert "already In Progress" in output

    def test_not_found(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "progress", "Nonexistent"]):
            main()

        output = capsys.readouterr().out
        assert "not found" in output


# ── persona block ──────────────────────────────────────────────────────────

class TestBlock:
    def test_marks_task_blocked(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Blocked Task"]):
            main()
        with patch("sys.argv", ["keeli", "block", "Blocked Task"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "blocked-task.md"
        content = task.read_text()
        assert "**Status:** Blocked" in content

    def test_logs_event(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Block Log"]):
            main()
        with patch("sys.argv", ["keeli", "block", "Block Log"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task blocked: Block Log" in log


# ── persona update ─────────────────────────────────────────────────────────

class TestUpdate:
    def test_updates_instructions(self, initialized_dir, capsys):
        # Tamper with version to simulate old template
        instructions = initialized_dir / ".github" / "copilot-instructions.md"
        instructions.write_text("# Old template v0.1.0\nStale content.")

        with patch("sys.argv", ["keeli", "update"]):
            main()

        output = capsys.readouterr().out
        assert "Updated" in output
        content = instructions.read_text()
        assert "Five-Persona Architecture" in content

    def test_skip_if_same_version(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "update"]):
            main()

        output = capsys.readouterr().out
        assert "Already at" in output

    def test_force_regenerate(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "update", "--force"]):
            main()

        output = capsys.readouterr().out
        assert "Updated" in output

    def test_preserves_user_files(self, initialized_dir):
        # Write custom content to project.md
        project = initialized_dir / "docs" / "project.md"
        project.write_text("# My Custom Project")

        with patch("sys.argv", ["keeli", "update", "--force"]):
            main()

        # project.md should be untouched
        assert project.read_text() == "# My Custom Project"


# ── persona resume token estimate ──────────────────────────────────────────

class TestResumeTokenEstimate:
    def test_shows_token_estimate(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "resume"]):
            main()

        output = capsys.readouterr().out
        assert "~" in output and "tokens" in output
        assert "default mode" in output

    def test_brief_mode_label(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "resume", "--brief"]):
            main()

        output = capsys.readouterr().out
        assert "brief mode" in output

    def test_full_mode_label(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "resume", "--full"]):
            main()

        output = capsys.readouterr().out
        assert "full mode" in output


# ── persona init .gitkeep ──────────────────────────────────────────────────

class TestInitGitkeep:
    def test_creates_gitkeep_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["keeli", "init"]):
            main()

        assert (tmp_path / "docs" / "tasks" / ".gitkeep").exists()
        assert (tmp_path / "docs" / "requirements" / ".gitkeep").exists()


# ── persona reopen ─────────────────────────────────────────────────────────

class TestReopen:
    def test_reopens_completed_task(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Reopen Me"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Reopen Me"]):
            main()
        with patch("sys.argv", ["keeli", "reopen", "Reopen Me"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "reopen-me.md"
        content = task.read_text()
        assert "**Status:** In Progress" in content
        assert "**Completed:** —" in content

    def test_logs_reopen_event(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Log Reopen"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Log Reopen"]):
            main()
        with patch("sys.argv", ["keeli", "reopen", "Log Reopen"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Task reopened: Log Reopen" in log

    def test_cannot_reopen_backlog_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Backlog Task"]):
            main()
        with patch("sys.argv", ["keeli", "reopen", "Backlog Task"]):
            main()

        output = capsys.readouterr().out
        assert "reopen only works on Completed or Review" in output

    def test_reopen_not_found(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "reopen", "Nonexistent"]):
            main()

        output = capsys.readouterr().out
        assert "not found" in output


# ── persona bug ────────────────────────────────────────────────────────────

class TestBug:
    def test_creates_bug_report(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Login crash"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "bug-login-crash.md"
        assert task.exists()
        content = task.read_text()
        assert "# Bug: Login crash" in content
        assert "**Priority:** P0" in content  # default for bugs
        assert "- [ ] Write regression test" in content

    def test_bug_with_description(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "NullPointer in OrderService", "-d", "Happens when order.qty is null"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "bug-nullpointer-in-orderservice.md"
        content = task.read_text()
        assert "Happens when order.qty is null" in content

    def test_bug_with_priority(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Minor typo", "-p", "P2"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "bug-minor-typo.md"
        content = task.read_text()
        assert "**Priority:** P2" in content

    def test_bug_with_found_during(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Race condition", "--found-during", "implement-auth"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "bug-race-condition.md"
        content = task.read_text()
        assert "implement-auth" in content

    def test_bug_logs_event(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Auth bypass"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Bug reported: Auth bypass" in log

    def test_bug_no_overwrite_without_force(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Dup Bug"]):
            main()
        marker = "ORIGINAL"
        (initialized_dir / "docs" / "tasks" / "bug-dup-bug.md").write_text(marker)

        with patch("sys.argv", ["keeli", "bug", "Dup Bug"]):
            main()
        assert (initialized_dir / "docs" / "tasks" / "bug-dup-bug.md").read_text() == marker


# ── persona init skills ───────────────────────────────────────────────────

class TestInitSkills:
    def test_project_md_has_skills(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["keeli", "init"]):
            main()

        content = (tmp_path / "docs" / "project.md").read_text()
        assert "Java" in content
        assert "Spring Framework" in content
        assert "React" in content
        assert "React Native" in content
        assert "AngularJS" in content
        assert "Python" in content
        assert "Trading" in content


# ── keeli feature ──────────────────────────────────────────────────────────

class TestFeature:
    def test_creates_feature_file(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Dark Mode Support"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "feat-dark-mode-support.md"
        assert task.exists()
        content = task.read_text()
        assert "# Feature: Dark Mode Support" in content
        assert "**Priority:** P1" in content  # default
        assert "## User Story" in content
        assert "## Acceptance Criteria" in content
        assert "## Design Notes" in content
        assert "- [ ] @author docs updated" in content

    def test_feature_with_priority(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Payment Gateway", "-p", "P0"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "feat-payment-gateway.md"
        assert "**Priority:** P0" in task.read_text()

    def test_feature_with_context(self, initialized_dir):
        ctx = initialized_dir / "docs" / "requirements" / "payment-spec.md"
        ctx.write_text("# Payment Spec")

        with patch("sys.argv", ["keeli", "feature", "Checkout Flow", "-c", str(ctx)]):
            main()

        task = initialized_dir / "docs" / "tasks" / "feat-checkout-flow.md"
        assert "payment-spec.md" in task.read_text()

    def test_feature_logs_event(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Search Bar"]):
            main()

        log = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Feature created: Search Bar" in log

    def test_feature_no_overwrite_without_force(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Dup Feature"]):
            main()
        marker = "ORIGINAL"
        (initialized_dir / "docs" / "tasks" / "feat-dup-feature.md").write_text(marker)

        with patch("sys.argv", ["keeli", "feature", "Dup Feature"]):
            main()
        assert (initialized_dir / "docs" / "tasks" / "feat-dup-feature.md").read_text() == marker

    def test_feature_force_overwrites(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Overwrite Me"]):
            main()
        (initialized_dir / "docs" / "tasks" / "feat-overwrite-me.md").write_text("OLD")

        with patch("sys.argv", ["keeli", "feature", "Overwrite Me", "-f"]):
            main()

        content = (initialized_dir / "docs" / "tasks" / "feat-overwrite-me.md").read_text()
        assert "# Feature: Overwrite Me" in content


# ── cross-prefix task resolution ──────────────────────────────────────────

class TestPrefixResolution:
    """complete / progress / block / reopen should find bug- and feat- files."""

    def test_complete_resolves_bug_prefix(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Some Bug"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Some Bug"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "archive" / "bug-some-bug.md"
        from keeli.main import _parse_task_field
        assert _parse_task_field(task.read_text(), "Status") == "Completed"

    def test_complete_resolves_feat_prefix(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Cool Feature"]):
            main()
        with patch("sys.argv", ["keeli", "complete", "Cool Feature"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "archive" / "feat-cool-feature.md"
        from keeli.main import _parse_task_field
        assert _parse_task_field(task.read_text(), "Status") == "Completed"

    def test_progress_resolves_bug_prefix(self, initialized_dir):
        with patch("sys.argv", ["keeli", "bug", "Flaky Test"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Flaky Test"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "bug-flaky-test.md"
        from keeli.main import _parse_task_field
        assert _parse_task_field(task.read_text(), "Status") == "In Progress"

    def test_reopen_resolves_feat_prefix(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Dark Theme"]):
            main()
        # Complete it first, then reopen
        task = initialized_dir / "docs" / "tasks" / "feat-dark-theme.md"
        from keeli.main import _update_task_field, _parse_task_field
        task.write_text(_update_task_field(task.read_text(), "Status", "Completed"))

        with patch("sys.argv", ["keeli", "reopen", "Dark Theme"]):
            main()
        assert _parse_task_field(task.read_text(), "Status") == "In Progress"
