---
name: research-analysis
description: "Multi-source empirical investigation, fact triangulation, and structured synthesis reports."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [research, analysis, investigation, synthesis, evidence, anti_slop]
---

# Empirical Research & Technical Analysis Playbook

## 1. Tool-Chained Investigation SOP
- **Codebase & Architecture**: Execute `read_file` or `codebase-inspection` tools first to verify ground truth in code. Never assume module structure from memory.
- **Macro & Market Intelligence**: Chain `get_fundamental_brief` $\rightarrow$ `get_economic_calendar` $\rightarrow$ `web_search` with strict boolean operators.
- **Fact Triangulation**: A technical claim requires at least TWO independent verifiable sources (e.g. source code implementation + official SDK documentation or database telemetry).

## 2. Anti-Slop Quality Gate (Mandatory)
Every research deliverable MUST pass these 4 criteria:
1. **Concrete Numeric Grounding**: Never use vague qualifiers (*"significant increase"*, *"relatively high"*). Use exact values (*"spread widened by 35 points"*, *"win rate dropped from 62% to 48%"*).
2. **Code / File Citations**: Every architectural assertion must cite exact file paths and line numbers (e.g. `[risk/risk_gate.py:575]`).
3. **Zero AI Fluff Phrases**: Reject generic conversational intros (*"Let's dive in"*, *"It is important to remember"*).
4. **Falsifiable Hypotheses**: State the exact condition that would prove the research conclusion wrong.

## 3. Mandatory Structured Output Format
```markdown
# Research Brief: [Subject / Topic]

## 1. Executive Summary
- [1-2 dense paragraphs detailing core finding and strategic takeaway]

## 2. Verified Empirical Facts
- **Fact 1**: [Description with file/source citation `path/to/file.py:L123`]
- **Fact 2**: [Concrete metric / data table]

## 3. Assumptions vs Open Risks
- **Working Assumption**: [Clear declaration of unverified premise]
- **Key Risk**: [Scenario under which assumption fails]

## 4. Actionable Next Steps
1. [Deterministic step 1 with target file/component]
2. [Deterministic step 2 with test verification command]
```
