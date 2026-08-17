# LiveOps Community Intelligence

**A game version community insight & operations retrospective system** — a fixed, reproducible, auditable pipeline for analyzing Bilibili community comments, plus an operations workbench.

> Scope: every conclusion describes **the sampled Bilibili discussion** only — not all players.

## What it is

```
public data (restricted sampling / file import) → Canonical Schema normalization → relevance filter
  → topic / stance / emotion / irony / request annotation (LLM structured + strong-model seed + human review, two gold tiers)
  → Python quantitative aggregation (LLM never touches numbers) → original-text evidence traceback → version retrospective report (conclusion verification gate)
```

**Not** a generic sentiment tool, not an LLM "summarize all comments" wrapper, not real-time public-opinion monitoring.

## Quick start

### Public demo mode (no key, read-only, see it immediately)

```bash
bash scripts/start-demo.sh          # one command: build static site + local server + open browser
# or choose a port: bash scripts/start-demo.sh 8080
```

First run builds automatically (~1-2 min), then it starts instantly. Demo data is precomputed JSON (`demo/public-data/`, anonymized + leak-scanned) with a game switcher (Genshin 6.8 / Wuthering Waves 3.5) in the top-left. This is the recommended way to view the full sample with zero configuration.

### Local full mode (when you want real LLM annotation)

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
# or Git Bash / WSL
bash scripts/start-local.sh
```

Open http://localhost:3000 (FastAPI backend on :8000, Next.js frontend on :3000).

- First time: `cd backend && uv sync --extra dev --extra embed`; `cd frontend && pnpm install`
- Real LLM annotation: copy `.env.example` to `.env` and fill `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL` (OpenAI-compatible; Ollama adapter reserved). Without a key the system runs on seed-replay/demo data.
- Two real case runs are built in: `runs/seed-genshin-6.8` and `runs/seed-wuthering-3.5` (select one on the "Data & Runs" page).

## Reproduce the main results

```bash
cd backend
uv run python -m pytest tests/ -q            # 208+ tests
uv run python tools/collect_bilibili.py --study genshin68   # restricted public sampling (resumable)
uv run python tools/freeze_study.py --study genshin-6.8     # quota validation + freeze
uv run python tools/run_seed_analysis.py    # dual-game full analysis + evaluation
uv run python tools/export_demo.py          # demo export (with leak-scan assertion)
```

## Repository layout

| Directory | Purpose |
|---|---|
| `backend/liveops` | Schema / importers / collector / normalization / embeddings & clustering / LLM client (injection defense) / LangGraph harness / metrics / evaluation / FastAPI |
| `backend/tests` | Pytest: import/Schema/dedup/window/metric formulas/abnormal model output/checkpoint recovery/injection/corrupted files/empty data/overlong text/rate-limit/missing key |
| `backend/tools` | collect / freeze / sampling / seed merge / full analysis / demo export |
| `frontend/src` | 9-page operations workbench (Next.js + Tailwind + shadcn-style + ECharts) |
| `data/raw` | raw collection (gitignored, contains non-anonymized) → `frozen/` frozen samples |
| `data/gold` | 800 seed gold labels (400×2) |
| `runs/<run_id>` | per-run artifacts: manifest (models/prompt versions/code SHA/dataset hash/cost/duration) + stage checkpoints + metrics + report |
| `demo/public-data` | anonymized demo data (leak-scan enforced) |
| `docs` | PRD / sampling protocol / compliance / labeling guide / evaluation report / two case retrospectives / architecture |

## Docs index

- [PRD](docs/prd.md) · [Sampling protocol & version locking](docs/sampling-protocol.md) · [Data compliance](docs/compliance.md) (Chinese)
- [Labeling guide v1.0](docs/labeling-guide.md) · [Architecture](docs/architecture.md)
- [Evaluation report (real numbers)](docs/evaluation-report.md)
- [Genshin 6.8 retrospective](docs/case-genshin-6.8.md) · [Wuthering Waves 3.5 retrospective](docs/case-wuthering-3.5.md)
- [Stage review reports](docs/stage-reviews.md)

## Core design constraints

1. **LLM never computes metrics**: 9 metrics (topic share / net support rate / controversy / trend / engagement / persistence / UGC spread / issue priority / opportunity) are all exact Python implementations, asserted to decimal places by hand-built fixtures.
2. **Untrusted data boundary**: community text is wrapped in `<untrusted_community_text>` + injection-defense declaration + strict JSON Schema + one repair retry + abstain path; injection-corpus tests guarantee the output stays a valid label.
3. **Every conclusion is traceable**: dual metric_id + evidence_id citations; a verification node rejects overgeneralization ("all players"), causal wording, and small-sample conclusions without a marker.
4. **Honest reporting**: quota gaps from restricted sampling, the ~34% abstain rate, weak vector-baseline numbers, and "LLM tier not measured" are all shown as-is; composite scores are declared as configurable ranking rules with ±10% weight sensitivity.
5. **Single-machine serial + stage checkpoints**: a file lock enforces one task at a time; a killed run resumes per-stage by artifact hash (covered by tests).

## Testing & QA

- Backend: `uv run python -m pytest tests/ -q` (208+ cases)
- Frontend: `pnpm exec playwright test` (demo site, 9 pages × desktop/mobile: render / non-empty charts / no horizontal overflow / evidence links / read-only checks)
- Collector guardrail tests: hard-stop on risk codes (no retry), token-bucket intervals, journal resume, quota rules.

## Compliance bottom line (summary)

Public content only, no login / no bypassing risk control (hard-stop on 412/-352), raw UID never persisted (HMAC irreversible anonymization), public exports enforce leak-scanning, synthetic data explicitly flagged. See [docs/compliance.md](docs/compliance.md) (Chinese).

## Known limitations (stated honestly)

1. Restricted public sampling does not reach the 4,000-5,000 comments/game quota (logged-out sessions only expose first-page comments + sub-replies); the completion path is: export comments yourself → file import (a first-class feature).
2. The human gold tier awaits user review (workbench is ready); two-annotator Kappa is not yet computed.
3. LLM annotation quality is not yet measured (key pending); current numbers are pipeline verification and the vector baseline.
