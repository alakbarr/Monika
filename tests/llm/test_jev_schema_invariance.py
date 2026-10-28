import json
from monika.core.primitives.jev_primitives import (
    jev_questions_to_schema,
    build_position_guardian_questions,
    build_trade_risk_questions,
    build_conservative_risk_questions,
    build_aggressive_risk_questions,
    build_confluence_gate_questions,
    build_session_timing_questions,
    build_exit_prescreen_questions,
    build_trigger_validator_questions,
    build_news_realtime_questions,
)


def test_position_guardian_schema_invariance():
    """Verify build_position_guardian_questions produces identical schema across symbols and directions."""
    q_eur = build_position_guardian_questions("EURUSD", "buy")
    q_xau = build_position_guardian_questions("XAUUSD", "sell")

    schema_eur = jev_questions_to_schema(q_eur)
    schema_xau = jev_questions_to_schema(q_xau)

    assert schema_eur == schema_xau
    # Check that descriptions contain no asset-specific names
    for prop in schema_eur["properties"].values():
        desc = prop.get("description", "")
        assert "EURUSD" not in desc
        assert "XAUUSD" not in desc
        assert "buy" not in desc.lower() or "buyer" in desc.lower()


def test_all_builders_schema_invariance():
    """Verify all question builders produce identical schemas regardless of arguments."""
    pairs = [
        (
            build_trade_risk_questions("EURUSD", "buy"),
            build_trade_risk_questions("XAUUSD", "sell"),
        ),
        (
            build_conservative_risk_questions("EURUSD", "buy"),
            build_conservative_risk_questions("XAUUSD", "sell"),
        ),
        (
            build_aggressive_risk_questions("EURUSD", "buy"),
            build_aggressive_risk_questions("XAUUSD", "sell"),
        ),
        (
            build_confluence_gate_questions("EURUSD", "trend"),
            build_confluence_gate_questions("XAUUSD", "breakout"),
        ),
        (
            build_session_timing_questions("LONDON", 45),
            build_session_timing_questions("NEW_YORK", 10),
        ),
        (
            build_exit_prescreen_questions("EURUSD", "buy"),
            build_exit_prescreen_questions("XAUUSD", "sell"),
        ),
        (
            build_news_realtime_questions(["EURUSD", "USDJPY"]),
            build_news_realtime_questions(["XAUUSD"]),
        ),
        (
            build_trigger_validator_questions("EURUSD", "breakout_buy"),
            build_trigger_validator_questions("XAUUSD", "retest_sell"),
        ),
    ]

    for q1, q2 in pairs:
        s1 = jev_questions_to_schema(q1)
        s2 = jev_questions_to_schema(q2)
        assert s1 == s2, f"Schema mismatch between {q1} and {q2}"


def test_no_dynamic_interpolations_in_instructions():
    """Verify instructions in builders do not contain dynamic symbol, direction, session or dates."""
    builders = [
        build_position_guardian_questions("EURUSD", "buy"),
        build_trade_risk_questions("EURUSD", "buy"),
        build_conservative_risk_questions("EURUSD", "buy"),
        build_aggressive_risk_questions("EURUSD", "buy"),
        build_confluence_gate_questions("EURUSD", "trend"),
        build_session_timing_questions("LONDON", 45),
        build_exit_prescreen_questions("EURUSD", "buy"),
        build_news_realtime_questions(["EURUSD"]),
        build_trigger_validator_questions("EURUSD", "breakout"),
    ]

    forbidden_tokens = ["EURUSD", "buy", "LONDON", "45m", "trend"]
    for q_dict in builders:
        for q_name, q_obj in q_dict.items():
            instructions = getattr(q_obj, "instructions", "")
            for token in forbidden_tokens:
                assert token not in instructions, f"Found '{token}' in {q_name} instructions: {instructions}"


def test_llm_factory_list_jev_questions_to_schema():
    """Verify that a list of jev_questions is converted to a valid schema."""
    from monika.core.primitives.jev_primitives import list_to_jev_questions

    q_list = [
        {"name": "is_valid", "type": "Noul", "description": "Is setup valid?"},
        {"name": "score", "type": "Score", "range": [1, 4], "description": "Confidence score"},
    ]
    q_dict = list_to_jev_questions(q_list)
    schema = jev_questions_to_schema(q_dict)

    assert schema["type"] == "object"
    assert "is_valid" in schema["properties"]
    assert schema["properties"]["is_valid"]["type"] == "boolean"
    assert "score" in schema["properties"]
    assert schema["properties"]["score"]["type"] == "integer"
    assert schema["properties"]["score"]["minimum"] == 1
    assert schema["properties"]["score"]["maximum"] == 4


def test_deterministic_state_sorting():
    """Verify that json.dumps with sort_keys=True formats state keys deterministically."""
    state1 = {"zeta": 1, "alpha": 2, "gamma": 3}
    state2 = {"alpha": 2, "gamma": 3, "zeta": 1}

    dump1 = json.dumps(state1, indent=2, sort_keys=True)
    dump2 = json.dumps(state2, indent=2, sort_keys=True)

    assert dump1 == dump2
    # Verify alpha comes before zeta in output
    alpha_pos = dump1.find('"alpha"')
    zeta_pos = dump1.find('"zeta"')
    assert alpha_pos != -1 and zeta_pos != -1
    assert alpha_pos < zeta_pos
