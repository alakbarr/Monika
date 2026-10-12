"""
Institutional Word (.docx) Portfolio Performance Report Generator for Monika.

Generates beautifully structured Microsoft Word documents containing:
1. Executive Header & Metadata
2. Quantitative Key Performance Indicators (KPI) Table
3. Risk & Drawdown Profile
4. Multi-Asset Attribution Breakdown
5. LLM Synthesis & Strategic Recommendations
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("TradingAgent.DocxReportGenerator")


class DocxReportGenerator:
    """Generates institutional-grade .docx performance tearsheets and summaries."""

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_report(
        self,
        metrics: Dict[str, Any],
        narrative_synthesis: Optional[str] = None,
        recommendations: Optional[List[str]] = None,
        title: str = "Monika Quantitative Portfolio Performance Report",
        filename: Optional[str] = None,
    ) -> str:
        """
        Builds and saves a styled Word document.
        Returns the absolute filepath to the created document.
        """
        try:
            import docx
            from docx import Document
            from docx.shared import Inches, Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.table import WD_TABLE_ALIGNMENT
            from docx.oxml import parse_xml, OxmlElement
            from docx.oxml.ns import nsdecls, qn
        except ImportError as e:
            logger.error(f"python-docx is not installed: {e}")
            raise ImportError("python-docx is required for Word document generation. Install via pip install python-docx") from e

        doc = Document()

        # Set standard margins
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # Title
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(4)
        run_title = title_p.add_run(title)
        run_title.font.name = 'Calibri'
        run_title.font.size = Pt(22)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(16, 44, 87) # Deep Institutional Blue

        # Subtitle / Metadata
        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_after = Pt(18)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        run_sub = sub_p.add_run(f"System: Monika MT5 Autonomous Agent Harness | Generated: {now_str}")
        run_sub.font.name = 'Calibri'
        run_sub.font.size = Pt(10)
        run_sub.font.italic = True
        run_sub.font.color.rgb = RGBColor(100, 110, 125)

        # Section 1: Executive KPI Summary
        h1 = doc.add_heading("1. Executive Performance Summary", level=1)
        h1.paragraph_format.space_before = Pt(12)
        h1.paragraph_format.space_after = Pt(6)

        kpis = [
            ("Initial Equity", f"${metrics.get('initial_equity', 10000.0):,.2f}", "Total Net PnL", f"${metrics.get('total_net_pnl', 0.0):+,.2f}"),
            ("Final Equity", f"${metrics.get('final_equity', 10000.0):,.2f}", "Total Return", f"{metrics.get('total_return_pct', 0.0):+.2f}%"),
            ("Annualized Sharpe", f"{metrics.get('annualized_sharpe', 0.0):.2f}", "Win Rate", f"{metrics.get('win_rate_pct', 0.0):.1f}%"),
            ("Profit Factor", f"{metrics.get('profit_factor', 0.0):.2f}", "Max Drawdown", f"{metrics.get('max_drawdown_pct', 0.0):.2f}%"),
            ("Total Trades", str(metrics.get('total_trades', 0)), "Trade Expectancy", f"{metrics.get('expectancy_r', 0.0):+.2f} R"),
        ]

        table = doc.add_table(rows=1, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        headers = ["Metric", "Value", "Metric", "Value"]
        for idx, text in enumerate(headers):
            hdr_cells[idx].text = text
            hdr_cells[idx].paragraphs[0].runs[0].font.bold = True
            hdr_cells[idx].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
            shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="102C57"/>')
            hdr_cells[idx]._tc.get_or_add_tcPr().append(shading)

        for m1_label, m1_val, m2_label, m2_val in kpis:
            row_cells = table.add_row().cells
            row_cells[0].text = m1_label
            row_cells[1].text = m1_val
            row_cells[2].text = m2_label
            row_cells[3].text = m2_val
            for cell in row_cells:
                cell.paragraphs[0].runs[0].font.size = Pt(9.5)

        # Section 2: Narrative Synthesis
        if narrative_synthesis:
            h2 = doc.add_heading("2. Qualitative Market & Execution Synthesis", level=1)
            h2.paragraph_format.space_before = Pt(14)
            h2.paragraph_format.space_after = Pt(6)
            for paragraph_text in narrative_synthesis.split("\n\n"):
                if paragraph_text.strip():
                    p = doc.add_paragraph(paragraph_text.strip())
                    p.paragraph_format.space_after = Pt(6)
                    p.paragraph_format.line_spacing = 1.15

        # Section 3: Recommendations & Risk Governance
        if recommendations:
            h3 = doc.add_heading("3. Strategic Directives & Risk Governance", level=1)
            h3.paragraph_format.space_before = Pt(14)
            h3.paragraph_format.space_after = Pt(6)
            for rec in recommendations:
                bp = doc.add_paragraph(rec, style='List Bullet')
                bp.paragraph_format.space_after = Pt(3)

        # Section 4: Compliance & Disclaimer
        h4 = doc.add_heading("4. Operational Disclaimer", level=1)
        h4.paragraph_format.space_before = Pt(14)
        h4.paragraph_format.space_after = Pt(4)
        disc_p = doc.add_paragraph(
            "This report is algorithmically generated by the Monika Autonomous Trading Agent for research, "
            "evaluation, and portfolio supervision purposes only. Quantitative past performance is not guarantee of future return. "
            "All risk gates and hard drawdown limits are deterministically enforced."
        )
        disc_p.runs[0].font.size = Pt(8.5)
        disc_p.runs[0].font.italic = True
        disc_p.runs[0].font.color.rgb = RGBColor(120, 120, 120)

        # Save File
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"monika_performance_report_{timestamp}.docx"
        filepath = os.path.join(self.output_dir, filename)
        doc.save(filepath)
        logger.info(f"Docx report successfully saved to {filepath}")
        return os.path.abspath(filepath)
