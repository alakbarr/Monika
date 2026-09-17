# Contributing to Monika

Thank you for your interest in contributing to **Monika**! Monika is a multi-agent autonomous trading system that bridges macroeconomic intelligence, technical market structure analysis, multi-agent debate, risk management, and MetaTrader 5 execution.

Because Monika interacts with financial markets and execution brokers, we place the highest priority on **system stability, code hygiene, deterministic risk constraints, and security**.

---

## Code of Conduct

By participating in this project, you agree to abide by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Please report unacceptable behavior according to the guidelines outlined in that document.

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** (for the Observability Dashboard UI)
- **PostgreSQL 14+** (required for state persistence and event store)
- **MetaTrader 5** (Terminal installed on Windows or accessed via Wine/EA bridge)
- **Git**

### 1. Fork and Clone
```bash
git clone https://github.com/alakbarr/Monika.git
cd Monika
```

### 2. Set Up Python Virtual Environment
```bash
# Windows:
python -m venv venv
venv\Scripts\activate

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r trading-agent/requirements.txt
```

### 4. Install Dashboard Frontend Dependencies
```bash
cd trading-agent/logging_observability/dashboard/frontend
npm install
cd ../../../..
```

### 5. Configure Local Environment
```bash
cp .env.example .env
```
> [!CAUTION]
> **NEVER commit your `.env` file!** It contains broker credentials, private keys, and API tokens. `.gitignore` is configured to block `.env*` files by default.

---

## Development Standards & Hygiene

### Branch Conventions
Create a descriptive branch for your work:
- `feat/feature-name` — New features or agent capabilities
- `fix/bug-description` — Bug fixes
- `docs/doc-update` — Documentation improvements
- `refactor/scope` — Refactoring without behavioral change
- `test/test-scope` — Adding or improving tests

### Code Formatting and Linting
We use **Ruff** for lightning-fast linting and code formatting:
```bash
# Check code for lint violations
ruff check .

# Automatically apply safe fixes
ruff check --fix .

# Check and apply formatting
ruff format .
```

### Testing Guidelines
All contributions must include comprehensive automated tests. Regression tests are strictly enforced.

**Running the test suite:**
```bash
# Windows (PowerShell):
$env:PYTHONPATH="trading-agent"; python -m pytest trading-agent/tests

# Linux / macOS:
PYTHONPATH=trading-agent pytest trading-agent/tests

# Running a specific test file:
PYTHONPATH=trading-agent pytest trading-agent/tests/risk/test_risk_gate.py -v
```

> [!IMPORTANT]
> - Never disable, weaken, or delete an existing test to make new code pass.
> - When adding a new module, you must add corresponding unit tests in `trading-agent/tests/`.
> - Always test edge cases: empty datafeeds, network timeouts, broker disconnects, and negative account balances.

---

## Safety & Financial Invariants

Monika enforces strict safety invariants that cannot be violated under any circumstances:

1. **RiskGate is Mandatory**: No trade signal may reach the execution layer without passing through `RiskGate` and `EffectGate`.
2. **Paper Trading by Default**: `paper_trading.enabled: true` and `dry_run: true` are safe defaults. New installations must execute a minimum of paper trades before live trading can be unlocked.
3. **Emergency Circuit Breaker**: The dead-man switch and kill-switch endpoints must remain functional and responsive at all times.
4. **No Credential Leaks**: Never print, log, or store plain-text API keys, MT5 passwords, or database credentials.

---

## Documentation Synchronization

Monika maintains a detailed codebase index and structure map:
- `INDEX.md`: Complete index of modules, classes, and functions.
- `STRUKTUR.md`: File hierarchy and architectural map.

If your changes add, rename, or remove files, classes, or public functions:
1. Update `INDEX.md` and `STRUKTUR.md` manually to reflect your changes.
2. Run the Table-of-Contents synchronization script:
   ```bash
   python scripts/update_index_toc.py
   ```

---

## Submitting a Pull Request

1. Push your branch to your fork.
2. Open a Pull Request targeting the `main` branch.
3. Complete all items in the [Pull Request Template](.github/pull_request_template.md).
4. Verify that CI passes all linting, test suites, and frontend build checks.
5. Address any review comments promptly.

Thank you for helping make Monika a safer, more powerful algorithmic trading system!
