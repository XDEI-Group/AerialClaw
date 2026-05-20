# AerialClaw OSS Review Hardening Plan

Goal: make the repository easier to evaluate for ACM Multimedia Open Source Software Track reviewers.

| ID | Issue | Reviewer risk | Fix | Verification | Status |
|---|---|---|---|---|---|
| P0-1 | `pytest -q` fails without `PYTHONPATH=.` | Reviewers may mark tests broken | Add `pyproject.toml` pytest config with `pythonpath=["."]` | `python -m pytest` | DONE |
| P0-2 | README/docs claim missing client paths | Documentation trust loss | Align docs with actual repo; mark device clients as protocol examples/planned unless shipped | grep for stale `clients/` claims | DONE |
| P0-3 | `docs/DEPLOYMENT.md` references missing `scripts/start_gz_sim.sh` | Copy-paste setup failure | Replace with `scripts/start_sim.sh` | grep stale script name | DONE |
| P0-4 | custom `x500_lidar_2d_cam` model path is referenced but not shipped | PX4 setup warning/failure | Make setup script gracefully fall back to PX4 `x500`; document current shipped default | grep + script inspection | DONE |
| P0-5 | No reviewer artifact guide | Reviewers lack quick path | Add `ARTIFACT.md` with 5-minute mock demo, full sim path, expected outputs, limitations | read/review | DONE |
| P0-6 | No lightweight reproducible mock path | Reviewers cannot evaluate quickly | Document `SIM_ADAPTER=mock`; add Dockerfile for mock Web UI/server build | `npm run build`, `python -m pytest`, optionally `docker build` | DONE |
| P1-1 | No CI | Weak maturity signal | Add GitHub Actions: compile, pytest, npm build | inspect workflow | DONE |
| P1-2 | Missing citation/contribution metadata | OSS polish gap | Add `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md` | file presence | DONE |
| P1-3 | Sparse tests | Maturity gap | Add smoke tests for mock adapter/server import where safe | `python -m pytest` | DONE |
| P2-1 | Reviewer re-test after fixes | Need second-pass assessment | Run as reviewer: clone state, install, test, build, grep docs, score | report | DONE |

## Verification log

- `python -m compileall -q .` — PASS
- `python -m pytest` — PASS (`6 passed`)
- `cd ui && npm run build` — PASS
- `cd ui && npm run lint` — PASS with warnings, 0 errors
- stale-doc grep for missing `clients/`, `requirements-edge.txt`, `core.doctor`, `/api/doctor/run`, `scripts/start_gz_sim.sh`, `Multi-platform clients`, `15 React components` — PASS/no matches
- `git ls-files Users/*` — PASS/no tracked absolute-path duplicate files in this working branch
- Docker build — not executed because local Docker daemon is unavailable; root `Dockerfile` and `.dockerignore` are present for reviewer mock-mode builds.

## 90% readiness hardening pass

Additional reviewer-facing gates added after the first OSS hardening pass:

- Added `REVIEWER_CHECKLIST.md` to expose a concise ACM MM OSS evidence checklist.
- Added `scripts/check_artifact.py` and `tests/test_artifact_consistency.py` to prevent stale documentation/path regressions.
- Added `scripts/smoke_mock.sh` as a one-command local reviewer smoke gate.
- Extended CI to run artifact consistency, Python compile, pytest, Web UI lint/build, the one-command smoke gate, and a Docker image build job.
- Declared `requires-python >=3.10` in `pyproject.toml` and made `scripts/smoke_mock.sh` auto-select an available Python 3.10+ interpreter.
- Increased tests from 6 to 10 by adding adapter-manager and artifact-consistency smoke tests.
- Fixed Web UI ESLint 9 config and `MapView.jsx` hook dependencies so `npm run lint` passes with no warnings.

Latest local gate:

```text
bash scripts/smoke_mock.sh
artifact consistency checks passed
10 passed
npm run lint: pass with no warnings/errors
npm run build: pass
mock artifact smoke checks passed
```

Known environment limitation:

- Local Docker Desktop/OrbStack daemons were unavailable on this machine, so `docker build` could not be executed locally. The root `Dockerfile`, `.dockerignore`, and CI Docker build job are present so this will be validated on a normal Docker-enabled runner.
