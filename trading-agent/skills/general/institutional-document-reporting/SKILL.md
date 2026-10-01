---
name: institutional-document-reporting
description: "Institutional document and pitch deck generation (Word .docx, PowerPoint .pptx, Excel .xlsx, PDF tearsheets)."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [document_generation, office, docx, pptx, excel, tearsheet, pdf, reporting, investor_pitch]
---

# Institutional Document & Reporting Playbook

This skill governs the algorithmic production of publication-grade financial documents across four primary formats:
1. **Microsoft Word (`.docx`)**: Detailed qualitative narrative, portfolio performance summaries, and governance memos.
2. **Microsoft PowerPoint (`.pptx`)**: 16:9 widescreen investor pitch decks, architectural presentations, and strategy reviews.
3. **Microsoft Excel (`.xlsx`)**: Comprehensive trade journals, granular fill histories, PnL attribution, and commission/spread breakdowns.
4. **Quant Tearsheet (`.html` / `.pdf`)**: Institutional tearsheets featuring equity curves, underwater drawdown profiles, and risk ratios.

---

## 1. Document Architecture & Style Guidelines

### 1.1 Color Palette
- **Primary Navy (`#102C57`)**: Major headers, title backgrounds, and table primary banners.
- **Accent Gold / Brass (`#DAA520` / `#C5A059`)**: Key metric callouts, ratios, and subtitles.
- **Neutral Dark (`#282C34`)**: Body text, table cells, and narrative paragraphs.
- **Card Background (`#F5F8FC`)**: Metric boxes and callout containers.

### 1.2 Structure & Standard Sections
Every performance report must include:
1. **Executive Header**: Model name, version, generation timestamp (UTC), and execution mode (Live / Paper).
2. **Core KPIs Table**: Initial Equity, Final Equity, Total Net PnL, Total Return %, Annualized Sharpe, Win Rate %, Profit Factor, Max Drawdown %, Trade Expectancy (R).
3. **Attribution Analysis**: Breakdown by symbol, strategy, and market regime.
4. **LLM Qualitative Narrative**: Synthesis of market dynamics, macro headwinds, and key wins/losses.
5. **Operational Disclaimer**: Mandatory research & simulation notice.

---

## 2. Python Generator API Reference

### Word Document Generation (`DocxReportGenerator`):
```python
from logging_observability.reporting.docx_report_generator import DocxReportGenerator

generator = DocxReportGenerator(output_dir="data/reports")
filepath = generator.generate_report(
    metrics={
        "initial_equity": 10000.0,
        "final_equity": 11450.0,
        "total_net_pnl": 1450.0,
        "total_return_pct": 14.50,
        "annualized_sharpe": 1.85,
        "win_rate_pct": 62.5,
        "profit_factor": 2.10,
        "max_drawdown_pct": 2.40,
        "total_trades": 48,
        "expectancy_r": 0.45,
    },
    narrative_synthesis="During Q3, the system captured significant trend expansions on XAUUSD and EURUSD...",
    recommendations=[
        "Maintain conservative position sizing during FOMC weeks.",
        "Tighten trailing stops on Friday afternoon sessions."
    ],
    title="Monika Portfolio Performance Review"
)
```

### PowerPoint Deck Generation (`PptxDeckGenerator`):
```python
from logging_observability.reporting.pptx_deck_generator import PptxDeckGenerator

deck_gen = PptxDeckGenerator(output_dir="data/reports")
filepath = deck_gen.generate_pitch_deck(
    metrics={
        "total_return_pct": 18.2,
        "annualized_sharpe": 1.92,
        "win_rate_pct": 64.0,
        "winning_trades": 32,
        "losing_trades": 18,
        "profit_factor": 2.25,
        "max_drawdown_pct": 2.10,
        "expectancy_r": 0.52,
    },
    title="Monika Autonomous Trading Agent",
    subtitle="Quantitative Multi-Agent Architecture & Performance Deck"
)
```

### Excel Workbook Export:
```python
import pandas as pd

def export_trades_to_excel(trades: list[dict], filepath: str):
    df = pd.DataFrame(trades)
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Trade_Log', index=False)
```
