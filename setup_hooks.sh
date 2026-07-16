#!/bin/bash
# Keeli Git Hooks Setup

mkdir -p .git/hooks

# Pre-commit hook: Validate Keeli files
cat <<'HOOK' > .git/hooks/pre-commit
#!/bin/sh
python3 -m keeli.main validate
HOOK
chmod +x .git/hooks/pre-commit

# Post-commit hook: Log commit to Keeli audit
cat <<'HOOK' > .git/hooks/post-commit
#!/bin/sh
COMMIT=$(git rev-parse HEAD)
MESSAGE=$(git log -1 --pretty=%s)
python3 -m keeli.main sync # Ensure index is fresh
# We could add a 'log' command to main.py but history works too
# python3 -m keeli.main log "Commit: $COMMIT - $MESSAGE" --actor git
HOOK
chmod +x .git/hooks/post-commit

echo "Git hooks installed."
