import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import MetaTrader5 as mt5
from scripts.build_empirical_playbooks import Evaluator, get_all_signal_generators


def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"]

    param_grid = [
        {"sl": 0.8, "tp": 1.4, "hold": 10},
        {"sl": 0.8, "tp": 1.6, "hold": 12},
        {"sl": 1.0, "tp": 1.5, "hold": 10},
        {"sl": 1.0, "tp": 1.8, "hold": 12},
        {"sl": 1.0, "tp": 2.0, "hold": 14},
        {"sl": 1.2, "tp": 1.8, "hold": 14},
        {"sl": 1.2, "tp": 2.2, "hold": 16},
        {"sl": 1.2, "tp": 2.4, "hold": 18},
        {"sl": 1.2, "tp": 3.0, "hold": 22},
        {"sl": 1.4, "tp": 2.2, "hold": 16},
        {"sl": 1.4, "tp": 2.8, "hold": 20},
        {"sl": 1.5, "tp": 2.5, "hold": 20},
        {"sl": 1.5, "tp": 3.2, "hold": 24},
        {"sl": 1.5, "tp": 3.5, "hold": 28},
        {"sl": 1.8, "tp": 3.0, "hold": 24},
        {"sl": 1.8, "tp": 3.6, "hold": 30},
    ]

    summary = {}
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 4500)
        if rates is None:
            continue
        df = pd.DataFrame(rates)
        ev = Evaluator(sym, df)
        sigs = get_all_signal_generators(ev)
        passing = []
        for name, s_fn in sigs.items():
            best_m = None
            best_p = None
            for p in param_grid:
                m = ev.simulate_signals(s_fn, p["sl"], p["tp"], p["hold"])
                # Strict user criteria: PF >= 1.25, PnL >= 15%, WR >= 40%, DD <= 15%, N >= 15
                if (
                    m["total_trades"] >= 15
                    and m["profit_factor"] >= 1.25
                    and m["total_pnl_pct"] >= 15.0
                    and m["win_rate_pct"] >= 40.0
                    and m["max_drawdown_pct"] <= 15.0
                ):
                    if best_m is None or m["total_pnl_pct"] > best_m["total_pnl_pct"]:
                        best_m = m
                        best_p = p
            if best_m is not None:
                passing.append((name, best_m, best_p))
        summary[sym] = passing
        print(f"{sym}: {len(passing)} meet STRICT criteria (PF>=1.25, PnL>=15%, WR>=40%, DD<=15%, N>=15)")

    mt5.shutdown()
    for sym, pbs in summary.items():
        print(f"\n=== {sym} ({len(pbs)} passing strict) ===")
        for name, m, p in pbs:
            print(
                f"  {name:26}: PnL=+{m['total_pnl_pct']:5.1f}% | PF={m['profit_factor']:4.2f} | WR={m['win_rate_pct']:4.1f}% | DD={m['max_drawdown_pct']:4.1f}% | N={m['total_trades']:3d} | SL={p['sl']} TP={p['tp']}"
            )


if __name__ == "__main__":
    main()
