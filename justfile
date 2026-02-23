# roomnl-stats task runner

# List available recipes
default:
    @just --list

# ── Python ──────────────────────────────────────────────────

# Run all Python checks (lint, format, typecheck, test)
check-py:
    poetry run ruff check pipeline/ tests/
    poetry run ruff format --check pipeline/ tests/
    poetry run mypy pipeline/
    poetry run pytest tests/ -x -q

# Run tests
test:
    poetry run pytest tests/ -x -q

# Lint and format
lint:
    poetry run ruff check pipeline/ tests/
    poetry run ruff format --check pipeline/ tests/

# Auto-fix lint and format issues
fix:
    poetry run ruff check --fix pipeline/ tests/
    poetry run ruff format pipeline/ tests/

# ── Frontend ────────────────────────────────────────────────

# Run all frontend checks (lint, typecheck, build)
check-fe:
    cd site && npm run lint && npm run check && npm run build

# Start dev server
dev:
    cd site && npm run dev

# Build static site
build:
    cd site && npm run build

# ── Pipeline ────────────────────────────────────────────────

# Scrape, fit model, and generate JSON data
generate:
    poetry run python -m pipeline.generate

# ── CI ──────────────────────────────────────────────────────

# Run all checks (Python + frontend)
check: check-py check-fe

# Auto-merge all open dependabot PRs that pass CI
automerge-dependabot:
    #!/usr/bin/env bash
    set -euo pipefail
    prs=$(gh pr list --author 'app/dependabot' --json number,title --jq '.[].number')
    if [ -z "$prs" ]; then
        echo "No open dependabot PRs."
        exit 0
    fi
    for pr in $prs; do
        title=$(gh pr view "$pr" --json title --jq '.title')
        # Check all CI checks passed
        status=$(gh pr checks "$pr" --json state --jq '[.[].state] | if all(. == "SUCCESS") then "pass" elif any(. == "PENDING") then "pending" else "fail" end')
        case "$status" in
            pass)
                echo "✓ PR #${pr}: ${title} — merging"
                gh pr merge "$pr" --squash --auto --delete-branch
                ;;
            pending)
                echo "⏳ PR #${pr}: ${title} — checks still running, enabling auto-merge"
                gh pr merge "$pr" --squash --auto --delete-branch
                ;;
            *)
                echo "✗ PR #${pr}: ${title} — checks failed, skipping"
                ;;
        esac
    done
