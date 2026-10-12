"""
Unit tests for prompt quality gates (model-gated discipline and stop-as-truncated heuristic).
"""

from utils.llm.model_discipline import get_model_discipline
from utils.llm.prompt_assembler import PromptAssembler
from analysis.harness.agent_harness import AgentHarness


def test_model_discipline_gating():
    # Models requiring tool use enforcement
    gpt_disc = get_model_discipline("gpt-4o")
    assert "Mandatory Tool Execution Discipline" in gpt_disc
    assert "Verification & Mathematical Grounding" in gpt_disc

    gemini_disc = get_model_discipline("gemini-2.5-flash")
    assert "Mandatory Tool Execution Discipline" in gemini_disc

    # Unknown or models without quirks
    empty_disc = get_model_discipline("custom-specialized-model")
    assert empty_disc == ""


def test_prompt_assembler_injects_discipline():
    assembler = PromptAssembler()
    t1, t2_plain, t3 = assembler.assemble_stage1_tiers()
    assert "Mandatory Tool Execution Discipline" not in t2_plain

    t1, t2_gpt, t3 = assembler.assemble_stage1_tiers(model_name="gpt-4.5")
    assert "Mandatory Tool Execution Discipline" in t2_gpt
    assert "Verification & Mathematical Grounding" in t2_gpt


def test_stop_as_truncated_heuristic():
    # Natural ending with stop finish_reason -> not truncated
    resp_complete = {"finish_reason": "stop"}
    assert AgentHarness._check_truncation(resp_complete, stop_reason="stop", content="Analysis complete. Concluding WAIT.") is False

    # Abrupt cut mid-sentence with stop finish_reason -> flagged as truncated!
    truncated_text = "I have evaluated the ATR and current market structure. Based on the 4-hour order block, the recommended entry price is"
    assert AgentHarness._check_truncation(resp_complete, stop_reason="stop", content=truncated_text) is True

    # Real length stop_reason -> always truncated
    resp_length = {"finish_reason": "length"}
    assert AgentHarness._check_truncation(resp_length, stop_reason="length") is True
