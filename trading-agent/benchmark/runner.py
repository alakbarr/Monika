import asyncio
import json
import logging
from datetime import datetime, timezone

from typing import cast, Sequence
from sqlalchemy import Table

from database.db import get_session, get_engine
from database.models import Base

from .db_models import BenchmarkRun, BenchmarkResult
from .db_access import BenchmarkToolExecutor, guarded_tool_executor
from .task_specs import TASKS
from .invoker import invoke_text, invoke_json, invoke_agent, invoke_chat, invoke_custom, invoke_system_one
from .pricing import cost_usd
from .judge import judge_output
from .deterministic import score_trade_payload
from .system_one_scorer import score_system_one

logger = logging.getLogger("Benchmark.Runner")

# run_agent()/run_chat_loop() memakai ToolExecutor yang di-patch class-level
# (lihat db_access.guarded_tool_executor) -> WAJIB diserialkan supaya tidak
# race antar model yang jalan paralel.
_AGENT_LOCK = asyncio.Lock()


async def ensure_tables():
    try:
        eng = get_engine()
        async with eng.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=cast(Sequence[Table], [BenchmarkRun.__table__, BenchmarkResult.__table__]), checkfirst=True)
            )
    except Exception as e:
        logger.warning("ensure_tables failed (DB might be offline or unmigrated): %s", e)


def _err_row(run_id, task_id, category, model_name, msg):
    return BenchmarkResult(run_id=run_id, task_id=task_id, category=category, model_name=model_name,
                            provider="?", context_key="?", error=msg)


async def _build_case_once(task_id, symbol, base_settings):
    task = TASKS[task_id]
    per_settings = dict(base_settings)
    if symbol:
        per_settings["_benchmark_symbol"] = symbol
    async with get_session() as session:
        ex = BenchmarkToolExecutor(session, per_settings)
        try:
            case = await task.build_case(session, per_settings, ex)
            return case, per_settings, None
        except RuntimeError as e:
            return None, per_settings, str(e)
        except Exception as e:
            logger.exception(f"[{task_id}] build_case gagal")
            return None, per_settings, f"build_case error: {e}"


async def run_one_model_for_case(run_id, task_id, category, mode, model_name, case, settings,
                                  judge_model, semaphore, judge_models: list[str] | None = None):
    async with semaphore:
        async with get_session() as session:
            role_kwargs = case.role_kwargs
            captured = None
            try:
                try:
                    if mode == "agent":
                        async with _AGENT_LOCK:
                            with guarded_tool_executor() as box:
                                inv = await invoke_agent(model_name, settings, session, case.system_prompt,
                                                          case.user_prompt, case.tools, case.stage_name, **role_kwargs)
                                captured = box.get("result")
                    elif mode == "chat":
                        async with _AGENT_LOCK:
                            with guarded_tool_executor() as box:
                                inv = await invoke_chat(model_name, settings, case.system_prompt, case.history or [],
                                                         case.user_prompt, case.tools, **role_kwargs)
                                captured = box.get("result")
                    elif mode == "json":
                        inv = await invoke_json(model_name, settings, case.system_prompt, case.user_prompt, case.schema, **role_kwargs)
                    elif mode == "text":
                        inv = await invoke_text(model_name, settings, case.system_prompt, case.user_prompt, **role_kwargs)
                    elif mode == "custom":
                        inv = await invoke_custom(model_name, settings, case.custom_fn, *case.custom_args, **role_kwargs)
                    elif mode == "system_one":
                        inv = await invoke_system_one(
                            model_name,
                            settings,
                            state=case.state,
                            questions=case.questions,
                            prompt=case.user_prompt,
                            schema=case.schema,
                            **role_kwargs,
                        )
                    else:
                        row = _err_row(run_id, task_id, category, model_name, f"mode tidak dikenal: {mode}")
                        session.add(row)
                        await session.commit()
                        return row
                except Exception as e:
                    logger.exception(f"[{task_id}] invoke gagal untuk {model_name}")
                    row = _err_row(run_id, task_id, category, model_name, str(e))
                    session.add(row)
                    await session.commit()
                    return row

                if captured:
                    output_for_judge = captured["payload"]
                elif isinstance(inv.raw_output, dict) and "final_text" in inv.raw_output:
                    output_for_judge = inv.raw_output.get("final_text")
                else:
                    output_for_judge = inv.raw_output

                schema_valid = bool(captured) if mode in ("agent", "chat") else bool(inv.raw_output) and inv.error is None

                deterministic = None
                if category == "trade_decision" and captured and captured.get("tool") == "submit_asset_analysis":
                    try:
                        deterministic = await score_trade_payload(session, settings, case.context_key, captured["payload"])
                    except Exception as e:
                        logger.debug(f"deterministic score gagal: {e}")

                judge_scores, judge_overall = ({}, None)
                if mode == "system_one" and inv.error is None and case.expected_answers:
                    # System One deterministic evaluation (Zero LLM judge call)
                    s1_res = score_system_one(
                        output=inv.raw_output if isinstance(inv.raw_output, dict) else {},
                        expected=case.expected_answers,
                        latency_s=inv.latency_s,
                        questions=case.questions,
                        target_latency_ms=case.latency_target_ms,
                    )
                    judge_scores = s1_res
                    judge_overall = s1_res["overall_score"]
                elif inv.error is None and output_for_judge and mode != "system_one":
                    try:
                        active_judges = judge_models or [judge_model]
                        if len(active_judges) > 1:
                            from .judge import judge_output_ensemble
                            judge_scores, judge_overall, _ji, _jo = await judge_output_ensemble(
                                active_judges, settings, category, case.context_summary, output_for_judge)
                        else:
                            judge_scores, judge_overall, _ji, _jo = await judge_output(
                                active_judges[0], settings, category, case.context_summary, output_for_judge)
                    except Exception as e:
                        logger.warning(f"judge gagal untuk {task_id}/{model_name}: {e}")

                det_pass = deterministic["pass_rate"] if deterministic else (judge_scores.get("accuracy_score", 0.0) / 10.0 if mode == "system_one" and judge_scores else None)
                overall = None
                if mode == "system_one" and judge_overall is not None:
                    overall = judge_overall
                elif judge_overall is not None and det_pass is not None:
                    overall = 0.6 * judge_overall + 0.4 * (det_pass * 10)
                elif judge_overall is not None:
                    overall = judge_overall
                elif det_pass is not None:
                    overall = det_pass * 10

                try:
                    cost = cost_usd(
                        model_name,
                        inv.input_tokens or 0,
                        inv.output_tokens or 0,
                        cached_tokens=getattr(inv, "cached_tokens", 0) or 0,
                    )
                except Exception as e:
                    logger.warning(f"Cost calculation failed for {model_name}: {e}")
                    cost = 0.0

                row = BenchmarkResult(
                    run_id=run_id, task_id=task_id, category=category, model_name=model_name,
                    provider=inv.provider, context_key=case.context_key,
                    input_tokens=inv.input_tokens or 0, output_tokens=inv.output_tokens or 0,
                    cost_usd=round(cost, 6),
                    latency_s=round(inv.latency_s, 2), schema_valid=schema_valid,
                    deterministic_score=det_pass, judge_scores_json=json.dumps(judge_scores),
                    judge_overall=judge_overall, overall_score=overall,
                    raw_output=json.dumps(output_for_judge, default=str)[:8000] if output_for_judge else None,
                    error=inv.error,
                )
                session.add(row)
                await session.commit()
                logger.info(f"[{task_id}] {model_name}: cost=${cost:.5f} tok={inv.input_tokens}/{inv.output_tokens} "
                            f"score={overall} err={inv.error}")
                return row
            except Exception as e:
                logger.exception(f"[{task_id}] unhandled error in benchmark post-processing for {model_name}")
                row = _err_row(run_id, task_id, category, model_name, str(e)[:200])
                try:
                    session.add(row)
                    await session.commit()
                except Exception:
                    pass
                return row


async def run_benchmark(task_ids: list[str], model_names: list[str], symbols: list[str] | None,
                         judge_model: str, reference_model: str, concurrency: int = 4,
                         judge_models: list[str] | None = None,
                         use_fixtures: bool = False) -> int:
    from config.settings import load_all_config
    base_settings = load_all_config()
    base_settings["_benchmark_reference_model"] = reference_model
    base_settings["_use_fixtures"] = use_fixtures or base_settings.get("benchmark", {}).get("use_fixtures", False)
    await ensure_tables()
    semaphore = asyncio.Semaphore(concurrency)

    async with get_session() as session:
        run = BenchmarkRun(judge_model=(", ".join(judge_models) if judge_models else judge_model),
                           reference_model=reference_model,
                           tasks_json=json.dumps(task_ids), models_json=json.dumps(model_names))
        session.add(run)
        await session.commit()
        run_id = run.id

    syms = symbols or [None]
    jobs = []
    for task_id in task_ids:
        task = TASKS[task_id]
        for symbol in syms:
            case, per_settings, build_err = await _build_case_once(task_id, symbol, base_settings)
            if build_err:
                logger.warning(f"[{task_id}/{symbol}] dilewati: {build_err}")
                async with get_session() as session:
                    session.add(_err_row(run_id, task_id, task.category, "ALL", build_err))
                    await session.commit()
                continue
            for model_name in model_names:
                jobs.append(run_one_model_for_case(run_id, task_id, task.category, task.mode,
                                                    model_name, case, per_settings, judge_model, semaphore,
                                                    judge_models=judge_models))
    results = await asyncio.gather(*jobs, return_exceptions=True)
    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"Benchmark job {idx} raised uncaught exception: {res}")

    async with get_session() as session:
        run = await session.get(BenchmarkRun, run_id)
        import utils.clock as clock
        if run is not None:
            run.finished_at = clock.now()
            await session.commit()
    return run_id

