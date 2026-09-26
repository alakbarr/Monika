# ==============================================================================
# File: tests/skills/test_phase8_skills_and_continuous_learning.py
# ==============================================================================

import os
import shutil
import tempfile
import pytest

from skills.skills_guard import SkillsGuard
from skills.skills_hub import SkillsHub
from skills.continuous_learning import ContinuousLearner, handle_learn_skill, LearnSkillInput
from analysis.tools.domain.todo_tool import handle_manage_todo, TodoActionInput, TodoTracker
from analysis.tools.domain.cron_tool import handle_manage_cron, CronActionInput, CronRegistry


def test_skills_guard_ast_audit():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Safe skill
        safe_dir = os.path.join(tmpdir, "safe_skill")
        os.makedirs(safe_dir)
        with open(os.path.join(safe_dir, "script.py"), "w", encoding="utf-8") as f:
            f.write("def calculate_rsi(data):\n    return sum(data) / len(data)\n")

        safe_report = SkillsGuard.audit_skill_directory(safe_dir, "safe_skill")
        assert safe_report.is_safe is True
        assert safe_report.score == 100
        assert len(safe_report.findings) == 0

        # 2. Malicious skill with eval & os.system
        bad_dir = os.path.join(tmpdir, "bad_skill")
        os.makedirs(bad_dir)
        with open(os.path.join(bad_dir, "exploit.py"), "w", encoding="utf-8") as f:
            f.write("import os\neval('__import__(\"os\").system(\"whoami\")')\nos.system('dir')\n")

        bad_report = SkillsGuard.audit_skill_directory(bad_dir, "bad_skill")
        assert bad_report.is_safe is False
        assert bad_report.score < 50
        rules = [f.rule for f in bad_report.findings]
        assert "FORBIDDEN_BUILTIN" in rules
        assert "UNRESTRICTED_OS_EXEC" in rules


def test_skills_hub_install_with_security_gate():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub = SkillsHub(search_directories=[tmpdir])

        # Attempt to install unsafe skill
        bad_skill_src = os.path.join(tmpdir, "unsafe_src")
        os.makedirs(bad_skill_src)
        with open(os.path.join(bad_skill_src, "run.py"), "w", encoding="utf-8") as f:
            f.write("eval('bad_code')\n")

        ok, msg, report = hub.install_skill(bad_skill_src, category="general", enforce_security=True)
        assert ok is False
        assert "Security Gate Rejected" in msg


@pytest.mark.asyncio
async def test_todo_tool_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        todo_file = os.path.join(tmpdir, "test_todos.json")
        tracker = TodoTracker(file_path=todo_file)

        # 1. Add
        item = tracker.add("Refactor risk position sizer", priority="high")
        assert item.id == 1
        assert item.status == "pending"

        # 2. List
        listed = tracker.list_items()
        assert len(listed) == 1
        assert listed[0].title == "Refactor risk position sizer"

        # 3. Update
        updated = tracker.update(1, "completed")
        assert updated is not None
        assert updated.status == "completed"

        # 4. Clear completed
        cleared = tracker.clear_completed()
        assert cleared == 1
        assert len(tracker.list_items()) == 0


@pytest.mark.asyncio
async def test_cron_tool_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = os.path.join(tmpdir, "test_cron.json")
        reg = CronRegistry(file_path=cron_file)

        # 1. Add
        job = reg.add_job(
            name="daily_cot_sync",
            cron_expr="0 9 * * 1-5",
            instruction="Fetch CFTC COT report and update database",
            description="Daily morning COT synchronization",
        )
        assert job.name == "daily_cot_sync"

        # 2. List
        jobs = reg.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].cron_expression == "0 9 * * 1-5"

        # 3. Remove
        removed = reg.remove_job("daily_cot_sync")
        assert removed is True
        assert len(reg.list_jobs()) == 0


@pytest.mark.asyncio
async def test_continuous_learner():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Temporarily redirect crystallized dir for isolated test
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            ok, msg, path = ContinuousLearner.distill_and_crystallize(
                skill_name="mt5_slippage_defense",
                description="Handling broker requotes during high NFP volatility",
                problem="Broker returns 10004 REQUOTE error on market order during news spike.",
                solution="Switch to IOC (Immediate or Cancel) with 5 pips deviation tolerance or place pending stop order.",
                category="crystallized",
            )
            assert ok is True
            assert os.path.exists(path)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "mt5_slippage_defense" in content
            assert "Broker returns 10004 REQUOTE" in content
            assert "deviation tolerance" in content
        finally:
            os.chdir(orig_cwd)
