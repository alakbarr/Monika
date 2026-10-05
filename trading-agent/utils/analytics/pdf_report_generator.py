# ==============================================================================
# File: utils/analytics/pdf_report_generator.py
# ==============================================================================

"""
Automated Weekly & Monthly Executive PDF Performance Report Generator.
Compiles executive metrics, trade distribution, risk posture, and equity curves
into publication-quality PDF documents using ReportLab (Q144).
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import utils.clock as clock

logger = logging.getLogger("TradingAgent.PDFReportGenerator")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


class PDFReportGenerator:
    """Compiles automated trading desk performance tear-sheets into PDF documents."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or "data/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_performance_pdf(
        self,
        metrics: Dict[str, Any],
        report_title: str = "Weekly Performance Tear-Sheet",
        period_label: Optional[str] = None,
        chart_png_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Builds institutional PDF tear-sheet.
        metrics: {
            "total_trades": int,
            "win_rate_pct": float,
            "net_pnl": float,
            "profit_factor": float,
            "sharpe_ratio": float,
            "max_drawdown_pct": float,
            "expectancy_usd": float,
            "avg_win_usd": float,
            "avg_loss_usd": float,
            "trades_by_symbol": dict,
        }
        """
        now = clock.now()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        period = period_label or now.strftime("Week ending %Y-%m-%d")
        filename = f"monika_report_{timestamp_str}.pdf"
        filepath = self.output_dir / filename

        if not HAS_REPORTLAB:
            # Fallback markdown report if reportlab is not installed
            md_filename = f"monika_report_{timestamp_str}.md"
            md_path = self.output_dir / md_filename
            md_content = (
                f"# Monika Executive Trading Desk Report\n"
                f"**{report_title}** | {period}\n\n"
                f"### Core Performance Metrics\n"
                f"- **Total Closed Trades**: {metrics.get('total_trades', 0)}\n"
                f"- **Win Rate**: {metrics.get('win_rate_pct', 0.0):.1f}%\n"
                f"- **Net Profit**: ${metrics.get('net_pnl', 0.0):+,.2f}\n"
                f"- **Profit Factor**: {metrics.get('profit_factor', 0.0):.2f}\n"
                f"- **Sharpe Ratio**: {metrics.get('sharpe_ratio', 0.0):.2f}\n"
                f"- **Max Drawdown**: {metrics.get('max_drawdown_pct', 0.0):.2f}%\n"
                f"- **Expectancy**: ${metrics.get('expectancy_usd', 0.0):+,.2f}\n\n"
                f"*(ReportLab not installed; compiled to Markdown tear-sheet)*\n"
            )
            md_path.write_text(md_content, encoding="utf-8")
            return {
                "success": True,
                "file_path": str(md_path),
                "format": "markdown",
                "message": "ReportLab missing; generated markdown tear-sheet fallback.",
            }

        try:
            doc = SimpleDocTemplate(
                str(filepath),
                pagesize=letter,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40,
            )
            styles = getSampleStyleSheet()

            # Custom typography styles
            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Heading1"],
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#1A202C"),
                spaceAfter=4,
            )
            subtitle_style = ParagraphStyle(
                "DocSubtitle",
                parent=styles["Normal"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#718096"),
                spaceAfter=15,
            )
            h2_style = ParagraphStyle(
                "DocH2",
                parent=styles["Heading2"],
                fontSize=13,
                leading=16,
                textColor=colors.HexColor("#2B6CB0"),
                spaceBefore=10,
                spaceAfter=6,
            )
            cell_bold = ParagraphStyle("CellBold", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold")
            cell_norm = ParagraphStyle("CellNorm", parent=styles["Normal"], fontSize=9)

            story = []

            # 1. Header Banner
            story.append(Paragraph("MONIKA INSTITUTIONAL TRADING DESK", title_style))
            story.append(Paragraph(f"{report_title} | Period: {period} | Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}", subtitle_style))
            story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=15))

            # 2. Executive Metrics Summary Table
            story.append(Paragraph("Executive Performance Dashboard", h2_style))
            pnl_val = metrics.get("net_pnl", 0.0)
            pnl_color = "#276749" if pnl_val >= 0 else "#C53030"

            metrics_data = [
                [
                    Paragraph("<b>Metric</b>", cell_bold), Paragraph("<b>Value</b>", cell_bold),
                    Paragraph("<b>Benchmark / Target</b>", cell_bold), Paragraph("<b>Status</b>", cell_bold)
                ],
                [
                    Paragraph("Net Realized PnL", cell_norm),
                    Paragraph(f"<font color='{pnl_color}'><b>${pnl_val:+,.2f}</b></font>", cell_norm),
                    Paragraph("Positive Drift (> 0)", cell_norm),
                    Paragraph("PASS" if pnl_val >= 0 else "DEFICIT", cell_bold)
                ],
                [
                    Paragraph("Win Rate (%)", cell_norm),
                    Paragraph(f"<b>{metrics.get('win_rate_pct', 0.0):.1f}%</b>", cell_norm),
                    Paragraph("Min 45.0% (R:R >= 1.5)", cell_norm),
                    Paragraph("OPTIMAL" if metrics.get("win_rate_pct", 0) >= 45 else "MONITOR", cell_norm)
                ],
                [
                    Paragraph("Profit Factor", cell_norm),
                    Paragraph(f"<b>{metrics.get('profit_factor', 0.0):.2f}</b>", cell_norm),
                    Paragraph("Target > 1.30", cell_norm),
                    Paragraph("HEALTHY" if metrics.get("profit_factor", 0) >= 1.3 else "COMPRESSED", cell_norm)
                ],
                [
                    Paragraph("Sharpe Ratio", cell_norm),
                    Paragraph(f"<b>{metrics.get('sharpe_ratio', 0.0):.2f}</b>", cell_norm),
                    Paragraph("Target > 1.50 (Annualized)", cell_norm),
                    Paragraph("STRONG" if metrics.get("sharpe_ratio", 0) >= 1.5 else "ADEQUATE", cell_norm)
                ],
                [
                    Paragraph("Max Period Drawdown", cell_norm),
                    Paragraph(f"<b>{metrics.get('max_drawdown_pct', 0.0):.2f}%</b>", cell_norm),
                    Paragraph("Risk Gate Hard Limit: 5.0%", cell_norm),
                    Paragraph("SAFE" if metrics.get("max_drawdown_pct", 0) < 5.0 else "BREACH", cell_bold)
                ],
                [
                    Paragraph("Trade Expectancy ($)", cell_norm),
                    Paragraph(f"<b>${metrics.get('expectancy_usd', 0.0):+,.2f}</b>", cell_norm),
                    Paragraph("Positive per executed lot", cell_norm),
                    Paragraph("PASS" if metrics.get("expectancy_usd", 0) > 0 else "FAIL", cell_norm)
                ],
                [
                    Paragraph("Total Trades Executed", cell_norm),
                    Paragraph(f"<b>{metrics.get('total_trades', 0)}</b>", cell_norm),
                    Paragraph("Statistical Significance (N >= 30)", cell_norm),
                    Paragraph("ACTIVE", cell_norm)
                ],
            ]

            table = Table(metrics_data, colWidths=[1.8 * inch, 1.5 * inch, 2.3 * inch, 1.2 * inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ]))
            story.append(table)
            story.append(Spacer(1, 15))

            # 3. Embedded Equity Curve Chart if available
            if chart_png_path and os.path.exists(chart_png_path):
                story.append(Paragraph("Visual Equity Trajectory & High-Water Mark", h2_style))
                story.append(Image(chart_png_path, width=6.5 * inch, height=3.0 * inch))
                story.append(Spacer(1, 15))

            # 4. Symbol PnL Breakdown if available
            sym_breakdown = metrics.get("trades_by_symbol")
            if sym_breakdown and isinstance(sym_breakdown, dict):
                story.append(Paragraph("Asset Allocation & Symbol Attribution", h2_style))
                sym_data = [[Paragraph("<b>Asset</b>", cell_bold), Paragraph("<b>Trades</b>", cell_bold), Paragraph("<b>Net PnL</b>", cell_bold)]]
                for sym, s_data in list(sym_breakdown.items())[:8]:
                    tr_cnt = s_data.get("count", 0) if isinstance(s_data, dict) else s_data
                    pnl_s = s_data.get("pnl", 0.0) if isinstance(s_data, dict) else 0.0
                    sym_data.append([
                        Paragraph(str(sym), cell_norm),
                        Paragraph(str(tr_cnt), cell_norm),
                        Paragraph(f"${pnl_s:+,.2f}", cell_norm),
                    ])
                sym_table = Table(sym_data, colWidths=[2.5 * inch, 2.0 * inch, 2.3 * inch])
                sym_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(sym_table)

            doc.build(story)
            logger.info(f"[PDFGenerator] Report generated: {filepath}")
            return {
                "success": True,
                "file_path": str(filepath),
                "format": "pdf",
                "filename": filename,
                "message": f"Successfully compiled PDF report to {filepath}",
            }
        except Exception as e:
            logger.error(f"[PDFGenerator] Error building PDF: {e}")
            return {"success": False, "error": str(e)}
