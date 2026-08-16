# Kyverno AI Maintainer Assistant — Prototype

A read-only proof-of-concept demonstrating two core capabilities of the proposed [AI Maintainer Assistant](https://github.com/kyverno/kyverno/issues/16665) for the Kyverno project.

## What This Does

### 1. Diff-to-Test-Scope Mapper (Deterministic, No LLM)
Given a PR's changed file paths, outputs exactly which unit tests, conformance tests, and integration tests should run — instead of the full suite. Uses static path-to-test mapping based on Kyverno's repository structure.

### 2. Issue Triage Classifier (LLM-based, Multi-label)
Given a GitHub issue (title + body), classifies it by `kind` (bug/feature/question/cleanup), `area` (engine/cli/webhooks/etc.), and priority — with confidence scores that determine whether to auto-label or escalate to a human.

### 3. Tamper-Evident Audit Log
Every decision made by either module is logged as an append-only JSONL record with hash-chain integrity. Any tampering is detectable.

## What This Does NOT Do

> **This prototype is read-only.** It makes zero writes to GitHub.

- ❌ No labels are applied
- ❌ No comments are posted
- ❌ No PRs are merged or created
- ❌ No GitHub App or webhook server
- ❌ No sandboxed agent runtime
- ❌ No KinD cluster for issue reproduction
- ❌ No Slack/Discussions bot

These are all **future phases** described in [DESIGN.md](DESIGN.md).

## Quick Start

```bash
# Clone and setup
cd kyverno-ai-maintainer-poc
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure (copy and edit)
cp .env.example .env
# Edit .env with your GitHub token and LLM API key

# Classify a specific issue
python -m src.cli triage --issue 16665

# Map a PR's diff to tests
python -m src.cli map-tests --pr 12345

# Run full evaluation
python -m src.cli eval --mode triage --count 50
python -m src.cli eval --mode mapper --count 20

# Verify audit log integrity
python -m src.cli audit --log data/audit/decisions.jsonl

# Run unit tests
pytest tests/ -v
```

## Evaluation

The eval harness runs both features against real historical Kyverno data:

- **Triage**: Classifies 50 recent closed issues, compares against actual maintainer-applied labels, and reports accuracy, per-category precision, calibration, cost, and adversarial resistance.
- **Mapper**: Runs the test mapper against 20 recent merged PR diffs and reports scope reduction metrics.

Results are saved to `eval/results/`.

## Configuration

All settings are in `config.yaml`. Secrets go in `.env`:

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub PAT (read-only, `public_repo` scope) |
| `LLM_PROVIDER` | `groq`, `openai`, or `anthropic` |
| `LLM_API_KEY` | API key for your chosen provider |
| `LLM_MODEL` | Model name (e.g., `llama-3.3-70b-versatile` for Groq) |

## Architecture

See [DESIGN.md](DESIGN.md) for:
- Full 5-phase architecture with the prototype scope marked
- Permission model (least-privilege per phase)
- Guardrails: audit logging, kill switch, rate limiting, human escalation
- 12 edge cases with mitigations
- Safety hierarchy

## Tech Stack

- **Python 3.11+**
- **httpx** — lightweight HTTP client (no heavy SDK dependencies)
- **click** — CLI framework
- **LLM**: Model-agnostic (Groq/OpenAI/Anthropic via unified client)
- **No database** — flat JSONL files for prototype simplicity
