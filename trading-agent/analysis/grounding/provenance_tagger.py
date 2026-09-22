"""
Provenance Tagger & Ledger: Tracks numeric provenance of tool outputs
and cross-verifies figures cited by LLM agents.
Source: Vibe-Trading src/agent/grounding/
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("TradingAgent.ProvenanceTagger")


@dataclass(frozen=True)
class ObservedFact:
    """Single numeric fact extracted from tool output."""
    field: str
    value: float
    tool_name: str
    timestamp: datetime


class ProvenanceLedger:
    """
    Append-only registry of numeric facts produced by tool executions.
    Can verify whether cited prices/numbers in LLM reasoning were empirically observed.
    """

    def __init__(self):
        self._facts: List[ObservedFact] = []

    def register_from_tool_output(self, tool_name: str, result: Any) -> int:
        """Parse numeric values from tool result and register as observed facts."""
        numerics = self._extract_numerics(result)
        count = 0
        now = datetime.now(timezone.utc)
        for key, val in numerics.items():
            self._facts.append(
                ObservedFact(field=key, value=val, tool_name=tool_name, timestamp=now)
            )
            count += 1
        return count

    def register_fact(self, field_name: str, value: float, tool_name: str = "manual") -> None:
        """Manually register a single observed fact."""
        self._facts.append(
            ObservedFact(
                field=field_name,
                value=float(value),
                tool_name=tool_name,
                timestamp=datetime.now(timezone.utc),
            )
        )

    def verify_citation(
        self, claimed_value: float, field_hint: str = "", tolerance: float = 1e-4
    ) -> Optional[ObservedFact]:
        """Find nearest matching observed fact within relative tolerance."""
        best: Optional[ObservedFact] = None
        best_dist = float("inf")

        for fact in self._facts:
            if field_hint and field_hint.lower() not in fact.field.lower():
                continue
            dist = abs(fact.value - claimed_value)
            denom = abs(fact.value) if abs(fact.value) > 1e-8 else 1.0
            rel_dist = dist / denom

            if rel_dist <= tolerance and dist < best_dist:
                best = fact
                best_dist = dist

        return best

    def verify_text_citations(
        self, text: str, tolerance: float = 1e-3
    ) -> Tuple[int, int, List[float]]:
        """
        Scan text for numbers and verify against ledger facts.
        Returns: (verified_count, unverified_count, unverified_numbers)
        """
        if not text:
            return 0, 0, []

        tokens = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
        verified = 0
        unverified = 0
        unverified_nums: List[float] = []

        for token in tokens:
            try:
                num = float(token)
            except ValueError:
                continue

            # Ignore small structural integers (e.g. 1, 2, 3, 14, 20)
            if num in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 14.0, 20.0, 50.0, 100.0, 200.0):
                continue

            match = self.verify_citation(num, tolerance=tolerance)
            if match:
                verified += 1
            else:
                unverified += 1
                unverified_nums.append(num)

        return verified, unverified, unverified_nums

    def _extract_numerics(self, obj: Any, prefix: str = "") -> Dict[str, float]:
        """Recursively extract float values from nested dict/list/primitives."""
        result: Dict[str, float] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                result.update(self._extract_numerics(v, f"{prefix}{k}."))
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                result.update(self._extract_numerics(v, f"{prefix}[{i}]."))
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            result[prefix.rstrip(".")] = float(obj)
        return result

    @property
    def facts(self) -> List[ObservedFact]:
        return list(self._facts)

    def verify_lot_size(
        self,
        symbol: str,
        lot_size: Optional[float],
        account_equity: Optional[float] = None,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        risk_pct: float = 1.0,
        max_leverage: float = 30.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that proposed lot size is mathematically grounded in risk rules and equity.
        Prevents hallucinated lot sizes (e.g. 50.0 lots on a $1,000 account).
        """
        if lot_size is None or lot_size <= 0:
            return False, f"Ungrounded lot size: lot_size must be positive (received {lot_size})."

        # Standard broker bounds: min 0.01, max 100.0
        if lot_size < 0.01:
            return False, f"Ungrounded lot size {lot_size}: below broker minimum 0.01 lots."
        if lot_size > 100.0:
            return False, f"Ungrounded lot size {lot_size}: exceeds safety ceiling of 100.0 lots."

        if account_equity and account_equity > 0:
            sym_u = symbol.upper()
            contract_size = 100000.0
            if "XAU" in sym_u or "GOLD" in sym_u:
                contract_size = 100.0
            elif "BTC" in sym_u or "ETH" in sym_u or "XTI" in sym_u or "XBR" in sym_u:
                contract_size = 1.0

            eff_price = entry_price if (entry_price and entry_price > 0) else 1.0
            notional = lot_size * contract_size * eff_price
            max_permitted_notional = account_equity * max_leverage

            if notional > max_permitted_notional:
                return False, (
                    f"Ungrounded lot size {lot_size}: notional exposure ${notional:,.2f} "
                    f"exceeds maximum permitted leverage ({max_leverage}x equity = ${max_permitted_notional:,.2f})."
                )

            # Check risk-based theoretical lot
            if entry_price and stop_loss and entry_price > 0 and stop_loss > 0:
                sl_distance = abs(entry_price - stop_loss)
                if sl_distance > 0:
                    max_risk_usd = account_equity * (risk_pct / 100.0)
                    risk_per_lot_usd = sl_distance * contract_size
                    if risk_per_lot_usd > 0:
                        theoretical_lot = max_risk_usd / risk_per_lot_usd
                        if lot_size > theoretical_lot * 2.5 and lot_size > 0.05:
                            return False, (
                                f"Ungrounded lot size {lot_size}: exceeds theoretical risk-based lot "
                                f"{theoretical_lot:.2f} by more than 2.5x at {risk_pct}% equity risk (${max_risk_usd:.2f})."
                            )

        return True, None

    def verify_spread(
        self,
        symbol: str,
        empirical_spread: Optional[float] = None,
        cited_spread: Optional[float] = None,
        max_spread_ceiling: float = 60.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that spread is within tradeable bounds and cited spread is grounded in empirical data.
        """
        if empirical_spread is not None:
            if empirical_spread < 0:
                return False, f"Negative empirical spread ({empirical_spread}) is anomalous."
            if empirical_spread > max_spread_ceiling:
                return False, (
                    f"Empirical spread for {symbol} ({empirical_spread:.1f} pts) exceeds "
                    f"maximum tradeable ceiling ({max_spread_ceiling:.1f} pts). Spread blowout detected."
                )

        if cited_spread is not None and empirical_spread is not None and empirical_spread > 0:
            diff = abs(cited_spread - empirical_spread)
            if diff / empirical_spread > 0.50 and diff > 5.0:
                return False, (
                    f"Cited spread ({cited_spread:.1f}) diverges substantially from empirical "
                    f"market spread ({empirical_spread:.1f}). Possible hallucinated liquidity condition."
                )

        return True, None

    def verify_margin(
        self,
        symbol: str,
        lot_size: Optional[float],
        entry_price: Optional[float],
        free_margin: Optional[float],
        leverage: float = 100.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that account has sufficient free margin to support proposed position with 20% safety buffer.
        """
        if free_margin is None or free_margin <= 0:
            return False, f"Ungrounded account state: free_margin must be positive (received {free_margin})."

        sym_u = symbol.upper()
        contract_size = 100000.0
        if "XAU" in sym_u or "GOLD" in sym_u:
            contract_size = 100.0
        elif "BTC" in sym_u or "ETH" in sym_u or "XTI" in sym_u or "XBR" in sym_u:
            contract_size = 1.0

        eff_price = entry_price if (entry_price and entry_price > 0) else 1.0
        notional = (lot_size or 0.0) * contract_size * eff_price
        eff_leverage = max(1.0, leverage)
        estimated_margin_required = notional / eff_leverage

        max_usable_margin = free_margin * 0.80  # 20% safety margin buffer
        if estimated_margin_required > max_usable_margin:
            return False, (
                f"Insufficient margin for {symbol}: estimated required margin ${estimated_margin_required:,.2f} "
                f"exceeds 80% of free margin (${max_usable_margin:,.2f} of ${free_margin:,.2f})."
            )

        return True, None

    def verify_equity(
        self,
        account_equity: Optional[float],
        min_equity: float = 50.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that account equity is grounded, positive, and above operational floor.
        """
        if account_equity is None or account_equity <= 0:
            return False, f"Ungrounded account equity: equity must be positive (received {account_equity})."
        if account_equity < min_equity:
            return False, (
                f"Account equity (${account_equity:.2f}) is below minimum operational floor (${min_equity:.2f})."
            )
        return True, None

    def verify_trade_parameters(
        self,
        proposal: Dict[str, Any],
        market_snapshot: Dict[str, Any],
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Comprehensive grounding verification across all 4 extended dimensions (lot_size, spread, margin, equity)
        in addition to entry_price and stop_loss.
        """
        errors: List[str] = []
        meta: Dict[str, Any] = {"verified_extended": 0}

        symbol = str(proposal.get("symbol") or market_snapshot.get("symbol") or "UNKNOWN")
        entry_price = proposal.get("entry_price") or proposal.get("entry")
        stop_loss = proposal.get("stop_loss") or proposal.get("sl")
        lot_size = proposal.get("lot_size") or proposal.get("lots")
        account_equity = proposal.get("account_equity") or market_snapshot.get("account_equity") or market_snapshot.get("equity")
        free_margin = proposal.get("free_margin") or market_snapshot.get("free_margin") or market_snapshot.get("margin_free")
        empirical_spread = market_snapshot.get("spread") or market_snapshot.get("tick_spread")
        cited_spread = proposal.get("spread")

        # 1. Equity Grounding
        if account_equity is not None:
            ok, err = self.verify_equity(float(account_equity))
            if not ok and err:
                errors.append(err)
            else:
                meta["verified_extended"] += 1

        # 2. Lot Size Grounding
        if lot_size is not None:
            ok, err = self.verify_lot_size(
                symbol=symbol,
                lot_size=float(lot_size),
                account_equity=float(account_equity) if account_equity is not None else None,
                entry_price=float(entry_price) if entry_price is not None else None,
                stop_loss=float(stop_loss) if stop_loss is not None else None,
            )
            if not ok and err:
                errors.append(err)
            else:
                meta["verified_extended"] += 1

        # 3. Spread Grounding
        if empirical_spread is not None or cited_spread is not None:
            ok, err = self.verify_spread(
                symbol=symbol,
                empirical_spread=float(empirical_spread) if empirical_spread is not None else None,
                cited_spread=float(cited_spread) if cited_spread is not None else None,
            )
            if not ok and err:
                errors.append(err)
            else:
                meta["verified_extended"] += 1

        # 4. Margin Grounding
        if free_margin is not None and lot_size is not None:
            ok, err = self.verify_margin(
                symbol=symbol,
                lot_size=float(lot_size),
                entry_price=float(entry_price) if entry_price is not None else None,
                free_margin=float(free_margin),
            )
            if not ok and err:
                errors.append(err)
            else:
                meta["verified_extended"] += 1

        return len(errors) == 0, errors, meta
