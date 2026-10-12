---
name: retail-money-management
description: "Capital preservation, lot sizing, margin requirements, and drawdown control."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [money_management, position_sizing, margin, risk_gate, beginner, drawdown]
---

# Retail Money Management & Capital Protection Playbook

## 1. Prime Directive: Survival Before Profit
The number one reason retail traders fail within their first 90 days is improper position sizing leading to catastrophic margin calls during normal market volatility spikes. 

Monika enforces an institutional-grade risk framework tailored to protect retail capital:
1. **Fixed Risk Per Trade**: Maximum risk should strictly never exceed $1.0\%\text{--}2.0\%$ of account equity per trade.
2. **Leverage Illusion Avoidance**: High broker leverage (e.g. 1:100 to 1:500) allows opening dangerous oversized lots. Leverage must be used solely to reduce required margin, never to increase dollar risk.
3. **Daily Loss Circuit Breaker**: If cumulative daily loss hits $3.0\%$ of starting daily balance, all trading is paused automatically for the remainder of the 24-hour cycle.

## 2. Quantitative Position Sizing Mathematical Model
$$\text{Lot Size} = \frac{\text{Account Equity} \times \text{Risk Percentage}}{\text{Stop Loss Distance (pips)} \times \text{Pip Value per Standard Lot}}$$

### Standard Lot Sizing Reference Table
| Account Size | Max 1% Risk ($) | SL 20 pips Lot (EURUSD) | SL 30 pips Lot (GBPUSD) | SL $10 Lot (XAUUSD) |
|:---|:---|:---|:---|:---|
| **$500** | $5.00 | 0.02 lot | 0.01 lot | 0.01 micro |
| **$1,000** | $10.00 | 0.05 lot | 0.03 lot | 0.01 lot |
| **$5,000** | $50.00 | 0.25 lot | 0.16 lot | 0.05 lot |
| **$10,000** | $100.00 | 0.50 lot | 0.33 lot | 0.10 lot |

## 3. Margin Call & Stop Out Defense
- **Free Margin Buffer**: Never allocate more than $15\%$ of total account equity as used margin across concurrent positions.
- **Margin Level Protection**:
  - Healthy Zone: Margin Level $> 500\%$.
  - Caution Zone: Margin Level $200\%\text{--}500\%$ (prohibit opening new positions).
  - Danger Zone: Margin Level $< 150\%$ (trigger immediate position reduction via `close_positions_batch(filter="loss")`).

## 4. Monika Tools for Money Management
- `calculate_position_size(symbol, stop_loss_pips, risk_pct)`: Calculates exact mathematical lot size conforming to equity and instrument contract size.
- `calculate_margin(symbol, lot_size, action)`: Computes exact broker margin required in USD before order proposal.
- `get_account_info()`: Real-time query of balance, equity, margin, free margin, and margin level percentage.
- `simulate_price_shock(symbol, shock_pct)`: Stress-tests portfolio equity against adverse flash crash scenarios.
