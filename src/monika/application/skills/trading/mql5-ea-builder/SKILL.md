---
name: mql5-ea-builder
description: "MQL5 Expert Advisor and script generation with strict risk rules."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [mql5, ea, expert_advisor, robot_trading, metaeditor, ontick, oninit, mql, script_mt5]
---

# MQL5 Expert Advisor & Custom Indicator Architecture

## 1. Engineering Principles
When generating MetaTrader 5 (MQL5) code for Expert Advisors (EAs), custom scripts, or indicators:
- **Risk Invariant**: Always enforce hardcoded stop losses and client-side lot sizing validation before dispatching `OrderSend()`.
- **Async Execution Safety**: Handle retries on requotes (`TRADE_RETCODE_REQUOTE`), off quotes, and connection timeouts gracefully.
- **Modern Object-Oriented Standard**: Use standard library classes `<Trade\Trade.mqh>` and `<Trade\SymbolInfo.mqh>` instead of legacy procedural MQL4 patterns.

## 2. Standard EA Skeleton Structure

```mql5
//+------------------------------------------------------------------+
//|                                                MonikaEA_Template |
//|                                  Copyright 2026, Monika Quant    |
//+------------------------------------------------------------------+
#property copyright "Monika Institutional Engine"
#property link      "https://github.com/monika-quant"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>

input group "=== Risk Management ==="
input double InpRiskPercent    = 1.0;    // Risk per trade (% of equity)
input double InpMaxDailyLoss   = 3.0;    // Max daily drawdown kill-switch (%)
input int    InpMagicNumber    = 108823; // Magic Number
input int    InpSlippagePoints = 10;     // Max allowable slippage

CTrade trade;
CSymbolInfo sym;

int OnInit() {
   if(!sym.Name(_Symbol)) return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   // Resource cleanup
}

void OnTick() {
   if(!sym.RefreshRates()) return;
   
   // Ensure bar close check if evaluating higher timeframe signals
   static datetime last_bar = 0;
   datetime current_bar = iTime(_Symbol, _Period, 0);
   if(current_bar == last_bar) return;
   last_bar = current_bar;

   // Signal evaluation and execution logic here
}
```

## 3. Best Practices for Operator Delivery
1. Provide the complete, fully compilable `.mq5` source code.
2. Outline exact MetaEditor compilation instructions (Press F7 in MetaEditor).
3. Specify required input parameters and recommended backtest modeling quality (Every tick based on real ticks).
