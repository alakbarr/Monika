"""
Institutional PowerPoint (.pptx) Pitch Deck & Performance Slide Generator for Monika.

Generates presentation decks for investors and quantitative review meetings:
Slide 1: Title & Vision (Monika Autonomous Trading Agent Harness)
Slide 2: Core Philosophy & Architecture (AI Proposes, Mechanical Fortress Disposes)
Slide 3: Quantitative Performance & Key Metrics
Slide 4: Risk Governance & Fortress Mechanics (10-Layer RiskGate)
Slide 5: Multi-Asset Execution & SMC Edge
Slide 6: Conclusion & Research Disclaimer
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("TradingAgent.PptxDeckGenerator")


class PptxDeckGenerator:
    """Generates PowerPoint presentation slide decks for Monika portfolio pitch and review."""

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_pitch_deck(
        self,
        metrics: Dict[str, Any],
        title: str = "Monika Autonomous Trading Agent",
        subtitle: str = "Quantitative Architecture & Performance Deck",
        filename: Optional[str] = None,
    ) -> str:
        """
        Builds and saves a PowerPoint presentation.
        Returns the absolute filepath to the created presentation.
        """
        try:
            import pptx
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor
            from pptx.enum.text import PP_ALIGN
            from pptx.enum.shapes import MSO_SHAPE
        except ImportError as e:
            logger.error(f"python-pptx is not installed: {e}")
            raise ImportError("python-pptx is required for PowerPoint generation. Install via pip install python-pptx") from e

        prs = Presentation()
        # 16:9 Widescreen dimensions
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Color Palette: Deep Navy & Gold/Phosphor
        NAVY = RGBColor(16, 44, 87)
        GOLD = RGBColor(218, 165, 32)
        DARK_GRAY = RGBColor(40, 44, 52)
        LIGHT_BG = RGBColor(245, 247, 250)
        WHITE = RGBColor(255, 255, 255)

        blank_layout = prs.slide_layouts[6]

        # -------------------------------------------------------------
        # Slide 1: Title Slide (Dark Background)
        # -------------------------------------------------------------
        slide1 = prs.slides.add_slide(blank_layout)
        bg1 = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg1.fill.solid()
        bg1.fill.fore_color.rgb = NAVY
        bg1.line.color.rgb = NAVY

        tx_box1 = slide1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(3.0))
        tf1 = tx_box1.text_frame
        tf1.word_wrap = True

        p1 = tf1.paragraphs[0]
        p1.text = title
        p1.font.bold = True
        p1.font.size = Pt(44)
        p1.font.color.rgb = GOLD
        p1.font.name = "Calibri"

        p2 = tf1.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(24)
        p2.font.color.rgb = WHITE
        p2.font.name = "Calibri"
        p2.space_before = Pt(12)

        p3 = tf1.add_paragraph()
        now_str = datetime.now(timezone.utc).strftime("%B %Y")
        p3.text = f"MetaTrader 5 Multi-Agent Execution Framework | {now_str}"
        p3.font.size = Pt(14)
        p3.font.italic = True
        p3.font.color.rgb = RGBColor(180, 200, 230)
        p3.space_before = Pt(20)

        # -------------------------------------------------------------
        # Slide 2: Core Philosophy & Architecture
        # -------------------------------------------------------------
        slide2 = prs.slides.add_slide(blank_layout)
        self._add_slide_header(slide2, "Core Philosophy & System Architecture", NAVY, GOLD)

        items_s2 = [
            ("AI Proposes, Mechanical Fortress Disposes", "Probabilistic LLM models only formulate trade hypotheses. Deterministic Python controls all position sizing, broker execution, and stops."),
            ("Dialectical Multi-Agent Adversarial Debate", "Specialized Bullish and Bearish personas cross-examine trade hypotheses. An impartial Investment Judge arbitrates before order creation."),
            ("Fail-Closed Safety Fortress", "10-layer immutable RiskGate enforcing daily drawdown ceilings, spread filters, and news event blackout periods."),
            ("MQL5 Dead-Man Switch", "Independent Expert Advisor (AIAgent_EA) automatically secures active capital if Python process disconnects."),
        ]
        self._add_bullet_cards(slide2, items_s2, prs.slide_width, NAVY, DARK_GRAY)

        # -------------------------------------------------------------
        # Slide 3: Performance & Key Metrics
        # -------------------------------------------------------------
        slide3 = prs.slides.add_slide(blank_layout)
        self._add_slide_header(slide3, "Quantitative Performance & Track Record", NAVY, GOLD)

        kpi_cards = [
            ("Total Return", f"{metrics.get('total_return_pct', 0.0):+.2f}%", "Overall portfolio growth"),
            ("Annualized Sharpe", f"{metrics.get('annualized_sharpe', 0.0):.2f}", "Risk-adjusted return"),
            ("Win Rate", f"{metrics.get('win_rate_pct', 0.0):.1f}%", f"{metrics.get('winning_trades', 0)}W / {metrics.get('losing_trades', 0)}L"),
            ("Profit Factor", f"{metrics.get('profit_factor', 0.0):.2f}", "Gross profit / gross loss"),
            ("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0.0):.2f}%", "Peak-to-valley ceiling"),
            ("Trade Expectancy", f"{metrics.get('expectancy_r', 0.0):+.2f} R", "Average gain per risk unit"),
        ]
        self._add_metric_grid(slide3, kpi_cards, prs.slide_width, NAVY, GOLD)

        # -------------------------------------------------------------
        # Slide 4: Risk Governance Fortress
        # -------------------------------------------------------------
        slide4 = prs.slides.add_slide(blank_layout)
        self._add_slide_header(slide4, "Deterministic Risk Governance (10-Layer RiskGate)", NAVY, GOLD)

        risk_rules = [
            ("1. Max Daily Drawdown", "Hard circuit breaker halts intake if daily floating/realized loss hits 3.0% limit."),
            ("2. High-Impact News Window", "Mandatory ±15 minute blackout around Tier-1 events (FOMC, NFP, CPI, Central Bank rates)."),
            ("3. Volatility Sizing", "Kelly-criterion with dynamic ATR/ADR boundaries for fractional risk protection."),
            ("4. Cross-Asset Correlation", "Prevents concentrated exposure across co-moving FX and commodity pairs."),
        ]
        self._add_bullet_cards(slide4, risk_rules, prs.slide_width, NAVY, DARK_GRAY)

        # -------------------------------------------------------------
        # Slide 5: Disclaimer & Conclusion
        # -------------------------------------------------------------
        slide5 = prs.slides.add_slide(blank_layout)
        self._add_slide_header(slide5, "Operational Governance & Disclaimer", NAVY, GOLD)

        box5 = slide5.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(11.333), Inches(4.5))
        tf5 = box5.text_frame
        tf5.word_wrap = True

        p_disc = tf5.paragraphs[0]
        p_disc.text = "Strictly for Quantitative Research, Simulation, and Algorithmic Trading Supervision."
        p_disc.font.bold = True
        p_disc.font.size = Pt(20)
        p_disc.font.color.rgb = NAVY

        p_body = tf5.add_paragraph()
        p_body.text = (
            "Monika is an advanced open research platform for MetaTrader 5 multi-agent execution. "
            "All paper-trading models require validated graduation (>50 trades with >=55% win rate) "
            "prior to capital allocation. Past quantitative performance is not indicative of future market returns."
        )
        p_body.font.size = Pt(16)
        p_body.font.color.rgb = DARK_GRAY
        p_body.space_before = Pt(16)

        # Save File
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"monika_pitch_deck_{timestamp}.pptx"
        filepath = os.path.join(self.output_dir, filename)
        prs.save(filepath)
        logger.info(f"Pptx pitch deck successfully saved to {filepath}")
        return os.path.abspath(filepath)

    def _add_slide_header(self, slide, title_text, navy_color, gold_color):
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        header_box = slide.shapes.add_textbox(Inches(1.0), Inches(0.6), Inches(11.333), Inches(1.0))
        tf = header_box.text_frame
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.bold = True
        p.font.size = Pt(28)
        p.font.color.rgb = navy_color
        p.font.name = "Calibri"

    def _add_bullet_cards(self, slide, items, slide_width, navy_color, dark_gray):
        from pptx.util import Inches, Pt
        from pptx.enum.shapes import MSO_SHAPE

        card_width = Inches(5.4)
        card_height = Inches(2.2)
        top_row_y = Inches(1.8)
        bot_row_y = Inches(4.3)
        left_col_x = Inches(1.0)
        right_col_x = Inches(6.9)

        coords = [
            (left_col_x, top_row_y),
            (right_col_x, top_row_y),
            (left_col_x, bot_row_y),
            (right_col_x, bot_row_y),
        ]

        for idx, (title, desc) in enumerate(items[:4]):
            x, y = coords[idx]
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_width, card_height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(245, 248, 252)
            shape.line.color.rgb = RGBColor(210, 225, 245)

            tx_box = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.2), card_width - Inches(0.4), card_height - Inches(0.4))
            tf = tx_box.text_frame
            tf.word_wrap = True

            p_title = tf.paragraphs[0]
            p_title.text = title
            p_title.font.bold = True
            p_title.font.size = Pt(16)
            p_title.font.color.rgb = navy_color

            p_desc = tf.add_paragraph()
            p_desc.text = desc
            p_desc.font.size = Pt(13)
            p_desc.font.color.rgb = dark_gray
            p_desc.space_before = Pt(8)

    def _add_metric_grid(self, slide, metrics, slide_width, navy_color, gold_color):
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        card_width = Inches(3.5)
        card_height = Inches(2.2)
        coords = [
            (Inches(1.0), Inches(1.8)),
            (Inches(4.9), Inches(1.8)),
            (Inches(8.8), Inches(1.8)),
            (Inches(1.0), Inches(4.3)),
            (Inches(4.9), Inches(4.3)),
            (Inches(8.8), Inches(4.3)),
        ]

        for idx, (title, value, subtext) in enumerate(metrics[:6]):
            x, y = coords[idx]
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_width, card_height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(245, 248, 252)
            shape.line.color.rgb = RGBColor(210, 225, 245)

            tx = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.15), card_width - Inches(0.4), card_height - Inches(0.3))
            tf = tx.text_frame
            tf.word_wrap = True

            p_title = tf.paragraphs[0]
            p_title.text = title.upper()
            p_title.font.bold = True
            p_title.font.size = Pt(12)
            p_title.font.color.rgb = RGBColor(120, 130, 145)

            p_val = tf.add_paragraph()
            p_val.text = value
            p_val.font.bold = True
            p_val.font.size = Pt(28)
            p_val.font.color.rgb = navy_color
            p_val.space_before = Pt(4)

            p_sub = tf.add_paragraph()
            p_sub.text = subtext
            p_sub.font.size = Pt(11)
            p_sub.font.color.rgb = RGBColor(140, 150, 165)
            p_sub.space_before = Pt(4)
