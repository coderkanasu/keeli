"""Tests for `keeli init` command."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

# We test by invoking main() directly with patched sys.argv
from keeli.main import main


@pytest.fixture
def clean_dir(tmp_path, monkeypatch):
    """Run each test inside a fresh temporary directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestInit:
    def test_creates_all_files(self, clean_dir):
        with patch("sys.argv", ["keeli", "init"]):
            main()

        assert (clean_dir / ".github" / "copilot-instructions.md").exists()
        assert (clean_dir / "docs" / "project.md").exists()
        assert (clean_dir / "docs" / "decision.md").exists()
        assert (clean_dir / "docs" / "ai_log.md").exists()
        assert (clean_dir / "docs" / "tasks").is_dir()
        assert (clean_dir / "docs" / "requirements").is_dir()
        assert (clean_dir / ".gitignore").exists()

    def test_does_not_overwrite_without_force(self, clean_dir):
        marker = "DO NOT OVERWRITE"
        (clean_dir / ".github").mkdir()
        (clean_dir / ".github" / "copilot-instructions.md").write_text(marker)

        with patch("sys.argv", ["keeli", "init"]):
            main()

        content = (clean_dir / ".github" / "copilot-instructions.md").read_text()
        assert content == marker

    def test_overwrites_with_force(self, clean_dir):
        marker = "DO NOT OVERWRITE"
        (clean_dir / ".github").mkdir()
        (clean_dir / ".github" / "copilot-instructions.md").write_text(marker)

        with patch("sys.argv", ["keeli", "init", "--force"]):
            main()

        content = (clean_dir / ".github" / "copilot-instructions.md").read_text()
        assert content != marker
        assert "Four-Persona Architecture" in content

    def test_gitignore_appends_if_exists(self, clean_dir):
        (clean_dir / ".gitignore").write_text("node_modules/\n")

        with patch("sys.argv", ["keeli", "init"]):
            main()

        content = (clean_dir / ".gitignore").read_text()
        assert "node_modules/" in content
        assert "docs/ai_log.md" in content

    def test_schema_version_in_files(self, clean_dir):
        from keeli.templates import SCHEMA_VERSION

        with patch("sys.argv", ["keeli", "init"]):
            main()

        for f in ["docs/project.md", "docs/decision.md", ".github/copilot-instructions.md"]:
            content = (clean_dir / f).read_text()
            assert SCHEMA_VERSION in content, f"{f} missing schema version"
