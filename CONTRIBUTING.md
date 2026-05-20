# Contributing to AerialClaw

Contributions are welcome through issues and pull requests.

## Development setup

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pytest
python -m pytest

cd ui
npm install
npm run build
```

## Before opening a pull request

Please run:

```bash
python -m compileall -q .
python -m pytest
cd ui && npm install && npm run build
```

## Scope

Good first contributions include:

- adapter fixes
- mock mode examples
- documentation improvements
- tests for skills, safety, memory, and planner fallback logic
- simulator setup fixes

Real-drone control changes should include clear safety notes and should not bypass the safety envelope.
