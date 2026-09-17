## 📌 Description of Changes
Please include a summary of the change, motivation, context, and any dependencies required.

Fixes # (issue)

## 🏷️ Type of Change
- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] ✨ New feature (non-breaking change adding functionality)
- [ ] ⚡ Performance improvement / Token optimization
- [ ] ♻️ Code refactoring
- [ ] 📝 Documentation update
- [ ] 🚨 Breaking change (fix or feature causing existing functionality to change)

---

## 🛡️ Financial & System Safety Checklist
- [ ] **RiskGate Uncompromised**: Changes do NOT bypass `RiskGate`, `EffectGate`, or drawdown circuit breakers.
- [ ] **Paper Mode Preserved**: Default safe configuration (`dry_run: true`, `paper_trading.enabled: true`) remains untouched.
- [ ] **No Secrets Exposed**: Verified that no API keys, MT5 account passwords, or private URLs are present in code or commit history.
- [ ] **Subprocess Safety**: Any programmatic execution is properly sanitized of environment credentials.

---

## ✅ Quality Assurance Checklist
- [ ] My code follows the code style and conventions of this project.
- [ ] I have run `ruff check .` and resolved all linter warnings.
- [ ] I have run `ruff format .` to format the code.
- [ ] I have added automated unit tests covering the changes.
- [ ] All existing and new tests pass locally (`pytest trading-agent/tests`).
- [ ] I have manually updated `INDEX.md` and `STRUKTUR.md` if any files, classes, or public functions were modified/added.
- [ ] I have run `python scripts/update_index_toc.py` to synchronize Table of Contents line numbers.
