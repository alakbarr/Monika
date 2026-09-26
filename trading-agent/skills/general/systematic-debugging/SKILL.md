---
name: systematic-debugging
description: Scientific root-cause analysis, reproduction, and defect verification.
category: GENERAL
version: 1.0.0
platforms:
  - windows
  - linux
  - macos
---

# Systematic Debugging Skill

Structured methodology for isolating and resolving software defects without regression.

## 4-Step Scientific Debugging Method

1. **Observe & Reproduce**:
   - Collect exact error traces, exit codes, and environmental preconditions.
   - Construct minimal reproducible test case before modifying production code.

2. **Formulate Falsifiable Hypotheses**:
   - Rank potential failure causes based on concrete evidence, not intuition.
   - Test each hypothesis sequentially by inspecting logs, runtime state, or targeted asserts.

3. **Apply Minimal Corrective Patch**:
   - Address the root vulnerability directly at the responsible subsystem layer.
   - Do not mask underlying errors with blanket `try...except Exception: pass` suppressions.

4. **Verify & Prove Resolution**:
   - Execute the reproduction script to confirm failure is resolved.
   - Execute the full test suite to guarantee zero regression on adjacent functionality.
