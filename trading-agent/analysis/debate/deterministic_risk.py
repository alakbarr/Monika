"""
Deterministic (non-LLM) risk personas.

Persona conservative/aggressive/neutral sebelumnya dihasilkan lewat LLM call terpisah,
padahal system prompt-nya SUDAH mendiktekan rumus persis (mis. "veto_trade=true ONLY if
R:R < 1.5"). `debate_node._apply_deterministic_risk_clamp` sudah menimpa ulang hasil akhir
secara deterministik apapun output LLM-nya — membuktikan lapisan LLM di sini dekoratif.
Fungsi-fungsi berikut mereplikasi rumus PERSIS yang sebelumnya ada di prompt masing-masing
persona, menghasilkan schema output yang sama (drop-in replacement).
"""
from typing import Optional


def analyze_risk_conservative(ctx: dict) -> dict:
    state = ctx.get('actual_risk_state') or {}
    daily_pnl_pct = state.get('daily_pnl_pct', 0.0)
    open_positions = state.get('open_positions', 0)
    heat_pct = state.get('portfolio_heat_pct', 0.0)
    confluence = ctx.get('confluence_score') or 0

    veto = False
    reasons = []
    if daily_pnl_pct <= -2.5:
        veto = True
        reasons.append(f'Rule1: daily_pnl_pct={daily_pnl_pct:.2f}% <= -2.5%')
    if open_positions >= 4:
        veto = True
        reasons.append(f'Rule2: open_positions={open_positions} >= 4')
    if heat_pct > 3.0:
        multiplier = 0.6
        reasons.append(f'Rule3: portfolio_heat_pct={heat_pct:.2f}% > 3.0% -> cap 0.6')
    else:
        multiplier = 0.90 if confluence >= 8 else 0.80
        reasons.append(f'Rule4: confluence={confluence} -> base_multiplier={multiplier}')
    if veto:
        multiplier = 0.0
    return {
        'risk_profile_assessment': 'CONSERVATIVE (deterministic): ' + '; '.join(reasons),
        'recommended_multiplier': round(multiplier, 3),
        'veto_trade': veto,
    }


def analyze_risk_aggressive(ctx: dict, min_rr_ratio: float = 1.0) -> dict:
    rr_ratio = ctx.get('rr_ratio')
    sl_beyond_structure = ctx.get('sl_beyond_structure', True)
    confluence = ctx.get('confluence_score') or 0

    veto = False
    reasons = []
    if rr_ratio is not None and rr_ratio < min_rr_ratio:
        veto = True
        reasons.append(f'Rule1: R:R={rr_ratio:.2f} < {min_rr_ratio}')
    if not sl_beyond_structure:
        veto = True
        reasons.append('Rule1: SL not beyond structural level')
    if confluence < 5:
        veto = True
        reasons.append(f'Rule1: confluence_score={confluence} < 5')
    if veto:
        multiplier = 0.0
    else:
        multiplier = 1.6 if confluence >= 9 else 1.0
        reasons.append(f'Rule2: confluence={confluence} -> multiplier={multiplier}')
    return {
        'risk_profile_assessment': 'AGGRESSIVE (deterministic): ' + ('; '.join(reasons) if reasons else 'no rule triggered'),
        'recommended_multiplier': round(multiplier, 3),
        'veto_trade': veto,
    }


def analyze_risk_neutral(ctx: dict, min_rr_ratio: float = 1.3) -> dict:
    state = ctx.get('actual_risk_state') or {}
    daily_pnl_pct = state.get('daily_pnl_pct', 0.0)
    heat_pct = state.get('portfolio_heat_pct', 0.0)
    open_positions = state.get('open_positions', 0)
    confluence = ctx.get('confluence_score') or 0
    rr_ratio = ctx.get('rr_ratio')

    veto = False
    reasons = []
    if heat_pct > 4.0 and confluence < 9:
        veto = True
        reasons.append(f'Rule1a: heat_pct={heat_pct:.2f}% > 4.0% AND confluence={confluence} < 9')
    if daily_pnl_pct <= -2.0:
        veto = True
        reasons.append(f'Rule1b: daily_pnl_pct={daily_pnl_pct:.2f}% <= -2.0%')
    if rr_ratio is not None and rr_ratio < min_rr_ratio:
        veto = True
        reasons.append(f'Rule1c: R:R={rr_ratio:.2f} < min_rr_ratio={min_rr_ratio}')

    penalty_pos = 0.15 * max(0, open_positions - 1)
    penalty_pnl = 0.2 if daily_pnl_pct < -1.0 else 0.0
    multiplier = max(0.4, min(1.5, 1.0 - penalty_pos - penalty_pnl))
    reasons.append(f'Rule2: 1.0 - {penalty_pos:.2f} - {penalty_pnl:.2f} = {multiplier:.3f}')
    if veto:
        multiplier = 0.0
    return {
        'risk_profile_assessment': 'NEUTRAL (deterministic): ' + '; '.join(reasons),
        'recommended_multiplier': round(multiplier, 3),
        'veto_trade': veto,
    }


def make_portfolio_decision_deterministic(risk_debate_states: dict) -> dict:
    cons = risk_debate_states.get('conservative', {})
    agg = risk_debate_states.get('aggressive', {})
    neu = risk_debate_states.get('neutral', {})
    multipliers = [
        cons.get('recommended_multiplier', 1.0),
        agg.get('recommended_multiplier', 1.0),
        neu.get('recommended_multiplier', 1.0),
    ]
    veto_count = sum(1 for d in (cons, agg, neu) if d.get('veto_trade'))
    avg_multiplier = sum(multipliers) / len(multipliers)
    approval = veto_count < 3
    reason = (
        f'Deterministic PM: avg_multiplier={avg_multiplier:.3f} '
        f'(C={multipliers[0]:.2f}, A={multipliers[1]:.2f}, N={multipliers[2]:.2f}), '
        f'veto_count={veto_count}/3'
    )
    return {'approval': approval, 'recommended_risk_multiplier': round(avg_multiplier, 3), 'reason': reason}
