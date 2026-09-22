# ==============================================================================
# File: skills/loader.py
# ==============================================================================
"""
Skills Loader: Sistem manajemen prompt modular.

Fungsi:
- Memisahkan logic Python dari instruksi prompt statis (playbook, SOP).
- Mendukung Prompt Caching dengan penggabungan file `.md`.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("TradingAgent.SkillLoader")

# Resolve skills base directory relative to this file
_SKILLS_DIR = Path(__file__).parent / "trading"


def _sanitize_skill_name(name: str) -> str:
    """Sanitize skill name to prevent directory traversal outside skills folder."""
    if not name or not isinstance(name, str):
        raise ValueError(f"Invalid skill name: '{name}'")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Path traversal detected in skill name: '{name}'")
    clean = os.path.basename(name).strip()
    if not clean or clean.startswith("."):
        raise ValueError(f"Invalid skill name: '{name}'")
    return clean


import yaml


def parse_skill_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter delimited by --- if present (Phase 4.5)."""
    if not content or not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) >= 3:
        raw_yaml = parts[1]
        body = parts[2].lstrip("\r\n")
        try:
            meta = yaml.safe_load(raw_yaml) or {}
            if isinstance(meta, dict):
                return meta, body
        except Exception as e:
            logger.debug(f"Failed to parse skill YAML frontmatter: {e}")
            return {}, content
    return {}, content


def _read_skill_raw(name: str) -> str:
    """Read raw file content without frontmatter processing."""
    clean_name = _sanitize_skill_name(name)
    skill_path = _SKILLS_DIR / f"{clean_name}.md"
    if not skill_path.exists():
        playbook_path = _SKILLS_DIR / "playbooks" / f"{clean_name}.md"
        crystallized_path = _SKILLS_DIR.parent / "crystallized" / f"{clean_name}.md"
        alt_cryst = _SKILLS_DIR.parent / "crystallized" / f"{clean_name.removeprefix('crystallized_')}.md"
        if playbook_path.exists():
            skill_path = playbook_path
        elif crystallized_path.exists():
            skill_path = crystallized_path
        elif alt_cryst.exists():
            skill_path = alt_cryst
        else:
            raise FileNotFoundError(
                f"Skill '{name}' not found at {skill_path}, {playbook_path}, or {crystallized_path}. "
                f"Available skills: {list_skills()}"
            )

    base_root = _SKILLS_DIR.parent.resolve()
    resolved = skill_path.resolve()
    if not resolved.is_relative_to(base_root):
        raise ValueError(f"Directory traversal detected outside skills folder: '{name}'")

    return skill_path.read_text(encoding="utf-8")


@lru_cache(maxsize=64)
def get_skill_metadata(name: str) -> dict:
    """Retrieve frontmatter metadata dictionary for a skill (Phase 4.5)."""
    try:
        raw = _read_skill_raw(name)
        meta, _ = parse_skill_frontmatter(raw)
        return meta
    except Exception:
        return {}


def is_skill_active(skill_name: str, context: Optional[dict] = None) -> bool:
    """Check whether a skill should be activated given runtime context (Phase 4.5).
    Evaluates:
      - requires_tools: all required tools must be present in context['tools']
      - fallback_for_tools: skill only activates if NONE of these tools are present
      - markets: active market category or symbol must match
    """
    if not context:
        return True

    meta = get_skill_metadata(skill_name)
    if not meta:
        return True

    active_tools = set(context.get("tools") or context.get("available_tools") or [])
    active_market = str(context.get("market") or "").lower()
    active_symbol = str(context.get("symbol") or "").upper()

    # 1. requires_tools: all must be available
    req_tools = meta.get("requires_tools")
    if req_tools:
        if isinstance(req_tools, str):
            req_tools = [req_tools]
        if active_tools and not all(t in active_tools for t in req_tools):
            return False

    # 2. fallback_for_tools: if any tool present, skill is skipped
    fallback_tools = meta.get("fallback_for_tools")
    if fallback_tools:
        if isinstance(fallback_tools, str):
            fallback_tools = [fallback_tools]
        if any(t in active_tools for t in fallback_tools):
            return False

    # 3. markets: must match active market or symbol
    markets = meta.get("markets")
    if markets:
        if isinstance(markets, str):
            markets = [markets]
        markets_lower = [m.lower() for m in markets]
        matched = False
        if active_market and active_market in markets_lower:
            matched = True
        if active_symbol and any(m.upper() in active_symbol for m in markets):
            matched = True
        if not matched and (active_market or active_symbol):
            return False

    return True


@lru_cache(maxsize=64)
def load_skill(name: str, strip_frontmatter: bool = True) -> str:
    """Muat isi skill markdown berdasarkan nama (tanpa .md), mencari di trading/, trading/playbooks/, dan crystallized/."""
    content = _read_skill_raw(name)
    if strip_frontmatter:
        _, content = parse_skill_frontmatter(content)
    logger.debug(f"Loaded skill '{name}' ({len(content)} chars)")
    return content


def list_skills() -> list[str]:
    """List semua file skill yang terdeteksi di direktori trading/, trading/playbooks/, dan crystallized/."""
    if not _SKILLS_DIR.exists():
        return []
    skills = [p.stem for p in _SKILLS_DIR.glob("*.md") if p.is_file()]
    playbooks_dir = _SKILLS_DIR / "playbooks"
    if playbooks_dir.exists():
        skills.extend([p.stem for p in playbooks_dir.glob("*.md") if p.is_file()])
    cryst_dir = _SKILLS_DIR.parent / "crystallized"
    if cryst_dir.exists():
        skills.extend([p.stem for p in cryst_dir.glob("*.md") if p.is_file()])
    return list(dict.fromkeys(skills))


def is_playbook_eligible(skill_name: str, context: Optional[dict] = None) -> bool:
    """Verify if a playbook is currently eligible for production use (not demoted/archived in ledger)."""
    try:
        from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager
        mgr = PlaybookLifecycleManager()
        meta = mgr.get_metadata(skill_name)
        if meta and meta.status in ("archived", "demoted", "stale"):
            logger.info(f"[ProgressiveDisclosure] Skipping ineligible/demoted playbook: {skill_name} (status={meta.status})")
            return False
    except Exception:
        pass
    return True


def get_progressive_playbook_index(symbol: Optional[str] = None) -> str:
    """Level 0: Compact index of available playbooks and setups (< 150 tokens)."""
    try:
        from analysis.memory.progressive_loader import ProgressivePlaybookLoader
        loader = ProgressivePlaybookLoader()
        return loader.get_level0_index()
    except Exception as e:
        logger.debug(f"Progressive playbook loader fallback: {e}")
        return "[AVAILABLE_PLAYBOOKS_INDEX (Level 0)]: SMC/ICT liquidity sweep, order block, and FVG playbooks active."


def compose_system_prompt(*skill_names: str, separator: str = "\n\n---\n\n", max_tokens: Optional[int] = None, progressive: bool = False, **template_vars) -> str:
    """Rangkai beberapa skill menjadi satu system prompt dan isi template variables."""
    # Check if max_tokens or progressive was passed via kwargs or explicitly
    if max_tokens is None and "max_tokens" in template_vars:
        max_tokens = template_vars.pop("max_tokens")
    if not progressive and "progressive" in template_vars:
        progressive = bool(template_vars.pop("progressive"))

    runtime_context = template_vars.pop("context", None) or template_vars.pop("active_context", None) or {}

    parts = []
    included_index = False

    for name in skill_names:
        # Filter with Playbook Ledger FSM
        if not is_playbook_eligible(name, runtime_context):
            continue

        if runtime_context and not is_skill_active(name, runtime_context):
            logger.debug(f"Skill '{name}' skipped by conditional activation (Phase 4.5)")
            continue

        # Progressive Disclosure: list-then-load for bulky playbooks
        is_bulky_playbook = "playbook" in name.lower() or name.startswith("alpha_")
        if progressive and is_bulky_playbook:
            active_setup = str(runtime_context.get("setup") or runtime_context.get("pattern") or runtime_context.get("focus_playbook") or "").lower()
            # If explicit setup matches, load full content (Level 1)
            if active_setup and (active_setup in name.lower() or name.lower() in active_setup):
                try:
                    parts.append(load_skill(name))
                except FileNotFoundError:
                    continue
            else:
                # Include compact index once instead of entire bulky text
                if not included_index:
                    parts.append(get_progressive_playbook_index(symbol=runtime_context.get("symbol")))
                    included_index = True
            continue

        try:
            parts.append(load_skill(name))
        except FileNotFoundError as e:
            logger.warning(f"Skill not found during compose: {e}")
            # Graceful degradation: skip missing skill, don't crash
            continue

    composed = separator.join(parts)

    # Auto-include performance notes if they exist
    # (only for stage 2 compositions that include smc_ict_playbook)
    if "smc_ict_playbook" in skill_names and "performance_notes" not in skill_names:
        try:
            performance_notes = load_skill("performance_notes")
            if performance_notes and len(performance_notes) > 100:
                composed = composed + separator + performance_notes
        except FileNotFoundError:
            pass  # No performance notes yet, that's fine

    if template_vars:
        for k, v in template_vars.items():
            # Handle both double-brace {{key}} and single-brace {key} in skill files
            composed = composed.replace(f"{{{{{k}}}}}", str(v))
            composed = composed.replace(f"{{{k}}}", str(v))

    if max_tokens:
        try:
            from utils.llm.prompt_compressor import estimate_tokens
            current = estimate_tokens(composed)
            if current > max_tokens:
                # Jika over-budget, coba pangkas performance_notes opsional terlebih dahulu
                if "performance_notes" in skill_names or "performance notes" in composed.lower():
                    logger.warning(f"Skill composition {current} tok exceeds budget {max_tokens}. Pruning optional performance notes to preserve core rules.")
                    # Buang catatan performa opsional
                    lines = composed.split(separator)
                    filtered = [l for l in lines if "performance_notes" not in l.lower() and "historical execution notes" not in l.lower()]
                    composed = separator.join(filtered)
                    current = estimate_tokens(composed)
                if current > max_tokens:
                    from utils.llm.prompt_compressor import truncate_to_budget
                    composed = truncate_to_budget(composed, max_tokens)
        except Exception as e:
            logger.debug(f"Max tokens enforcement non-fatal: {e}")

    return composed


def invalidate_cache() -> None:
    """Kosongkan cache memori LRU untuk skill."""
    load_skill.cache_clear()
    logger.info("Skill cache cleared")


def get_dynamic_micro_skills(symbol: str, context: Optional[dict] = None) -> list[str]:
    """Menghasilkan list skill yang terarah dinamis berdasarkan aset dan regim pasar."""
    sym = (symbol or "").strip().upper().replace("/", "")
    ctx = context or {}

    # Base core skills present in all analytical agents
    skills = [
        "adjudication_framework",
        "central_banks_framework",
        "smc_ict_playbook",
        "market_dynamics_framework",
        "liquidity_and_macro_edge",
        "risk_management_principles",
        "session_timing_rules",
        "lessons_learned",
    ]

    # Asset-specific micro-agent playbooks
    if sym in ("BTCUSD", "ETHUSD", "SOLUSD") or "crypto" in sym.lower():
        if "crypto_analysis" not in skills:
            skills.insert(1, "crypto_analysis")
    elif sym in ("XAUUSD", "XTIUSD", "BRENT", "XAGUSD") or "commodity" in sym.lower():
        if "commodity_analysis" not in skills:
            skills.insert(1, "commodity_analysis")

    # Dynamic autonomous micro-playbook routing
    regime = str(ctx.get("regime") or ctx.get("macro_regime") or "").lower().strip()
    if regime:
        regime_tokens = [regime]
        if "trend" in regime:
            regime_tokens.extend(["trend", "trending"])
        elif "range" in regime or "chop" in regime:
            regime_tokens.extend(["range", "ranging", "chop"])
        elif regime.endswith("ing"):
            regime_tokens.append(regime[:-3])
        elif regime.endswith("e"):
            regime_tokens.append(regime[:-1] + "ing")
        else:
            regime_tokens.append(regime + "ing")

        seen_candidates = set()
        matched = False
        for r in regime_tokens:
            for candidate_playbook in (f"{sym.lower()}_{r}_playbook", f"{sym.lower()}_{r}"):
                if candidate_playbook not in seen_candidates:
                    seen_candidates.add(candidate_playbook)
                    playbook_path = _SKILLS_DIR / "playbooks" / f"{candidate_playbook}.md"
                    if playbook_path.exists() and candidate_playbook not in skills:
                        skills.insert(2, candidate_playbook)
                        matched = True
                        break
            if matched:
                break

    # Crystallized operational playbooks (closed-loop learning)
    try:
        from analysis.memory.skill_crystallizer import SkillCrystallizer
        crystallized = SkillCrystallizer.get_crystallized_skills_for_symbol(sym)
        for c_name in crystallized[:2]:
            if c_name not in skills and not SkillCrystallizer.is_skill_deprecated(c_name):
                skills.insert(2, c_name)
        # Exclude any deprecated skill that might be in the candidate list
        skills = [s for s in skills if not SkillCrystallizer.is_skill_deprecated(s)]
    except Exception as e:
        logger.debug(f"Crystallized skills load non-fatal: {e}")

    return skills


class SafeDict(dict):
    """Dict helper yang biarkan {key} tak tersentuh jika variabel tidak diprovide."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"

# Backward compat alias
_SafeDict = SafeDict

__all__ = ['load_skill', 'list_skills', 'compose_system_prompt', 'get_dynamic_micro_skills', 'invalidate_cache', 'SafeDict']
