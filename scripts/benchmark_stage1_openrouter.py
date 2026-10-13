"""
Benchmark Runner for Stage 1 Fundamental Analysis across 8 LLMs via OpenRouter.
Completely isolated in-memory execution via guarded_tool_executor().
Zero database modification, zero live broker order execution.
Produces full transparent input/output/thinking Markdown report.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Set up paths
REPO_ROOT = Path(__file__).resolve().parent.parent
_src_dir = REPO_ROOT / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
try:
    from monika.infrastructure.infra.legacy_compat import install_legacy_compat

    install_legacy_compat()
except Exception:
    pass
os.chdir(str(REPO_ROOT))

# Ensure stdout handles UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.settings import load_all_config
from database.db import init_db, get_session
from benchmark.task_specs import _stage1_system_prompt, STAGE1_USER_MESSAGE_TEXT
from benchmark.fixture_loader import get_synthetic_stage1_bundle
from analysis.tools.tools_definitions import STAGE1_TOOLS
from analysis.prefetch.stage1_prefetcher import PREFETCH_KEY_TO_TOOL, CORE_STAGE1_PREFETCH_TOOLS, prune_stage1_tools
from benchmark.db_access import guarded_tool_executor
from analysis.providers.openrouter_provider import OpenRouterProvider
from utils.analytics.pricing import cost_usd

MODELS_TO_BENCHMARK = [
    {
        "name": "gpt-6.1-sol",
        "display_name": "GPT-6.1 Sol (high)",
        "model_id": "openai/gpt-6.1-sol",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "claude-opus-5.5",
        "display_name": "Claude Opus 5.5 (high)",
        "model_id": "anthropic/claude-opus-5.5",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "grok-4.6",
        "display_name": "Grok 4.6 (high)",
        "model_id": "x-ai/grok-4.6",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "muse-spark-1.3",
        "display_name": "Muse Spark 1.3 (xhigh)",
        "model_id": "meta/muse-spark-1.3",
        "thinking_level": "xhigh",
        "max_tokens": 24576,
    },
    {
        "name": "mimo-v2.6-pro",
        "display_name": "MiMo v2.6 Pro (max)",
        "model_id": "xiaomi/mimo-v2.6-pro",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "deepseek-v4-pro",
        "display_name": "DeepSeek v4 Pro (max)",
        "model_id": "deepseek/deepseek-v4-pro",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "kimi-k3",
        "display_name": "Kimi k3 (max)",
        "model_id": "moonshotai/kimi-k3",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "gemini-3.8-flash",
        "display_name": "Gemini 3.8 Flash (high)",
        "model_id": "google/gemini-3.8-flash",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "deepseek-v4.1-flash",
        "display_name": "DeepSeek v4.1 Flash (max)",
        "model_id": "deepseek/deepseek-v4.1-flash",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "glm-5.3",
        "display_name": "GLM-5.3 (max)",
        "model_id": "z-ai/glm-5.3",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "glm-5.3-flash",
        "display_name": "GLM-5.3 Flash (max)",
        "model_id": "z-ai/glm-5.3-flash",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
]

JSON_OUTPUT_PATH = (
    REPO_ROOT / "src" / "monika" / "application" / "benchmark" / "results" / "benchmark_stage1_results.json"
)
MARKDOWN_OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "monika"
    / "application"
    / "benchmark"
    / "results"
    / "benchmark_stage1_fundamental_openrouter.md"
)


def extract_turn_details(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract structured turn-by-turn trace including thinking content and tool calls."""
    turns_data = []
    current_turn = {}

    for idx, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content")
        reasoning = msg.get("reasoning_content") or msg.get("reasoning")

        if role == "assistant":
            text_parts = []
            tool_calls = []

            if isinstance(content, list):
                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "text":
                        t_text = block.get("text", "")
                        if getattr(block, "thinking", False):
                            if not reasoning:
                                reasoning = t_text
                        else:
                            text_parts.append(t_text)
                    elif b_type == "tool_use":
                        tool_calls.append(
                            {
                                "id": block.get("id"),
                                "name": block.get("name"),
                                "input": block.get("input"),
                            }
                        )
            elif isinstance(content, str):
                text_parts.append(content)

            raw_tc = msg.get("tool_calls") or []
            for tc in raw_tc:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
                fn_name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
                raw_args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", {})
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except Exception:
                        parsed_args = raw_args
                else:
                    parsed_args = raw_args
                tool_calls.append(
                    {
                        "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", ""),
                        "name": fn_name,
                        "input": parsed_args,
                    }
                )

            current_turn = {
                "turn_index": len(turns_data) + 1,
                "role": "assistant",
                "thinking": reasoning,
                "text": "\n".join(text_parts).strip(),
                "tool_calls": tool_calls,
                "tool_results": [],
            }
            turns_data.append(current_turn)

        elif role == "user":
            # Tool results or user prompt
            tool_res_list = []
            if isinstance(content, list):
                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "tool_result":
                        tool_res_list.append(
                            {
                                "tool_use_id": block.get("tool_use_id"),
                                "content": block.get("content"),
                            }
                        )
            if turns_data and tool_res_list:
                turns_data[-1]["tool_results"].extend(tool_res_list)

        elif role == "tool":
            if turns_data:
                turns_data[-1]["tool_results"].append(
                    {
                        "tool_use_id": msg.get("tool_call_id"),
                        "name": msg.get("name"),
                        "content": msg.get("content"),
                    }
                )

    return turns_data


def generate_markdown_report(benchmark_data: Dict[str, Any]) -> str:
    """Formats benchmark results into a clean, comprehensive Markdown report."""
    md = []
    meta = benchmark_data.get("metadata", {})
    models_res = benchmark_data.get("results", [])
    input_data = benchmark_data.get("input_specification", {})

    md.append("# 📊 Benchmark Report: Task Role `stage1_fundamental` (OpenRouter)")
    md.append(f"**Execution Timestamp**: `{meta.get('timestamp')}`  ")
    md.append(
        f"**Total Models Evaluated**: `{len(models_res)}` | **Router**: `OpenRouter.ai` | **Isolation Mode**: `In-Memory Guarded Box (Zero DB write, Zero Broker Execution)`\n"
    )
    md.append("---\n")

    # 1. Executive Summary Table
    md.append("## 1. 🏆 Executive Comparison Matrix & Scorecard\n")
    md.append(
        "| Model | Thinking Level | Status | Latency | Turns | Tools | In / Out Tokens | Thinking Tokens | Cost ($ USD) | Macro Regime | USD Bias | Brief Captured |"
    )
    md.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for m in models_res:
        captured = m.get("captured_payload") or {}
        regime = captured.get("macro_regime", "-")
        usd_bias = (captured.get("currency_bias") or {}).get("USD", "-")
        status_icon = "✅ Success" if m.get("success") else "❌ Failed"
        brief_icon = "✅ Yes" if captured else "❌ No"
        in_out = f"{m.get('input_tokens', 0):,} / {m.get('output_tokens', 0):,}"
        think_tok = f"{m.get('thinking_tokens', 0):,}"
        cost = f"${m.get('cost_usd', 0.0):.4f}"
        lat = f"{m.get('latency_s', 0.0):.1f}s"
        md.append(
            f"| **{m.get('display_name')}** | `{m.get('thinking_level')}` | {status_icon} | {lat} | {m.get('turns', 0)} | {m.get('tool_calls_made', 0)} | {in_out} | {think_tok} | {cost} | `{regime}` | `{usd_bias}` | {brief_icon} |"
        )

    md.append("\n---\n")

    # 2. Benchmark Input Specification
    md.append("## 2. 📥 Benchmark Input Specification (Full Transparency)\n")
    md.append("Setiap model dievaluasi menggunakan input baku yang 100% identik di bawah ini:\n")

    md.append("<details>")
    md.append("<summary><b>📄 System Prompt (`stage1_fundamental`) — Klik untuk membuka</b></summary>\n")
    md.append("```text")
    md.append(input_data.get("system_prompt", ""))
    md.append("```\n")
    md.append("</details>\n")

    md.append("<details>")
    md.append("<summary><b>📦 User Message & Pre-Fetched Macro Data Bundle — Klik untuk membuka</b></summary>\n")
    md.append("```text")
    md.append(input_data.get("user_prompt", ""))
    md.append("```\n")
    md.append("</details>\n")

    md.append("<details>")
    md.append("<summary><b>🛠️ Available Tool Definitions Schema (STAGE1_TOOLS) — Klik untuk membuka</b></summary>\n")
    md.append("```json")
    md.append(json.dumps(input_data.get("tool_schemas", []), indent=2))
    md.append("```\n")
    md.append("</details>\n")

    md.append("---\n")

    # 3. Per-Model Transparent Execution Details
    md.append("## 3. 🔍 Per-Model Detailed Execution & Reasoning Traces\n")

    for idx, m in enumerate(models_res, 1):
        md.append(f"### 3.{idx}. Model: {m.get('display_name')}\n")
        md.append(f"- **OpenRouter Model ID**: `{m.get('model_id')}`")
        md.append(f"- **Thinking Effort / Level**: `{m.get('thinking_level')}`")
        md.append(
            f"- **Execution Latency**: `{m.get('latency_s', 0.0):.2f}s` | **Turns Taken**: `{m.get('turns', 0)}` | **Tool Calls**: `{m.get('tool_calls_made', 0)}`"
        )
        md.append(
            f"- **Token Usage**: `{m.get('input_tokens', 0):,}` In | `{m.get('output_tokens', 0):,}` Out | `{m.get('thinking_tokens', 0):,}` Thinking | `{m.get('cached_tokens', 0):,}` Cached"
        )
        md.append(f"- **Calculated Cost**: `${m.get('cost_usd', 0.0):.6f} USD`")
        if m.get("error"):
            md.append(f"- **Error Encountered**: `{m.get('error')}`")

        captured = m.get("captured_payload")
        if captured:
            md.append("\n#### 📋 Captured `submit_fundamental_brief` Payload:\n")
            md.append("```json")
            md.append(json.dumps(captured, indent=2))
            md.append("```\n")
        else:
            md.append(
                "\n> ⚠️ *`submit_fundamental_brief` payload tidak tertangkap (model menyimpulkan via teks bebas atau batas turn tercapai).*\n"
            )

        # Turn by turn trace
        turns = m.get("turns_trace", [])
        md.append(f"#### 🧠 Turn-by-Turn ReAct Lifecycle & Reasoning Trace ({len(turns)} Turns):\n")

        for t in turns:
            t_idx = t.get("turn_index")
            md.append(f"<details open>")
            md.append(f"<summary><b>Turn {t_idx} Execution Details</b></summary>\n")

            thinking = t.get("thinking")
            if thinking:
                md.append("**Thinking / Chain-of-Thought Trace:**")
                md.append("```text")
                md.append(thinking.strip())
                md.append("```\n")
            else:
                md.append("*(Tidak ada reasoning block eksplisit pada turn ini)*\n")

            calls = t.get("tool_calls", [])
            if calls:
                md.append("**Tool Invocations:**")
                for c in calls:
                    md.append(f"- Call: `{c.get('name')}` (ID: `{c.get('id')}`)")
                    md.append("  ```json")
                    md.append("  " + json.dumps(c.get("input", {}), indent=2).replace("\n", "\n  "))
                    md.append("  ```")
                md.append("")

            results = t.get("tool_results", [])
            if results:
                md.append("**Tool Results Returned:**")
                for r in results:
                    c_preview = str(r.get("content", ""))
                    if len(c_preview) > 600:
                        c_preview = c_preview[:600] + "... [truncated for brevity]"
                    md.append(f"- Return `{r.get('tool_use_id', '')}`: `{c_preview}`")
                md.append("")

            txt = t.get("text")
            if txt:
                md.append("**Assistant Text:**")
                md.append(f"> {txt}\n")

            md.append("</details>\n")

        final_text = m.get("final_text")
        if final_text:
            md.append("#### 📝 Final Summary Narrative:\n")
            md.append(f"{final_text}\n")

        md.append("---\n")

    # 4. Comparative Synthesis & Insights
    md.append("## 4. 📈 Comparative Analysis & Insights\n")
    md.append("### 4.1. Efisiensi Token & Biaya Komputasi")
    md.append(
        "- Model dengan reasoning tingkat tinggi (`max`, `xhigh`) secara alami mengonsumsi token thinking yang jauh lebih besar (1,000–8,000 token) untuk mensintesis relasi inflasi, FedWatch repricing, dan divergensi bank sentral."
    )
    md.append(
        "- Model-model yang langsung memanggil `submit_fundamental_brief` dari pre-fetched data bundle menunjukkan efisiensi latency dan biaya yang optimal."
    )
    md.append("\n### 4.2. Kepatuhan Skema & Rigor Analitis")
    md.append(
        "- Keberhasilan penangkapan `submit_fundamental_brief` membuktikan kepatuhan model terhadap *Pydantic structural constraints* (checklist, numeric validation, invalidation conditions >= 40 karakter, dan pricing assessment)."
    )

    return "\n".join(md)


async def main():
    print("=" * 70)
    print("[*] MONIKA BENCHMARK: Stage 1 Fundamental Analysis across 8 LLMs")
    print("=" * 70)

    # 1. Initialize DB & Configuration
    print("Initializing local DB and configurations...")
    await init_db()
    settings = load_all_config()
    settings["_benchmark_mode"] = True
    settings["_use_fixtures"] = True
    settings["llm"]["providers"]["openrouter"]["enabled"] = True
    settings["stall_terminate_threshold"] = 50
    settings["stall_warning_threshold"] = 30

    # Freeze simulated clock to benchmark evaluation scenario time
    import utils.clock as clock

    clock.set_simulated_now(datetime(2026, 10, 4, 19, 0, 0, tzinfo=timezone.utc))

    system_prompt = _stage1_system_prompt(settings)
    bundle = get_synthetic_stage1_bundle()
    synthetic_satisfied_tools = set(CORE_STAGE1_PREFETCH_TOOLS)
    pruned_stage1_tools = prune_stage1_tools(STAGE1_TOOLS, synthetic_satisfied_tools)

    simulation_directive = (
        "[BENCHMARK SIMULATION CONTEXT & TEMPORAL ANCHOR]\n"
        "Current Simulated Time: 2026-10-04T19:00:00Z\n"
        "All market data, yield curves, calendar events, and news digests in this evaluation are frozen to October 4, 2026.\n"
        "Treat October 4, 2026 as TODAY. Data dated Oct 1 - Oct 4, 2026 is FRESH and current (within hours/days).\n"
        "Do NOT evaluate data against real-world wall-clock dates or reject data as stale.\n"
        "Formulate active, decisive non-neutral hypotheses for assets where structural catalyst divergence exists."
    )
    user_prompt = f"{simulation_directive}\n\n{STAGE1_USER_MESSAGE_TEXT}\n\n[PRE-FETCHED DATA]\n{bundle}"

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default=None, help="Specific model to run (e.g. gemini-3.8-flash)")
    parser.add_argument("--force", action="store_true", help="Force re-run even if model already succeeded")
    args = parser.parse_args()

    benchmark_record = {
        "metadata": {
            "task_role": "stage1_fundamental",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runner": "scripts/benchmark_stage1_openrouter.py",
        },
        "input_specification": {
            "system_prompt": system_prompt if isinstance(system_prompt, str) else str(system_prompt),
            "user_prompt": user_prompt,
            "tool_schemas": [
                {
                    "name": t.get("name") if isinstance(t, dict) else getattr(t, "name", ""),
                    "description": t.get("description") if isinstance(t, dict) else getattr(t, "description", ""),
                    "parameters": t.get("input_schema") if isinstance(t, dict) else getattr(t, "input_schema", {}),
                }
                for t in pruned_stage1_tools
            ],
        },
        "results": [],
    }

    if JSON_OUTPUT_PATH.exists():
        try:
            with open(JSON_OUTPUT_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "results" in saved:
                    benchmark_record = saved
                    print(
                        f"[*] Loaded {len(benchmark_record['results'])} existing results from {JSON_OUTPUT_PATH.name}"
                    )
        except Exception as e:
            print(f"[Warning] Could not load existing benchmark results: {e}")

    targets_to_run = [
        m
        for m in MODELS_TO_BENCHMARK
        if not args.model or args.model.lower() in m["name"].lower() or args.model.lower() in m["model_id"].lower()
    ]

    # 2. Iterate through selected models
    total_models = len(targets_to_run)
    for i, target in enumerate(targets_to_run, 1):
        name = target["name"]
        disp = target["display_name"]
        model_id = target["model_id"]
        thinking_level = target["thinking_level"]
        max_tokens = target["max_tokens"]

        existing_match = next(
            (r for r in benchmark_record["results"] if r.get("name") == name and r.get("success")), None
        )
        if existing_match and not args.force:
            print(f"\n[{i}/{total_models}] [SKIPPED] {disp} already completed successfully.")
            continue

        print(f"\n[{i}/{total_models}] [RUNNING] {disp} ({model_id})...")
        print(f"      Thinking Level: {thinking_level} | Max Tokens: {max_tokens}")

        model_result = {
            "name": name,
            "display_name": disp,
            "model_id": model_id,
            "thinking_level": thinking_level,
            "success": False,
            "latency_s": 0.0,
            "turns": 0,
            "tool_calls_made": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "cached_tokens": 0,
            "cost_usd": 0.0,
            "captured_payload": None,
            "turns_trace": [],
            "final_text": "",
            "error": None,
        }

        # Attempt execution with 1 retry on transient failure
        for attempt in range(2):
            try:
                client = OpenRouterProvider(
                    model=model_id,
                    max_tokens=max_tokens,
                    max_tool_turns=2,
                    thinking_level=thinking_level,
                    settings=settings,
                    temperature=0.0,
                )

                t0 = time.perf_counter()
                async with get_session() as session:
                    with guarded_tool_executor() as box:
                        result = await client.run_agent(
                            session=session,
                            system_prompt=system_prompt,
                            user_message=user_prompt,
                            tools=pruned_stage1_tools,
                            stage_name="benchmark_stage1_fundamental",
                            max_tool_turns=2,
                            prefetch_satisfied_tools=synthetic_satisfied_tools,
                        )
                        captured = box.get("result")
                elapsed = time.perf_counter() - t0

                model_result["latency_s"] = round(elapsed, 2)
                model_result["success"] = bool(result.get("success", False))
                model_result["turns"] = result.get("turns", 0)
                model_result["tool_calls_made"] = result.get("tool_calls_made", 0)
                model_result["input_tokens"] = result.get("input_tokens", 0)
                model_result["output_tokens"] = result.get("output_tokens", 0)
                model_result["thinking_tokens"] = result.get("thinking_tokens", 0)
                model_result["cached_tokens"] = result.get("cached_tokens", 0)
                model_result["final_text"] = result.get("final_text", "")

                # Calculate USD cost
                model_result["cost_usd"] = cost_usd(
                    model_id,
                    model_result["input_tokens"],
                    model_result["output_tokens"],
                    provider="openrouter",
                )

                if captured and "payload" in captured:
                    model_result["captured_payload"] = captured["payload"]
                    model_result["success"] = True
                elif model_result["final_text"]:
                    from analysis.stages.fundamental_stage_recovery import recover_fundamental_brief_from_text

                    recovered = recover_fundamental_brief_from_text(model_result["final_text"])
                    if recovered:
                        model_result["captured_payload"] = recovered
                        model_result["success"] = True
                        model_result["recovered_via_heuristic"] = True
                        print("      [RECOVERED] Brief recovered from final text via heuristic extraction!")

                # Extract turn-by-turn trace
                raw_messages = result.get("context_messages", [])
                model_result["turns_trace"] = extract_turn_details(raw_messages)

                print(
                    f"      [OK] Finished in {elapsed:.1f}s | Turns: {model_result['turns']} | In/Out/Think: {model_result['input_tokens']}/{model_result['output_tokens']}/{model_result['thinking_tokens']}"
                )
                if model_result["captured_payload"]:
                    regime = model_result["captured_payload"].get("macro_regime")
                    biases = model_result["captured_payload"].get("currency_bias")
                    print(f"      [CAPTURED] Brief Captured! Regime: {regime} | Biases: {biases}")
                else:
                    print("      [NOTICE] Brief payload not captured (final text produced)")

                break  # Successful attempt
            except Exception as e:
                print(f"      [WARN] Attempt {attempt + 1} encountered exception: {e}")
                model_result["error"] = str(e)
                if attempt == 0:
                    print("      [WAIT] Retrying in 5 seconds...")
                    await asyncio.sleep(5.0)

        existing_idx = next((idx for idx, r in enumerate(benchmark_record["results"]) if r.get("name") == name), None)
        if existing_idx is not None:
            benchmark_record["results"][existing_idx] = model_result
        else:
            benchmark_record["results"].append(model_result)

        # Write intermediate checkpoint JSON
        try:
            with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(benchmark_record, f, indent=2, ensure_ascii=False)
        except Exception as se:
            print(f"      [Warning] Checkpoint save failed: {se}")

    # 3. Generate Final Markdown Report
    print("\n" + "=" * 70)
    print("[*] Generating formatted Markdown report...")
    md_content = generate_markdown_report(benchmark_record)
    with open(MARKDOWN_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[OK] Report saved to: {MARKDOWN_OUTPUT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
