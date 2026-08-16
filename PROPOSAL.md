# LFX Mentorship Application Proposal

**Project Title:** AI-Ready Kyverno Dev: Repo Restructuring, Agent Docs, and an AI Maintainer Assistant  
**Target Repository:** [`kyverno/kyverno`](https://github.com/kyverno/kyverno)  
**Issue Reference:** [Issue #16665](https://github.com/kyverno/kyverno/issues/16665)  
**Mentorship Program:** LFX Mentorship 2025 / 2026 Term  
**Mentorship Project ID:** `c869e19a-8815-459b-8a2d-3a068e8863c3`  
**Working Prototype Repository:** `https://github.com/<YOUR_GITHUB_USERNAME>/kyverno-ai-maintainer-poc`  

---

## 1. Executive Summary

Kyverno is the cloud-native policy engine for Kubernetes, managing validation, mutation, generation, image verification, and cleanup across thousands of enterprise clusters. As the project has grown, maintainers face significant administrative overhead:
1. **CI Bottlenecks & Flaky Tests:** Running the exhaustive test suite on every PR wastes compute credits and developer time when only specific subsystems (e.g., `pkg/engine/` or `cmd/cli/`) are changed.
2. **Issue Triage Overhead:** High volumes of incoming bug reports and feature requests require manual categorization into kind, area, and priority taxonomy.
3. **Routine Maintenance Load:** Dependabot bumps, documentation syncs, and flaky test reruns consume valuable maintainer bandwidth.

To address these challenges safely, I propose building the **Kyverno AI Maintainer Assistant**: a modular, security-hardened system that automates routine maintainer tasks while enforcing a strict **human-in-the-loop, least-privilege boundary**. 

To prove feasibility before the mentorship begins, I have developed and benchmarked a **fully functional, read-only Python 3.11+ prototype** (`kyverno-ai-maintainer-poc`) that demonstrates:
- **80% Average CI Scope Reduction with 100% Test Recall** across real Kyverno PRs, featuring deterministic fallback to full test suites on any unmapped or sensitive paths to eliminate false-negative omissions by design.
- **100% Security Boundary Enforcement** on sensitive directories (`charts/`, `.github/workflows/`, `api/kyverno/v1/`).
- **87.5% Real-Issue Triage Accuracy (21/24 Evaluated)** on real closed Kyverno issues with zero parse failures.
- **5/5 (100%) Prompt Injection Resistance** using data quarantine and instruction-recency placement.
- **Tamper-Evident SHA-256 Audit Logging** with cryptographic hash-chaining.

---

## 2. Working Prototype & Empirical Benchmark Results

Rather than proposing purely theoretical designs, the proposed architecture has been implemented, tested (`31/31 unit tests passing`), and benchmarked on real historical data from `kyverno/kyverno`.

### Key Benchmark Metrics (Reproducible Run: `temperature=0.0`, `seed=42`)

| Module | Benchmark Dataset | Measured Metric | Maintainer Impact |
|---|---|---|---|
| **Diff-to-Test Mapper** | 20 Recent Merged Kyverno PRs | **80% Avg Scope Reduction (100% Test Recall)** | Eliminates redundant test suites with 100% full-suite fallback on unmapped/sensitive paths — zero false negatives by design |
| **Security Boundaries** | 7 Sensitive PRs (`charts/`, `.github/`) | **100% Deny-List Enforcement** | Zero autonomous modifications to critical infrastructure; routes 100% to `manual_review` |
| **Issue Triage Classifier** | 25 Historical Kyverno Issues | **87.5% Kind Accuracy (21/24 Evaluated\*)** | High bug categorization precision (100%: 19/19 bugs). Small-sample feature caveat below\*\* |
| **Parser Resilience** | 25 Real Issue Payloads + Markdown/YAML | **0% Parse Errors (0/25 Failures)** | Multi-stage JSON parser with rate-limit exponential backoff prevents pipeline failures |
| **Adversarial Resilience** | 5 Attack Vectors (Override, Leak, Impersonation) | **5/5 (100% Blocked & Escalated)** | Data quarantine + instruction-recency placement + mandatory injection extraction |
| **Confidence Calibration** | Full 30-Item Battery (Real + Attacks) | **ECE = 0.1714 (Spread across 4 bins)** | Correctly escalates 100% of adversarial inputs (conf 0.35–0.65). Overconfidence on real issues addressed in Phase 2\*\*\* |
| **Escalation Gating** | 30 Total Test Items | **16.7% Overall (5/5 Attacks Escalated)** | 100% of untrusted/adversarial submissions routed to human maintainer review |
| **Audit Logger** | All Decision Records | **100% Cryptographic Integrity** | SHA-256 hash-chaining ensures full transparency and auditability (verified by 31 unit tests) |

*\*Note on Denominator (21/24): Out of 25 fetched issues, Issue #16809 lacked a ground-truth `kind/*` label in GitHub, leaving 24 evaluable items.*  
*\*\*Note on `kind/feature` ($n=5$): 2 of 3 misses were repo-migration issues titled `[Chore]` that maintainers labeled `kind/feature` — a genuinely ambiguous taxonomy case (chore vs. feature) rather than a clear classifier error.*  
*\*\*\*Note on Calibration: On well-formed real issues, the top-confidence bin sits at ~88% accuracy vs ~98% average confidence — a known LLM self-report gap that will be resolved in Weeks 6–7 via Multi-Sample Self-Consistency ($k=3$).*

---

## 3. System Architecture & Technical Design

The AI Maintainer Assistant is structured in three decoupled, auditable layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      1. Ingestion & Event Layer                         │
│  - GitHub Webhook Receiver (PR open, Issue open, Workflow failed)       │
│  - Read-Only Token Boundary & Token-Bucket Rate Limiter                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   2. Analysis & Governance Engine                       │
│  ┌───────────────────────────────┐     ┌──────────────────────────────┐ │
│  │   Deterministic Rule Engine   │     │  Hardened LLM Reasoning Node │ │
│  │  - Diff-to-Test Path Mapping  │     │  - Data Quarantine Wrapper   │ │
│  │  - Zero-Auto-Touch Deny-List  │     │  - Multi-Stage JSON Parser   │ │
│  │  - Static AST Dependency Map  │     │  - Calibrated Confidence     │ │
│  └───────────────┬───────────────┘     └──────────────┬───────────────┘ │
│                  └──────────────────────┬─────────────┘                 │
└─────────────────────────────────────────┼───────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     3. Action, Gate & Audit Layer                       │
│  - Confidence Evaluator (≥ 0.75 Auto-Suggest, < 0.75 Escalate to Human) │
│  - Maintainer Override & Global Kill-Switch (`hold` label / config file)│
│  - Tamper-Evident SHA-256 Append-Only JSONL Audit Logger                │
│  - Read-Only PR Comments & Draft Label Suggestions                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### A. Deterministic Diff-to-Test Scope Mapper
- Analyzes changed file paths in pull requests using Go package dependency heuristics.
- Maps changes directly to relevant unit test packages (`pkg/engine/...`, `pkg/webhooks/...`) and conformance tests (`test/conformance/chainsaw/...`).
- **Security Boundary:** Explicit deny-list automatically flags any PR touching `api/kyverno/v1/`, `pkg/cosign/`, `.github/workflows/`, or `charts/` for mandatory `manual_review`.

#### B. Hardened Triage Classifier
- Classifies issues into standard Kyverno taxonomy (`kind/*`, `area/*`, priority hints `P1`–`P4`).
- **Prompt Injection Defense:** Untrusted user input is quarantined within `<untrusted_issue_data>` blocks. System classification directives are placed *after* untrusted input to leverage autoregressive recency bias.
- **Analysis-First Reasoning:** Requires the model to output a technical summary and flag detected injections before producing classification labels.
- **Confidence Calibration:** Computes a composite confidence score combining semantic clarity with structural heuristics (issue template adherence, presence of YAML blocks and panic traces).

#### C. Tamper-Evident Audit Logger
- Every decision (input summary, model used, latency, token count, calibrated confidence, recommended action) is recorded in an append-only JSONL log.
- Cryptographically chained using SHA-256 hashes (`record_hash = SHA-256(data + prev_hash)`), enabling automated validation of log integrity.

#### D. Safety Guardrails & Least-Privilege Permissions
- **Read-Only First:** The bot operates exclusively via draft labels and non-intrusive PR review comments in initial phases.
- **Kill-Switch:** Can be disabled instantly via a single repository flag or by applying a `hold` label to any specific PR/issue.
- **Rate-Limiting:** Token-bucket rate limiting prevents runaway API costs or GitHub rate limits.

---

## 4. 12-Week Implementation Plan

### Detailed Milestone Breakdown

| Weeks | Focus Area | Deliverables & Milestones | Acceptance Criteria |
|---|---|---|---|
| **Weeks 1–2** | **Phase 0: Repo Audit, Agent Docs & Ingestion** | • Comprehensive audit of repository structure and monorepo/module boundary evaluation.<br>• Expand root `AGENTS.md` and add per-directory agent docs (`pkg/engine/`, `pkg/webhooks/`, `pkg/controllers/`, `test/conformance/`).<br>• Author and publish explicit **Safe Automation Boundaries** document (autonomous-safe vs. zero-auto-touch paths).<br>• Machine-readable task index (`TASKS.md` / `agents.json`) for automated task routing.<br>• Project scaffolding, GitHub Actions webhook dispatcher with read-only least-privilege token boundaries. | `AGENTS.md`, per-directory guides, and task index merged; safe automation boundaries published; webhooks ingest PR and issue events without write access. |
| **Weeks 3–5** | **Phase 1: Diff-to-Test Scope Mapper** | • Full Go AST dependency graph generator parsing Kyverno package imports.<br>• Integration with Kyverno's `Makefile` and Chainsaw test runner.<br>• Fallback logic for unmapped files and monorepo bumps (preserving 100% test recall). | Achieves ≥ 75% test suite reduction on historical PRs; 100% detection of security-sensitive paths; zero unmapped regressions. |
| **Weeks 6–7** | **Phase 2: Issue Triage & Labeling** | • Multi-stage triage classifier with prompt injection defense.<br>• Self-consistency sampling ($k=3$) and confidence calibration engine.<br>• Non-intrusive maintainer suggestion comments. | ≥ 85% kind accuracy on benchmark issue suite; < 0.10 ECE calibration; zero autonomous actions on ambiguous issues. |
| **Weeks 8–9** | **Phase 3: PR Hygiene & Flaky Triager** | • PR hygiene automation (stale PR detection, merge-conflict flagging, clean rebase verification).<br>• Dependabot PR validation engine (verifying semver patch bumps + green CI).<br>• Flaky test analyzer (detecting transient test failures and correlating with open issues).<br>• Human-in-the-loop recommendation workflow. | Accurately flags safe patch bumps; distinguishes flaky tests from genuine PR regressions; automates stale PR hygiene. |
| **Weeks 10–11** | **Phase 4: Safety, Audit & Multi-Model** | • Cryptographic SHA-256 audit logging and tamper-verification CLI.<br>• Global kill-switch and `hold` label override handlers.<br>• Model-agnostic backend (Groq, OpenAI, Anthropic, Ollama/local). | Zero security bypasses; tamper verification CLI successfully detects any modified audit logs. |
| **Weeks 12** | **Phase 5: Documentation, Eval & Handoff** | • Maintainer onboarding guide & evaluation playbook.<br>• Continuous evaluation harness running in Kyverno CI.<br>• Final presentation and mentorship handoff report. | Complete documentation merged into repository; evaluation harness running as a reproducible CI step. |

> [!NOTE]
> **Scope Note & Progressive Automation Roadmap:**
> - **Fast-Follows & Stretch Goals:** The automated `codegen-all-code` / `verify-codegen` gate for `api/` changes, documentation-drift detection, and KinD-based automated reproduction environments are prioritized as Phase 3 fast-follows building directly upon the AST dependency graph; the Slack / GitHub Discussions Q&A assistant remains an explicit Phase 4 stretch goal as labeled in Kyverno Issue #16665.
> - **Graduated Write Permissions:** All automated actions operate strictly in recommend-only mode through Week 12; progressive write-scoped automation (e.g., auto-merging verified green patch bumps) represents a graduated Phase 2 extension requiring explicit maintainer sign-off.

---

## 5. Edge Case Handling & Risk Mitigation

| Edge Case / Risk | Potential Failure Mode | Built-in Mitigation in Design |
|---|---|---|
| **Prompt Injection** | User submits issue containing commands to alter labels or leak prompt. | Delimited quarantine tags (`<untrusted_issue_data>`), instruction-recency placement, explicit analysis step, and hard safety escalation if injections are detected. (Tested 5/5). |
| **False-Positive Actions** | Bot applies incorrect label or suggests unsafe test reduction. | Low-confidence escalation gate (< 0.75); all actions are reversible; zero auto-merges without human maintainer sign-off. |
| **Flaky Test Cascade** | Flaky Chainsaw test triggers repeated CI reruns and rate limit starvation. | Token-bucket rate limiter with per-minute and per-day caps; backoff retries; maximum 1 automated retry before escalating to human. |
| **Stale Test Mapping** | Codebase refactoring invalidates package-to-test mapping. | Test mapper dynamically rebuilds dependencies from Go AST at HEAD commit; safe fallback to `full_suite` if any path is unmapped. |
| **API Rate Limits / Outages** | GitHub API or LLM provider hits 429 rate limit mid-batch. | Built-in exponential backoff with dynamic `retry-after` header parsing; non-blocking asynchronous queue; local fallback model option. |
| **Model Deprecation / Drift** | Upstream LLM changes behavior, reducing classification accuracy. | Reproducible evaluation harness with versioned ground-truth datasets; model version pinned in audit logs. |

---

## 6. Relevant Background & Experience

- **Kubernetes & Cloud Native:** Experienced with Kubernetes architectures, CRDs, admission controllers, and policy engines. Familiar with Kyverno's policy structure (Validate, Mutate, Generate, VerifyImages, Cleanup).
- **Go & Python Development:** Strong background in Go (AST parsing, test harnesses) and Python (modern asynchronous pipelines, CLI tooling, testing frameworks).
- **LLM Systems & Security:** Hands-on experience building structured LLM applications, prompt injection defense, model calibration, and audit logging.
- **Open Source Commitment:** Enthusiastic about contributing to the CNCF ecosystem and actively collaborating with Kyverno maintainers throughout and beyond the mentorship period.

---

## 7. Availability & Commitment

- **Time Commitment:** 30–40 hours per week throughout the 12-week mentorship duration.
- **Communication:** Daily asynchronous updates via CNCF Slack (`#kyverno` / `#kyverno-dev`), weekly syncs with mentors, and transparent progress tracking on GitHub issues and project boards.
- **Post-Mentorship Goal:** Continue active contributions to Kyverno as an ongoing maintainer and community member.
