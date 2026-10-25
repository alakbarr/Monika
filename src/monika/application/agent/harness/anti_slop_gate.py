"""
Deterministic Anti-Slop Quality Gate & Sentence-Boundary Text Distiller.

Enforces institutional output standards across Monika's autonomous stages and chat responses:
1. Lexical Slop & Sycophantic Opener Detection: Rejects or strips stock AI filler phrases.
2. Placeholder & Stub Detection: Blocks unfinished placeholders (TODO, [insert ...], etc.).
3. Zero-Emoji Enforcement: Strips or flags Unicode pictographs/emoticons while preserving math/bullet typography.
4. Quantitative Grounding Density: Ensures analytical narratives cite concrete numbers/levels.
5. Smart Sentence-Boundary Distillation: Replaces mid-word character slicing ([:200]) with semantic sentence extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Banned stock AI slop phrases (case-insensitive)
BANNED_SLOP_PHRASES: Sequence[str] = (
    "delve into",
    "delving into",
    "a testament to",
    "rich tapestry",
    "intricate tapestry",
    "beacon of",
    "in today's fast-paced",
    "in conclusion, it is important to remember",
    "as an ai language model",
    "as an artificial intelligence",
    "i don't have personal opinions, but",
    "certainly! here is",
    "sure! here's",
    "i'd be happy to help you with",
    "tentu saja! berikut adalah",
    "sebagai model bahasa ai",
    "mari kita selami lebih dalam",
)

# Sycophantic opener regexes that can be stripped cleanly from the start of a response
_SYCOPHANTIC_OPENER_RE = re.compile(
    r"^\s*(?:certainly!|sure!|of course!|absolutely!|great question!|"
    r"tentu saja!|baik,?\s*berikut\s+adalah|dengan\s+senang\s+hati[,!])"
    r"[^\n.:!]*[:.!]\s*",
    re.IGNORECASE,
)

# Conversational closer / sign-off regexes that can be stripped from the tail of a response
_CONVERSATIONAL_CLOSER_RE = re.compile(
    r"(?:\n\s*|\A\s*)(?:hope this helps!|let me know if you need anything else!|"
    r"feel free to ask!|semoga membantu!|jangan ragu untuk bertanya!)[^\n]*\s*$",
    re.IGNORECASE,
)

# Unfinished placeholder patterns in analytical/code deliverables
_PLACEHOLDER_PATTERNS: Sequence[tuple[re.Pattern[str], str]] = (
    (re.compile(r"\[(?:insert|fill\s+in|todo|placeholder|tbd)\b[^\]]*\]", re.IGNORECASE), "bracketed placeholder"),
    (re.compile(r"<(?:insert|todo|placeholder|fill_in)\b[^>]*>", re.IGNORECASE), "angle-bracket placeholder"),
    (re.compile(r"\blorem\s+ipsum\b", re.IGNORECASE), "lorem ipsum dummy text"),
)

# Unicode emoji pictograph ranges (excludes standard math symbols, arrows, and • bullets)
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "]+",
    flags=re.UNICODE,
)

_QUANT_ANCHOR_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?%?|\b(?:atr|adr|rsi|adx|vix|dxy|fvg|ob|bos|choch|ote|sl|tp|bps|cpi|nfp|fomc|cot)\b)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class AntiSlopVerdict:
    """Result of evaluating agent output against the AntiSlopQualityGate."""

    passed: bool
    violations: List[str] = field(default_factory=list)
    remediation_prompt: str = ""

    def __bool__(self) -> bool:
        return self.passed


class AntiSlopQualityGate:
    """Deterministic quality gate preventing AI slop, placeholders, and ungrounded fluff."""

    @classmethod
    def evaluate(
        cls,
        text: str,
        *,
        stage_name: str = "general",
        require_quantitative_grounding: bool = False,
        forbid_emojis: bool = False,
    ) -> AntiSlopVerdict:
        """Evaluate text for banned AI slop phrases, unfinished placeholders, and grounding density."""
        if not text or not text.strip():
            return AntiSlopVerdict(passed=True)

        violations: List[str] = []
        text_lower = text.lower()

        # 1. Check banned lexical slop phrases
        matched_slop = [phrase for phrase in BANNED_SLOP_PHRASES if phrase in text_lower]
        if matched_slop:
            violations.append(f"Banned AI filler phrase(s) detected: {matched_slop[:3]}")

        # 2. Check unfinished placeholders
        for pattern, label in _PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                violations.append(f"Unfinished {label} detected: '{match.group(0)[:40]}'")

        # 3. Check Unicode emojis when forbidden
        if forbid_emojis:
            emoji_match = _EMOJI_RE.search(text)
            if emoji_match:
                violations.append(f"Forbidden Unicode emoji detected: '{emoji_match.group(0)}'")

        # 4. Check quantitative grounding for substantive analytical stages
        if require_quantitative_grounding and len(text.strip()) >= 160:
            anchors = _QUANT_ANCHOR_RE.findall(text)
            if len(anchors) < 2:
                violations.append(
                    "Insufficient quantitative grounding: analytical narrative must cite concrete numbers, "
                    "price levels, percentages, or structural indicators (found < 2 anchors)."
                )

        if not violations:
            return AntiSlopVerdict(passed=True)

        remediation = (
            f"[ANTI-SLOP QUALITY GATE REJECTION ({stage_name})]:\n"
            + "\n".join(f"- {v}" for v in violations)
            + "\nRewrite your response or tool submission with dense, concrete quantitative evidence, "
            "direct causal mechanisms, and zero AI filler phrases or placeholders."
        )
        return AntiSlopVerdict(
            passed=False,
            violations=violations,
            remediation_prompt=remediation,
        )

    @classmethod
    def sanitize_surface_slop(cls, text: str, *, strip_emojis: bool = True) -> str:
        """Clean sycophantic openers, closers, and forbidden emojis from user-facing text without altering numbers."""
        if not text:
            return text
        cleaned = _SYCOPHANTIC_OPENER_RE.sub("", text, count=1)
        cleaned = _CONVERSATIONAL_CLOSER_RE.sub("", cleaned, count=1)
        if strip_emojis:
            cleaned = _EMOJI_RE.sub("", cleaned)
        # Collapse any accidental triple blank lines created by stripping
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


def smart_distill_text(
    text: Optional[str],
    max_chars: int = 240,
    max_sentences: int = 0,
) -> str:
    """
    Distill text to complete sentences or clauses within max_chars without mid-word truncation.
    Prioritizes sentences with numerical/market anchors when selecting a subset of sentences.
    """
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= max_chars and (max_sentences <= 0 or cleaned.count(".") <= max_sentences):
        return cleaned

    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
    if not raw_sentences:
        return cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:") + "."

    # If max_sentences is specified, pick the highest-signal sentences in original order
    if max_sentences > 0 and len(raw_sentences) > max_sentences:
        scored = []
        for idx, sent in enumerate(raw_sentences):
            anchor_count = len(_QUANT_ANCHOR_RE.findall(sent))
            # First sentence gets a structural lead bonus
            score = anchor_count * 2 + (3 if idx == 0 else 0)
            scored.append((score, idx, sent))
        top_indices = {idx for _, idx, _ in sorted(scored, key=lambda item: (-item[0], item[1]))[:max_sentences]}
        selected_sentences = [s for idx, s in enumerate(raw_sentences) if idx in top_indices]
    else:
        selected_sentences = raw_sentences

    accumulated: List[str] = []
    current_len = 0
    for sent in selected_sentences:
        sep_len = 1 if accumulated else 0
        if current_len + sep_len + len(sent) <= max_chars:
            accumulated.append(sent)
            current_len += sep_len + len(sent)
        else:
            break

    if accumulated:
        return " ".join(accumulated)

    # Single sentence exceeds max_chars: snap to nearest clause or word boundary
    first_sent = selected_sentences[0][:max_chars]
    for delimiter in ("; ", ", ", " — ", " - "):
        idx = first_sent.rfind(delimiter)
        if idx >= max_chars // 2:
            return first_sent[:idx].rstrip() + "."
    word_snap = first_sent.rsplit(" ", 1)[0].rstrip(".,;:-")
    return (word_snap or first_sent).rstrip() + "..."
