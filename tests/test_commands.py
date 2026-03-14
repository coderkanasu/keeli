import sqlite3
import json
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

import pytest

from keeli.main import main


@pytest.fixture
def initialized_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["keeli", "init"]):
        main()
    return tmp_path


def _db_row(db_path: Path, query: str, params: tuple = ()):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query, params).fetchone()


def _db_value(db_path: Path, query: str, params: tuple = ()):
    row = _db_row(db_path, query, params)
    return None if row is None else row[0]


def _add_completion_evidence(task_path: Path) -> None:
    text = task_path.read_text()
    text = text.replace(
        "<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->",
        "- Commit: abcdef123456\n- Artifact: docs/ai_log.md",
    )
    text = text.replace(
        "<!-- Link validation artifacts (tests, checks, commands with outcomes). -->",
        "- Test: pytest -q (pass)\n- Report: tests/test_commands.py",
    )
    task_path.write_text(text)


class TestInit:
    def test_init_creates_framework_files_and_state_db(self, initialized_dir):
        assert (initialized_dir / ".github" / "copilot-instructions.md").exists()
        assert (initialized_dir / "docs" / "project.md").exists()
        assert (initialized_dir / "docs" / "tasks" / ".gitkeep").exists()
        assert (initialized_dir / "docs" / "requirements" / ".gitkeep").exists()
        assert (initialized_dir / "keeli_state.db").exists()

    def test_state_db_has_core_tables(self, initialized_dir):
        db_path = initialized_dir / "keeli_state.db"
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert {"state_meta", "work_items", "audit_events"}.issubset(tables)


class TestEpicStoryTask:
    def test_epic_creation_populates_file_and_db(self, initialized_dir):
        with patch(
            "sys.argv",
            ["keeli", "epic", "Build State Machine", "-p", "P0", "-o", "Replace markdown state"],
        ):
            main()

        epic = initialized_dir / "docs" / "tasks" / "epic-build-state-machine.md"
        assert epic.exists()
        assert "Replace markdown state" in epic.read_text()

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT item_type, slug, priority, status FROM work_items WHERE slug = ?",
            ("epic-build-state-machine",),
        )
        assert row["item_type"] == "epic"
        assert row["priority"] == "P0"
        assert row["status"] == "Backlog"

    def test_story_creation_uses_simple_user_story_and_acceptance_criteria(self, initialized_dir):
        with patch("sys.argv", ["keeli", "epic", "Auth Epic", "-p", "P1", "-o", "Auth goal"]):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "story",
                "User can login",
                "--epic",
                "auth-epic",
                "--role",
                "user",
                "--goal",
                "log in",
                "--reason",
                "access the app",
                "--ac",
                "Login succeeds with valid credentials",
                "--ac",
                "Invalid password shows an error",
                "-p",
                "P1",
            ],
        ):
            main()

        story = initialized_dir / "docs" / "tasks" / "story-user-can-login.md"
        text = story.read_text()
        assert "As a user, I want log in so that I can access the app." in text
        assert "Login succeeds with valid credentials" in text
        assert "Invalid password shows an error" in text

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT item_type, epic_slug FROM work_items WHERE slug = ?",
            ("story-user-can-login",),
        )
        assert row["item_type"] == "story"
        assert row["epic_slug"] == "auth-epic"

    def test_task_creation_syncs_to_db_with_persona(self, initialized_dir):
        with patch(
            "sys.argv",
            [
                "keeli",
                "start",
                "Create SQLite schema",
                "-k",
                "architect",
                "-p",
                "P0",
                "-o",
                "Design state database schema",
            ],
        ):
            main()

        task = initialized_dir / "docs" / "tasks" / "create-sqlite-schema.md"
        text = task.read_text()
        assert "**Persona:** @architect" in text
        assert "Design state database schema" in text

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT persona, priority, item_type FROM work_items WHERE slug = ?",
            ("create-sqlite-schema",),
        )
        assert row["persona"] == "@architect"
        assert row["priority"] == "P0"
        assert row["item_type"] == "task"


class TestBugAndFeature:
    def test_bug_renders_description_and_found_during(self, initialized_dir):
        with patch(
            "sys.argv",
            [
                "keeli",
                "bug",
                "Login crash",
                "-d",
                "Happens when session is expired",
                "--found-during",
                "implement-auth",
            ],
        ):
            main()

        bug = initialized_dir / "docs" / "tasks" / "bug-login-crash.md"
        text = bug.read_text()
        assert "Happens when session is expired" in text
        assert "**Found During:** implement-auth" in text

    def test_feature_renders_context_and_objective(self, initialized_dir):
        ctx = initialized_dir / "docs" / "requirements" / "payment-spec.md"
        ctx.write_text("# Payment Spec\n")

        with patch(
            "sys.argv",
            [
                "keeli",
                "feature",
                "Checkout Flow",
                "-c",
                str(ctx),
                "-o",
                "As a buyer, I want checkout so that I can pay",
            ],
        ):
            main()

        feature = initialized_dir / "docs" / "tasks" / "feat-checkout-flow.md"
        text = feature.read_text()
        assert "payment-spec.md" in text
        assert "## User Story" in text
        assert "As a buyer, I want checkout so that I can pay" in text


class TestLifecycle:
    def test_progress_updates_file_and_db(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Implement Login", "-o", "Build login flow"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Implement Login"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "implement-login.md"
        assert "**Status:** In Progress" in task.read_text()

        db_path = initialized_dir / "keeli_state.db"
        status = _db_value(
            db_path,
            "SELECT status FROM work_items WHERE slug = ?",
            ("implement-login",),
        )
        assert status == "In Progress"

    def test_complete_archives_and_marks_db_archived(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Ship Login", "-o", "Ship it"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "ship-login.md")
        with patch("sys.argv", ["keeli", "complete", "Ship Login"]):
            main()

        archived = initialized_dir / "docs" / "tasks" / "archive" / "ship-login.md"
        assert archived.exists()
        assert "**Status:** Completed" in archived.read_text()

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT status, archived, completed_at FROM work_items WHERE slug = ?",
            ("ship-login",),
        )
        assert row["status"] == "Completed"
        assert row["archived"] == 1
        assert row["completed_at"]

    def test_reopen_restores_archived_task_and_db_state(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Reopen Login", "-o", "Ship it"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "reopen-login.md")
        with patch("sys.argv", ["keeli", "complete", "Reopen Login"]):
            main()
        with patch("sys.argv", ["keeli", "reopen", "Reopen Login"]):
            main()

        live = initialized_dir / "docs" / "tasks" / "reopen-login.md"
        assert live.exists()
        assert "**Status:** In Progress" in live.read_text()

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT status, archived FROM work_items WHERE slug = ?",
            ("reopen-login",),
        )
        assert row["status"] == "In Progress"
        assert row["archived"] == 0

    def test_complete_syncs_parent_story_to_completed(self, initialized_dir):
        with patch("sys.argv", ["keeli", "epic", "Auth Epic", "-p", "P1", "-o", "Auth goal"]):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "story",
                "User can login",
                "--epic",
                "auth-epic",
                "--role",
                "user",
                "--goal",
                "log in",
                "--reason",
                "access the app",
                "--ac",
                "Login succeeds with valid credentials",
            ],
        ):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "start",
                "Implement login flow",
                "--epic",
                "auth-epic",
                "--story",
                "user-can-login",
                "-o",
                "Implement the login flow",
            ],
        ):
            main()

        task_path = initialized_dir / "docs" / "tasks" / "implement-login-flow.md"
        _add_completion_evidence(task_path)
        with patch("sys.argv", ["keeli", "complete", "Implement login flow"]):
            main()

        story_path = initialized_dir / "docs" / "tasks" / "story-user-can-login.md"
        story_text = story_path.read_text()
        assert "**Status:** Completed" in story_text
        assert "**Completed:** —" not in story_text

    def test_reopen_syncs_parent_story_back_to_in_progress(self, initialized_dir):
        with patch("sys.argv", ["keeli", "epic", "Auth Epic", "-p", "P1", "-o", "Auth goal"]):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "story",
                "User can login",
                "--epic",
                "auth-epic",
                "--role",
                "user",
                "--goal",
                "log in",
                "--reason",
                "access the app",
                "--ac",
                "Login succeeds with valid credentials",
            ],
        ):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "start",
                "Implement login flow",
                "--epic",
                "auth-epic",
                "--story",
                "user-can-login",
                "-o",
                "Implement the login flow",
            ],
        ):
            main()

        task_path = initialized_dir / "docs" / "tasks" / "implement-login-flow.md"
        _add_completion_evidence(task_path)
        with patch("sys.argv", ["keeli", "complete", "Implement login flow"]):
            main()
        with patch("sys.argv", ["keeli", "reopen", "Implement login flow"]):
            main()

        story_path = initialized_dir / "docs" / "tasks" / "story-user-can-login.md"
        story_text = story_path.read_text()
        assert "**Status:** In Progress" in story_text
        assert "**Completed:** —" in story_text


class TestListingAndStatus:
    def test_list_reads_from_db_backed_state(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "High Prio", "-p", "P0", "-o", "Do it"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Low Prio", "-p", "P2", "-o", "Do it"]):
            main()
        with patch("sys.argv", ["keeli", "list"]):
            main()

        output = capsys.readouterr().out
        assert "high-prio" in output
        assert "low-prio" in output

    def test_status_reports_state_database(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "status"]):
            main()

        output = capsys.readouterr().out
        assert "keeli_state.db" in output
        assert "Healthy" in output

    def test_next_json_returns_enveloped_task_payload(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Next", "-p", "P0", "-o", "Do it"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "next", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "next"
        assert payload["timestamp"]
        assert payload["data"]["task"] == "json-next"
        assert payload["data"]["priority"] == "P0"

    def test_list_json_returns_enveloped_items_payload(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json List", "-o", "Do it"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "list", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "list"
        assert payload["data"]["count"] >= 1
        assert any(item["task"] == "json-list" for item in payload["data"]["items"])

    def test_find_json_returns_enveloped_results_payload(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Find", "-o", "Do it"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "find", "json-find", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "find"
        assert payload["data"]["mode"] == "keyword"
        assert any(item["slug"] == "json-find" for item in payload["data"]["results"])

    def test_history_json_returns_enveloped_entries(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json History", "-o", "Do it"]):
            main()

        task_text = (initialized_dir / "docs" / "tasks" / "json-history.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "history", task_id, "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "history"
        assert payload["data"]["query"] == task_id
        assert payload["data"]["count"] >= 1
        assert any(task_id in entry for entry in payload["data"]["entries"])

    def test_digest_json_returns_enveloped_context(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Digest", "-o", "Do it"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "digest", "--budget", "500", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "digest"
        assert payload["data"]["budget"] == 500
        assert isinstance(payload["data"]["used_tokens"], int)
        assert isinstance(payload["data"]["context"], str)

    def test_snapshot_json_includes_kpi_metrics(self, initialized_dir, capsys):
        with patch(
            "sys.argv",
            [
                "keeli",
                "epic",
                "Governance Epic",
                "-p",
                "P1",
                "-o",
                "Governance objective",
            ],
        ):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "story",
                "Quality Story",
                "--epic",
                "governance-epic",
                "--role",
                "lead",
                "--goal",
                "stabilize quality",
                "--reason",
                "reduce defects",
                "--ac",
                "Quality checks are explicit",
            ],
        ):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "snapshot", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "snapshot"
        assert "kpi_metrics" in payload["data"]
        assert any(metric["name"] == "Hallucination rework rate" for metric in payload["data"]["kpi_metrics"])

    def test_snapshot_json_out_writes_file(self, initialized_dir):
        target = initialized_dir / "reports" / "snapshot.json"
        with patch("sys.argv", ["keeli", "snapshot", "--json-out", str(target)]):
            main()

        assert target.exists()
        payload = json.loads(target.read_text())
        assert payload["ok"] is True
        assert payload["command"] == "snapshot"


class TestCustomPrompts:
    def test_prompt_apply_renders_and_writes_output_file(self, initialized_dir):
        src = initialized_dir / "trello-template.md"
        src.write_text(
            "---\n"
            "persona: architect\n"
            "applies_to: connector-management\n"
            "priority: high\n"
            "---\n"
            "{\n"
            "  \"connector\": \"trello\",\n"
            "  \"board_id\": \"{{board_id}}\",\n"
            "  \"list_architect\": \"{{list_architect}}\"\n"
            "}\n"
        )

        with patch("sys.argv", ["keeli", "prompt", "add", "trello-manage", "--file", str(src)]):
            main()

        out_path = initialized_dir / ".keeli" / "connectors" / "trello.json"
        with patch(
            "sys.argv",
            [
                "keeli",
                "prompt",
                "apply",
                "trello-manage",
                "--var",
                "board_id=b-123",
                "--var",
                "list_architect=l-arch",
                "--output",
                str(out_path),
            ],
        ):
            main()

        assert out_path.exists()
        rendered = out_path.read_text()
        assert '{{board_id}}' not in rendered
        assert '"board_id": "b-123"' in rendered
        assert '"list_architect": "l-arch"' in rendered

    def test_prompt_apply_prints_rendered_content_without_output(self, initialized_dir, capsys):
        src = initialized_dir / "simple-template.md"
        src.write_text("Hello {{name}}")

        with patch("sys.argv", ["keeli", "prompt", "add", "hello-template", "--file", str(src)]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "prompt", "apply", "hello-template", "--var", "name=Keeli"]):
            main()

        output = capsys.readouterr().out
        assert "Hello Keeli" in output


class TestValidateTaskState:
    def test_passes_when_no_leaf_work_items_exist(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "validate-task-state"]):
            main()

        output = capsys.readouterr().out
        assert "Task state valid" in output

    def test_fails_when_leaf_task_exists_but_none_active(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Backlog Task", "-o", "Do the work"]):
            main()

        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["keeli", "validate-task-state"]):
                main()

        assert exc.value.code == 1

    def test_passes_when_task_is_in_progress(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Active Task", "-o", "Do the work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Active Task"]):
            main()
        with patch("sys.argv", ["keeli", "validate-task-state"]):
            main()

        output = capsys.readouterr().out
        assert "Task state valid" in output
        assert "active-task" in output

    def test_fails_on_pii_in_scanned_file(self, initialized_dir):
        sample = initialized_dir / "sample.txt"
        sample.write_text("contact me at test@example.com")

        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["keeli", "validate-task-state", "--paths", str(sample)]):
                main()

        assert exc.value.code == 1


class TestCaptureCommitState:
    def test_no_active_task_prints_info(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "capture-commit-state"]):
            main()

        output = capsys.readouterr().out
        assert "No active task" in output

    def test_active_task_logs_commit_metadata(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Track Commit", "-o", "Do the work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Track Commit"]):
            main()

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "abc123def4567890\n"
            else:
                result.stdout = "Add commit capture\n"
            return result

        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state"]):
                main()

        log_text = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert "Commit captured for track-commit" in log_text
        assert "abc123def456" in log_text

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT action, actor, details FROM audit_events WHERE action = 'commit' ORDER BY id DESC LIMIT 1",
        )
        assert row["action"] == "commit"
        assert row["actor"] == "git"
        assert "Add commit capture" in row["details"]


class TestOverwriteBehavior:
    def test_force_overwrite_preserves_existing_id(self, initialized_dir):
        with patch("sys.argv", ["keeli", "feature", "Overwrite Me", "-o", "First version"]):
            main()

        feature = initialized_dir / "docs" / "tasks" / "feat-overwrite-me.md"
        original_id = next(line.split()[-1] for line in feature.read_text().splitlines() if line.startswith("**ID:**"))

        with patch("sys.argv", ["keeli", "feature", "Overwrite Me", "-o", "Second version", "-f"]):
            main()

        text = feature.read_text()
        current_id = next(line.split()[-1] for line in text.splitlines() if line.startswith("**ID:**"))
        assert current_id == original_id
        assert "Second version" in text

        db_path = initialized_dir / "keeli_state.db"
        count = _db_value(
            db_path,
            "SELECT COUNT(*) FROM work_items WHERE slug = ?",
            ("feat-overwrite-me",),
        )
        assert count == 1


class TestStaleReconciliation:
    """_db_reconcile_stale_items() should archive rows whose source_path is gone."""

    def test_stale_in_progress_row_is_archived_on_reinit(self, initialized_dir):
        # Create a task and mark it In Progress
        with patch("sys.argv", ["keeli", "start", "Ghost Task", "-o", "Some work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Ghost Task"]):
            main()

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(db_path, "SELECT status, archived FROM work_items WHERE slug = ?", ("ghost-task",))
        assert row["status"] == "In Progress"
        assert row["archived"] == 0

        # Wipe docs/ to simulate a --force reinit scenario (file gone, row still in DB)
        import shutil
        shutil.rmtree(initialized_dir / "docs")

        # Run sync (called by init internally); do it directly by re-running init --force
        with patch("sys.argv", ["keeli", "init", "--force"]):
            main()

        # The old ghost-task row should now be archived
        row = _db_row(db_path, "SELECT status, archived FROM work_items WHERE slug = ?", ("ghost-task",))
        assert row is not None
        assert row["archived"] == 1
        assert row["status"] == "Archived"

    def test_audit_event_written_for_auto_archived_item(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Phantom Work", "-o", "Do it"]):
            main()

        import shutil
        shutil.rmtree(initialized_dir / "docs")

        with patch("sys.argv", ["keeli", "init", "--force"]):
            main()

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT action, actor FROM audit_events WHERE action = 'auto-archived' ORDER BY id DESC LIMIT 1",
        )
        assert row is not None
        assert row["action"] == "auto-archived"
        assert row["actor"] == "keeli-init"


class TestPiiRedaction:
    """_redact_pii() should sanitize sensitive data before it reaches the audit trail."""

    def test_email_is_redacted_in_audit_details(self, initialized_dir):
        from keeli.main import _db_log_event

        _db_log_event("T-0001", "test-action", actor="tester", details="Contact admin@example.com for help")

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(db_path, "SELECT details FROM audit_events WHERE action = 'test-action' ORDER BY id DESC LIMIT 1")
        assert row is not None
        assert "admin@example.com" not in row["details"]
        assert "[REDACTED-EMAIL]" in row["details"]

    def test_aws_key_is_redacted_in_audit_details(self, initialized_dir):
        from keeli.main import _db_log_event

        _db_log_event("T-0002", "deploy-action", actor="ci", details="Key: AKIAIOSFODNN7EXAMPLE")

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(db_path, "SELECT details FROM audit_events WHERE action = 'deploy-action' ORDER BY id DESC LIMIT 1")
        assert row is not None
        assert "AKIAIOSFODNN7EXAMPLE" not in row["details"]
        assert "[REDACTED-AWS-KEY]" in row["details"]

    def test_secret_assignment_is_redacted_in_audit_details(self, initialized_dir):
        from keeli.main import _db_log_event

        _db_log_event("T-0003", "config-action", actor="ci", details="token=supersecretvalue123")

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(db_path, "SELECT details FROM audit_events WHERE action = 'config-action' ORDER BY id DESC LIMIT 1")
        assert row is not None
        assert "supersecretvalue123" not in row["details"]
        assert "[REDACTED]" in row["details"]


class TestIterationFiveFeatures:
    def test_validate_auto_stub_creates_active_task(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Backlog Leaf", "-o", "Do work"]):
            main()

        with patch("sys.argv", ["keeli", "validate-task-state", "--auto-stub"]):
            main()

        output = capsys.readouterr().out
        assert "auto-created stub" in output

        db_path = initialized_dir / "keeli_state.db"
        row = _db_row(
            db_path,
            "SELECT status FROM work_items WHERE slug = ?",
            ("working-on-uncommitted-changes",),
        )
        assert row is not None
        assert row["status"] == "In Progress"

    def test_sync_rebuilds_db_from_markdown(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Sync Target", "-o", "Sync me"]):
            main()

        db_path = initialized_dir / "keeli_state.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM work_items WHERE slug = ?", ("sync-target",))
            conn.commit()

        missing = _db_row(db_path, "SELECT slug FROM work_items WHERE slug = ?", ("sync-target",))
        assert missing is None

        with patch("sys.argv", ["keeli", "sync"]):
            main()

        restored = _db_row(db_path, "SELECT status FROM work_items WHERE slug = ?", ("sync-target",))
        assert restored is not None
        assert restored["status"] == "Backlog"

    def test_capture_commit_transitions_to_review_on_closes_marker(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Commit Semantic", "-o", "Do work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Commit Semantic"]):
            main()

        task = initialized_dir / "docs" / "tasks" / "commit-semantic.md"
        task_text = task.read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "abc123def4567890\n"
            else:
                result.stdout = f"closes {task_id}\n"
            return result

        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state"]):
                main()

        updated = task.read_text()
        assert "**Status:** Review" in updated

    def test_capture_commit_completes_on_keeli_complete_marker(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Commit Complete", "-o", "Do work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Commit Complete"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "commit-complete.md")

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "f00ba41234123412\n"
            else:
                result.stdout = "keeli:complete\n"
            return result

        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state"]):
                main()

        archived = initialized_dir / "docs" / "tasks" / "archive" / "commit-complete.md"
        assert archived.exists()
        assert "**Status:** Completed" in archived.read_text()

    def test_test_command_auto_reviews_active_task_on_pass(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Pytest Gate", "-o", "Run tests"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Pytest Gate"]):
            main()

        class _Completed:
            returncode = 0

        with patch("keeli.main.subprocess.run", return_value=_Completed()):
            with pytest.raises(SystemExit) as exc:
                with patch("sys.argv", ["keeli", "test", "-q"]):
                    main()

        assert exc.value.code == 0
        task = initialized_dir / "docs" / "tasks" / "pytest-gate.md"
        assert "**Status:** Review" in task.read_text()


class TestIterationSixFeatures:
    def test_transition_from_commit_evaluates_multi_close_ids(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "A", "-o", "Work A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "B", "-o", "Work B"]):
            main()

        a_text = (initialized_dir / "docs" / "tasks" / "a.md").read_text()
        b_text = (initialized_dir / "docs" / "tasks" / "b.md").read_text()
        a_id = next(line.split()[-1] for line in a_text.splitlines() if line.startswith("**ID:**"))
        b_id = next(line.split()[-1] for line in b_text.splitlines() if line.startswith("**ID:**"))

        subject = f"feat: wiring closes {a_id}, {b_id}"
        with patch("sys.argv", ["keeli", "transition-from-commit", "--subject", subject]):
            main()

        raw = capsys.readouterr().out
        json_start = raw.find("{")
        payload = json.loads(raw[json_start:])
        assert payload["command"] == "transition-from-commit"
        assert payload["timestamp"]
        actions = payload["data"]["evaluation"]["actions"]
        review_action = next(a for a in actions if a["type"] == "review_ids")
        assert set(review_action["ids"]) == {a_id, b_id}

    def test_transition_from_commit_apply_moves_all_in_progress_close_ids_to_review(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "First Work", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Second Work", "-o", "B"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "First Work"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Second Work"]):
            main()

        first = (initialized_dir / "docs" / "tasks" / "first-work.md").read_text()
        second = (initialized_dir / "docs" / "tasks" / "second-work.md").read_text()
        first_id = next(line.split()[-1] for line in first.splitlines() if line.startswith("**ID:**"))
        second_id = next(line.split()[-1] for line in second.splitlines() if line.startswith("**ID:**"))

        with patch("sys.argv", ["keeli", "transition-from-commit", "--subject", f"chore: closes {first_id}, {second_id}", "--apply"]):
            main()

        assert "**Status:** Review" in (initialized_dir / "docs" / "tasks" / "first-work.md").read_text()
        assert "**Status:** Review" in (initialized_dir / "docs" / "tasks" / "second-work.md").read_text()

    def test_sync_dry_run_does_not_mutate_db(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Dry Sync", "-o", "Check"]):
            main()

        db_path = initialized_dir / "keeli_state.db"
        before = _db_value(db_path, "SELECT COUNT(*) FROM work_items")
        with patch("sys.argv", ["keeli", "sync", "--dry-run"]):
            main()
        after = _db_value(db_path, "SELECT COUNT(*) FROM work_items")

        assert before == after
        assert "[dry-run]" in capsys.readouterr().out

    def test_test_dry_run_exits_zero_without_running_pytest(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Dry Test", "-o", "Check"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Dry Test"]):
            main()

        with patch("keeli.main.subprocess.run") as fake_run:
            with pytest.raises(SystemExit) as exc:
                with patch("sys.argv", ["keeli", "test", "--dry-run", "-q"]):
                    main()

        assert exc.value.code == 0
        fake_run.assert_not_called()
        assert "**Status:** In Progress" in (initialized_dir / "docs" / "tasks" / "dry-test.md").read_text()


class TestIterationSevenFeatures:
    def test_transition_from_commit_parses_body_trailers(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Trailer Task", "-o", "A"]):
            main()
        task_text = (initialized_dir / "docs" / "tasks" / "trailer-task.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        capsys.readouterr()
        with patch(
            "sys.argv",
            [
                "keeli",
                "transition-from-commit",
                "--subject",
                "feat: refactor parser",
                "--body",
                f"Fixes: {task_id}",
            ],
        ):
            main()

        raw = capsys.readouterr().out
        payload = json.loads(raw[raw.find("{"):])
        assert payload["command"] == "transition-from-commit"
        review_action = next(a for a in payload["data"]["evaluation"]["actions"] if a["type"] == "review_ids")
        assert task_id in review_action["ids"]

    def test_transition_from_commit_apply_dry_run_returns_preview_without_mutation(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Dry Preview", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Dry Preview"]):
            main()
        task_text = (initialized_dir / "docs" / "tasks" / "dry-preview.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        capsys.readouterr()
        with patch(
            "sys.argv",
            [
                "keeli",
                "transition-from-commit",
                "--subject",
                f"feat: closes {task_id}",
                "--apply",
                "--dry-run",
            ],
        ):
            main()

        raw = capsys.readouterr().out
        payload = json.loads(raw[raw.find("{"):])
        assert payload["command"] == "transition-from-commit"
        preview = payload["data"]["preview"]
        assert preview
        first = preview[0]
        assert first["before"] == "In Progress"
        assert first["after"] == "Review"
        assert first["would_apply"] is True
        assert "**Status:** In Progress" in (initialized_dir / "docs" / "tasks" / "dry-preview.md").read_text()

    def test_capture_commit_state_json_output_includes_transitions(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Capture Json", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Capture Json"]):
            main()

        task_text = (initialized_dir / "docs" / "tasks" / "capture-json.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "1234567890abcdef\n"
            elif cmd[1:] == ["log", "-1", "--pretty=%s"]:
                result.stdout = f"closes {task_id}\n"
            else:
                result.stdout = ""
            return result

        capsys.readouterr()
        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state", "--json"]):
                main()

        raw = capsys.readouterr().out
        payload = json.loads(raw[raw.find("{"):])
        assert payload["ok"] is True
        assert payload["command"] == "capture-commit-state"
        assert payload["data"]["transitions"]
        assert any("moved to Review" in line for line in payload["data"]["transitions"])

    def test_capture_commit_state_reports_conflict_for_ambiguous_complete(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Ambiguous A", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Ambiguous B", "-o", "B"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Ambiguous A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Ambiguous B"]):
            main()

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "cafebabedeadbeef\n"
            elif cmd[1:] == ["log", "-1", "--pretty=%s"]:
                result.stdout = "keeli:complete\n"
            else:
                result.stdout = ""
            return result

        capsys.readouterr()
        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state", "--json"]):
                main()

        raw = capsys.readouterr().out
        payload = json.loads(raw[raw.find("{"):])
        assert payload["ok"] is False
        assert payload["command"] == "capture-commit-state"
        assert "Ambiguous commit intent" in payload["error"]
        assert "**Status:** In Progress" in (initialized_dir / "docs" / "tasks" / "ambiguous-a.md").read_text()
        assert "**Status:** In Progress" in (initialized_dir / "docs" / "tasks" / "ambiguous-b.md").read_text()


class TestIterationEightFeatures:
    def test_transition_from_commit_target_id_completes_explicit_task(self, initialized_dir):
        with patch("sys.argv", ["keeli", "start", "Target A", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Target B", "-o", "B"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Target A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Target B"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "target-b.md")

        target_b_text = (initialized_dir / "docs" / "tasks" / "target-b.md").read_text()
        target_b_id = next(line.split()[-1] for line in target_b_text.splitlines() if line.startswith("**ID:**"))

        with patch(
            "sys.argv",
            [
                "keeli",
                "transition-from-commit",
                "--subject",
                "keeli:complete",
                "--target-id",
                target_b_id,
                "--apply",
            ],
        ):
            main()

        assert "**Status:** In Progress" in (initialized_dir / "docs" / "tasks" / "target-a.md").read_text()
        archived_b = initialized_dir / "docs" / "tasks" / "archive" / "target-b.md"
        assert archived_b.exists()
        assert "**Status:** Completed" in archived_b.read_text()

    def test_capture_commit_state_json_includes_correlated_audit_id(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Audit Trail", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Audit Trail"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "audit-trail.md")

        def fake_run(cmd, check, capture_output, text):
            result = MagicMock()
            if cmd[1:] == ["rev-parse", "HEAD"]:
                result.stdout = "1111222233334444\n"
            elif cmd[1:] == ["log", "-1", "--pretty=%s"]:
                result.stdout = "keeli:complete\n"
            else:
                result.stdout = "\n"
            return result

        capsys.readouterr()
        with patch("keeli.main.subprocess.run", side_effect=fake_run):
            with patch("sys.argv", ["keeli", "capture-commit-state", "--json"]):
                main()

        raw = capsys.readouterr().out
        payload = json.loads(raw[raw.find("{"):])
        assert payload["ok"] is True
        assert payload["command"] == "capture-commit-state"
        assert isinstance(payload["data"]["commit_event_id"], int)
        assert any("audit_event=" in line for line in payload["data"]["transitions"])

        log_text = (initialized_dir / "docs" / "ai_log.md").read_text()
        assert f"[audit:{payload['data']['commit_event_id']}]" in log_text

    def test_progress_and_complete_support_json_output(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Flow", "-o", "A"]):
            main()
        _add_completion_evidence(initialized_dir / "docs" / "tasks" / "json-flow.md")

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "progress", "Json Flow", "--json"]):
            main()
        progress_payload = json.loads(capsys.readouterr().out)
        assert progress_payload["ok"] is True
        assert progress_payload["command"] == "progress"
        assert progress_payload["timestamp"]
        assert progress_payload["data"]["after"] == "In Progress"

        with patch("sys.argv", ["keeli", "complete", "Json Flow", "--json"]):
            main()
        complete_payload = json.loads(capsys.readouterr().out)
        assert complete_payload["ok"] is True
        assert complete_payload["command"] == "complete"
        assert complete_payload["data"]["after"] == "Completed"
        assert complete_payload["data"]["archived"] is True

    def test_block_review_and_reopen_support_json_output(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Lifecycle", "-o", "A"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "block", "Json Lifecycle", "--json"]):
            main()
        block_payload = json.loads(capsys.readouterr().out)
        assert block_payload["ok"] is True
        assert block_payload["command"] == "block"
        assert block_payload["data"]["after"] == "Blocked"

        with patch("sys.argv", ["keeli", "review", "Json Lifecycle", "--json"]):
            main()
        review_payload = json.loads(capsys.readouterr().out)
        assert review_payload["ok"] is True
        assert review_payload["command"] == "review"
        assert review_payload["data"]["before"] == "Blocked"
        assert review_payload["data"]["after"] == "Review"

        with patch("sys.argv", ["keeli", "reopen", "Json Lifecycle", "--json"]):
            main()
        reopen_payload = json.loads(capsys.readouterr().out)
        assert reopen_payload["ok"] is True
        assert reopen_payload["command"] == "reopen"
        assert reopen_payload["data"]["before"] == "Review"
        assert reopen_payload["data"]["after"] == "In Progress"

    def test_transition_from_commit_apply_outputs_strict_json(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Strict Json A", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Strict Json B", "-o", "B"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Strict Json A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Strict Json B"]):
            main()

        task_text = (initialized_dir / "docs" / "tasks" / "strict-json-b.md").read_text()
        task_id = next(line.split()[-1] for line in task_text.splitlines() if line.startswith("**ID:**"))

        capsys.readouterr()
        with patch(
            "sys.argv",
            [
                "keeli",
                "transition-from-commit",
                "--subject",
                "keeli:complete",
                "--target-id",
                task_id,
                "--apply",
            ],
        ):
            main()

        raw = capsys.readouterr().out
        assert raw.lstrip().startswith("{")
        payload = json.loads(raw)
        assert payload["command"] == "transition-from-commit"
        assert payload["data"]["evaluation"]["explicit_target"] == task_id
        assert payload["data"]["applied"]

    def test_sync_json_dry_run_output(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "sync", "--dry-run", "--json"]):
            main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "sync"
        assert payload["data"]["dry_run"] is True
        assert "predicted_items" in payload["data"]

    def test_test_json_dry_run_output(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Test Dry", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Json Test Dry"]):
            main()

        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["keeli", "test", "--dry-run", "--json", "-q"]):
                main()
        assert exc.value.code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "test"
        assert payload["data"]["dry_run"] is True
        assert payload["data"]["transition_target"]["slug"] == "json-test-dry"

    def test_test_json_success_includes_transition(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Json Test Pass", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Json Test Pass"]):
            main()

        class _Completed:
            returncode = 0

        capsys.readouterr()
        with patch("keeli.main.subprocess.run", return_value=_Completed()):
            with pytest.raises(SystemExit) as exc:
                with patch("sys.argv", ["keeli", "test", "--json", "-q"]):
                    main()
        assert exc.value.code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "test"
        assert payload["data"]["returncode"] == 0
        assert payload["data"]["transition"]["slug"] == "json-test-pass"
        assert payload["data"]["transition"]["after"] == "Review"


class TestArchitectImprovements:
    def test_list_and_find_accept_in_progress_alias(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Alias Match", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Alias Match"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "list", "--status", "in-progress", "--json"]):
            main()
        list_payload = json.loads(capsys.readouterr().out)
        assert list_payload["ok"] is True
        assert any(item["task"] == "alias-match" for item in list_payload["data"]["items"])

        with patch("sys.argv", ["keeli", "find", "alias-match", "--status", "in-progress", "--json"]):
            main()
        find_payload = json.loads(capsys.readouterr().out)
        assert find_payload["ok"] is True
        assert any(item["slug"] == "alias-match" for item in find_payload["data"]["results"])

    def test_list_refreshes_db_after_manual_markdown_edit(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Needs Refresh", "-o", "A"]):
            main()

        task_path = initialized_dir / "docs" / "tasks" / "needs-refresh.md"
        task_text = task_path.read_text().replace("**Status:** Backlog", "**Status:** Blocked")
        task_path.write_text(task_text)

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "list", "--status", "blocked", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert any(item["task"] == "needs-refresh" for item in payload["data"]["items"])

    def test_complete_scaffold_missing_populates_placeholders(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Evidence Scaffold", "-o", "A"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "complete", "Evidence Scaffold", "--scaffold-missing", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "complete"
        assert payload["data"]["archived"] is True

        task_text = (initialized_dir / "docs" / "tasks" / "archive" / "evidence-scaffold.md").read_text()
        assert "- Delivery artifact: docs/ai_log.md" in task_text
        assert "- Test command: pytest -q" in task_text

    def test_progress_json_includes_story_rollup(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "epic", "Rollup Epic", "-p", "P1", "-o", "Goal"]):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "story",
                "Rollup Story",
                "--epic",
                "rollup-epic",
                "--role",
                "user",
                "--goal",
                "ship",
                "--reason",
                "value",
                "--ac",
                "Done",
            ],
        ):
            main()
        with patch(
            "sys.argv",
            [
                "keeli",
                "start",
                "Rollup Child",
                "--epic",
                "rollup-epic",
                "--story",
                "rollup-story",
                "-o",
                "Implement",
            ],
        ):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "progress", "Rollup Child", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        rollup = payload["data"]["story_rollup"]
        assert rollup is not None
        assert rollup["updated"] is True
        assert rollup["after"] == "In Progress"

    def test_doctor_json_reports_multiple_in_progress(self, initialized_dir, capsys):
        with patch("sys.argv", ["keeli", "start", "Hung A", "-o", "A"]):
            main()
        with patch("sys.argv", ["keeli", "start", "Hung B", "-o", "B"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Hung A"]):
            main()
        with patch("sys.argv", ["keeli", "progress", "Hung B"]):
            main()

        capsys.readouterr()
        with patch("sys.argv", ["keeli", "doctor", "--json"]):
            main()

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "doctor"
        assert payload["data"]["in_progress_count"] == 2
        assert len(payload["data"]["in_progress_items"]) == 2

