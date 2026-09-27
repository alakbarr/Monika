# Contributing to Monika

Thank you for your interest in contributing to **Monika**! 

Monika is an open-source, domain-specific **Trading Agent Harness and Multi-Agent Execution Framework for MetaTrader 5 (MT5)**. It bridges macroeconomic intelligence, Smart Money Concepts (SMC), dialectical Bull/Bear adversarial debate, deterministic risk fortresses, and broker execution.

---

## 📌 Development Status & Community Invitation

Monika is in **early-stage research and active development**. It is an exploratory prototype designed to discover how LLM-based reasoning and market microstructure can be safely harnessed without sacrificing deterministic capital protection.

We warmly welcome all forms of contribution:
- **Feedback & Critique:** If you notice flawed assumptions, risk calculation edge cases, or architectural bottlenecks, please let us know!
- **Bug Reports:** Open an issue with reproduction steps and sanitized logs.
- **Feature Proposals & PRs:** From new indicators and broker adapters to test fixtures, documentation improvements, and UI enhancements.
- **Questions & Discussions:** Join our GitHub Discussions to exchange ideas on quantitative finance, multi-agent debate calibration, and prompt caching.

Because Monika interacts with financial execution environments, we place the highest priority on **system stability, code hygiene, deterministic risk constraints, and security**.

---

## Code of Conduct

By participating in this project, you agree to abide by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Please report unacceptable behavior according to the guidelines outlined in that document.

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & `npm` (for the Web Dashboard)
- **PostgreSQL 16+** (required for async advisory locks, event bus, and persistent state)
- **MetaTrader 5** (Desktop Terminal installed on Windows, or accessed via Wine / RPC bridge on Linux)
- **Git**

### 1. Fork and Clone
```bash
git clone https://github.com/alakbarr/Monika.git
cd Monika
```

### 2. Set Up Python Virtual Environment
```bash
# Windows (PowerShell):
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
npm run build
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
- `feat/feature-name` — New features, agent tools, or harness plugins
- `fix/bug-description` — Bug fixes and regression repairs
- `docs/doc-update` — Documentation, PRD, or guide improvements
- `refactor/scope` — Refactoring without behavioral change
- `test/test-scope` — Adding or expanding tests

### Code Formatting and Linting
We use **Ruff** for linting and code formatting:
```bash
# Check code for lint violations
ruff check .

# Automatically apply safe fixes
ruff check --fix .

# Check and apply formatting
ruff format .
```

### Testing Guidelines
All contributions must include automated tests. Regression tests are strictly enforced.

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
> - When adding a new module or plugin, you must add corresponding unit tests in `trading-agent/tests/`.
> - Always test edge cases: empty data feeds, network timeouts, broker disconnects, and volatile market anomalies.

---

## Safety & Financial Invariants

Monika enforces strict safety invariants that cannot be bypassed:

1. **"AI Proposes, Mechanical Fortress Disposes"**: AI agents produce structured proposals; they never directly dispatch orders.
2. **RiskGate is Mandatory**: No trade signal may reach the execution layer without passing through `RiskGate`.
3. **Paper Trading by Default**: `paper_trading.enabled: true` and `dry_run: true` are safe defaults. Live trading requires explicit opt-in and graduation criteria (50+ paper trades @ $\ge 55\%$ win rate).
4. **Emergency Circuit Breaker**: The MQL5 dead-man switch and kill-switch endpoints (`/kill`) must remain functional and responsive at all times.
5. **No Credential Leaks**: Never print, log, or store plain-text API keys, MT5 passwords, or database credentials.

---

## Documentation Synchronization

Monika maintains a detailed codebase index and structure map:
- `PRD.md`: Master Project Requirements Document.
- `INDEX.md`: Line-referenced index of all modules, classes, and functions.
- `STRUCTURE.md`: File hierarchy and directory tree inventory.

If your changes add, rename, or remove files, classes, or public functions:
1. Update `INDEX.md` and `STRUCTURE.md` manually to reflect your changes.
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

Thank you for helping develop and refine Monika!
