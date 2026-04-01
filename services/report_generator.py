"""
services/report_generator.py - Pest control report generator

Generates both structured JSON and PDF reports from analysis results.
Priority rule: user knowledge (High) > literature (Low)
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)

# PDF font path - uses built-in fonts (no Korean support needed for PDF)
# Korean text is handled via UTF-8 JSON response


@dataclass
class ReportSection:
    title: str
    items: list[str] = field(default_factory=list)


@dataclass
class FullReport:
    """Structured report data - used for both JSON and PDF output"""
    report_id: int
    created_at: str

    # Pest info
    pest_name_ko: str
    pest_confidence: float
    pest_candidates: list[dict]

    # Habitat info
    detected_habitats: list[dict]

    # Actions (3 levels)
    immediate_actions: list[str]       # Do right now
    short_term_actions: list[str]      # Within 1 week
    long_term_actions: list[str]       # Within 1 month

    # User knowledge applied
    applied_knowledge: list[dict]

    # Summary
    summary_text: str
    risk_level: str                    # LOW / MEDIUM / HIGH / CRITICAL
    is_low_confidence: bool


class ReportGenerator:
    """
    Converts AnalysisReport DB record into FullReport
    and renders it as JSON dict or PDF bytes.
    """

    def build(self, report) -> FullReport:
        """
        Build FullReport from AnalysisReport ORM object.
        Called after analysis is complete (status == completed).
        """
        risk_level = self._calc_risk_level(
            habitats=report.detected_habitats or [],
            confidence=report.pest_confidence or 0.0,
        )

        return FullReport(
            report_id=report.id,
            created_at=report.completed_at.strftime("%Y-%m-%d %H:%M")
            if report.completed_at else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            pest_name_ko=report.pest_id and report.pest.name_ko if hasattr(report, "pest") and report.pest else "",
            pest_confidence=report.pest_confidence or 0.0,
            pest_candidates=report.pest_candidates or [],
            detected_habitats=report.detected_habitats or [],
            immediate_actions=report.immediate_actions or [],
            short_term_actions=report.short_term_actions or [],
            long_term_actions=report.long_term_actions or [],
            applied_knowledge=report.applied_knowledge or [],
            summary_text=report.summary_text or "",
            risk_level=risk_level,
            is_low_confidence=report.is_low_confidence or False,
        )

    def to_dict(self, full_report: FullReport) -> dict:
        """Export FullReport as JSON-serializable dict"""
        return {
            "report_id": full_report.report_id,
            "created_at": full_report.created_at,
            "status": "low_confidence" if full_report.is_low_confidence else "completed",
            "risk_level": full_report.risk_level,
            "pest": {
                "name_ko": full_report.pest_name_ko,
                "confidence": full_report.pest_confidence,
                "confidence_pct": f"{full_report.pest_confidence:.0%}",
                "candidates": full_report.pest_candidates,
            },
            "habitats": full_report.detected_habitats,
            "actions": {
                "immediate": full_report.immediate_actions,
                "short_term": full_report.short_term_actions,
                "long_term": full_report.long_term_actions,
            },
            "applied_knowledge_count": len(full_report.applied_knowledge),
            "applied_knowledge": full_report.applied_knowledge,
            "summary": full_report.summary_text,
        }

    def to_pdf(self, full_report: FullReport, pest_obj=None) -> bytes:
        """
        Render FullReport as PDF bytes.
        Uses FPDF2 with built-in Latin fonts.
        Korean characters are transliterated to English labels.
        """
        pdf = _FlyAnalyzerPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # ── Cover ──────────────────────────────────────────
        pdf.cover_section(full_report)

        # ── Risk Badge ────────────────────────────────────
        pdf.risk_badge(full_report.risk_level)

        # ── Pest Result ───────────────────────────────────
        pdf.section_header("1. Pest Identification")

        pest_display = full_report.pest_name_ko or "Unknown"
        conf_pct = f"{full_report.pest_confidence:.0%}"

        pdf.key_value("Identified Species", f"{pest_display}  (confidence: {conf_pct})")

        if full_report.is_low_confidence:
            pdf.warning_box("Low confidence result. Please retake the photo for accuracy.")

        if full_report.pest_candidates:
            pdf.sub_header("Candidate Species")
            for c in full_report.pest_candidates[:3]:
                name = c.get("name_ko", c.get("name", "?"))
                score = c.get("score", c.get("confidence", 0))
                pdf.bullet_item(f"{name}  ({score:.0%})")

        if pest_obj:
            pdf.sub_header("Species Characteristics")
            if pest_obj.body_size_mm_min and pest_obj.body_size_mm_max:
                pdf.key_value("Body size", f"{pest_obj.body_size_mm_min}~{pest_obj.body_size_mm_max} mm")
            if pest_obj.active_season:
                pdf.key_value("Active season", pest_obj.active_season)
            if pest_obj.lifecycle_days:
                pdf.key_value("Lifecycle", f"{pest_obj.lifecycle_days} days (egg to adult)")

        # ── Habitats ──────────────────────────────────────
        pdf.section_header("2. Detected Contamination Sources")

        if full_report.detected_habitats:
            for h in full_report.detected_habitats:
                name = h.get("name_ko", "Unknown")
                conf = h.get("confidence", 0)
                pdf.bullet_item(f"{name}  (detection: {conf:.0%})")
        else:
            pdf.normal_text("No contamination sources detected in image.")

        # ── Action Plan ───────────────────────────────────
        pdf.section_header("3. Pest Control Action Plan")

        if full_report.applied_knowledge:
            pdf.info_box(
                f"* Field-verified knowledge applied: {len(full_report.applied_knowledge)} item(s)\n"
                "  (User-input data takes priority over literature)"
            )

        pdf.sub_header("Immediate Actions (Do Now)")
        if full_report.immediate_actions:
            for a in full_report.immediate_actions:
                pdf.bullet_item(a)
        else:
            pdf.normal_text("No immediate actions required.")

        pdf.sub_header("Short-term Actions (Within 1 Week)")
        if full_report.short_term_actions:
            for a in full_report.short_term_actions:
                pdf.bullet_item(a)

        pdf.sub_header("Long-term Actions (Within 1 Month)")
        if full_report.long_term_actions:
            for a in full_report.long_term_actions:
                pdf.bullet_item(a)

        # ── Applied Knowledge ─────────────────────────────
        if full_report.applied_knowledge:
            pdf.section_header("4. Field Expert Knowledge Applied")
            pdf.info_box("The following user-input knowledge was prioritized in this report.")
            for k in full_report.applied_knowledge:
                title = k.get("title", "")
                ktype = k.get("knowledge_type", "")
                rel = k.get("relevance", 0)
                conf = k.get("confidence", 1.0)
                pdf.bullet_item(
                    f"[{ktype.upper()}] {title}  "
                    f"(relevance: {rel:.0%}, confidence: {conf:.0%})"
                )

        # ── Footer note ───────────────────────────────────
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.multi_cell(
            0, 5,
            "Generated by Fly Analyzer | "
            "User-input field knowledge takes priority over literature data.",
        )

        return bytes(pdf.output())

    # ── Internal helpers ──────────────────────────────────

    def _calc_risk_level(self, habitats: list[dict], confidence: float) -> str:
        """
        Risk level based on habitat count and confidence.
        CRITICAL > HIGH > MEDIUM > LOW
        """
        if not habitats:
            return "LOW"

        max_risk = max((h.get("confidence", 0) for h in habitats), default=0)
        count = len(habitats)

        if count >= 3 or max_risk >= 0.9:
            return "CRITICAL"
        if count >= 2 or max_risk >= 0.7:
            return "HIGH"
        if count >= 1 or confidence >= 0.6:
            return "MEDIUM"
        return "LOW"


# ── PDF renderer class ──────────────────────────────────────────────────────

RISK_COLORS = {
    "LOW":      (39,  174, 96),
    "MEDIUM":   (241, 196, 15),
    "HIGH":     (230, 126, 34),
    "CRITICAL": (192, 57,  43),
}

LM = 15  # left margin
RM = 15  # right margin


class _FlyAnalyzerPDF(FPDF):
    """Custom PDF - always resets x to left margin before drawing"""

    def _x(self):
        """Always draw from left margin"""
        self.set_x(LM)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(150, 150, 150)
        self.set_x(LM)
        self.cell(0, 8, "Fly Analyzer - Pest Control Report", align="R")
        self.ln(4)
        self.set_draw_color(220, 220, 220)
        self.line(LM, self.get_y(), 200 - RM, self.get_y())
        self.ln(4)
        self.set_text_color(30, 30, 30)
        self.set_draw_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def cover_section(self, r: "FullReport"):
        self._x()
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(30, 30, 30)
        self.cell(0, 12, "Pest Control Report", ln=True, align="C")
        self._x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, f"Report ID: #{r.report_id}    Date: {r.created_at}", ln=True, align="C")
        self.ln(6)
        self.set_draw_color(52, 152, 219)
        self.set_line_width(0.8)
        self.line(LM, self.get_y(), 200 - RM, self.get_y())
        self.set_line_width(0.2)
        self.set_draw_color(0, 0, 0)
        self.ln(8)
        self.set_text_color(30, 30, 30)

    def risk_badge(self, level: str):
        r, g, b = RISK_COLORS.get(level, (100, 100, 100))
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 13)
        self._x()
        self.cell(0, 10, f"  Risk Level: {level}", ln=True, fill=True)
        self.ln(6)
        self.set_text_color(30, 30, 30)
        self.set_fill_color(255, 255, 255)

    def section_header(self, text: str):
        self.ln(4)
        self.set_fill_color(52, 73, 94)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self._x()
        self.cell(0, 9, f"  {text}", ln=True, fill=True)
        self.ln(3)
        self.set_text_color(30, 30, 30)
        self.set_fill_color(255, 255, 255)

    def sub_header(self, text: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(52, 73, 94)
        self._x()
        self.cell(0, 7, text, ln=True)
        self.set_text_color(30, 30, 30)

    def key_value(self, key: str, value: str):
        self._x()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(50, 7, key + ":")
        self.set_font("Helvetica", "", 10)
        w = self.epw - 50
        self.multi_cell(w, 7, value)

    def bullet_item(self, text: str):
        self._x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, f"  - {text}")

    def normal_text(self, text: str):
        self._x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, text)

    def warning_box(self, text: str):
        self._x()
        self.set_fill_color(253, 245, 230)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(130, 60, 0)
        self.multi_cell(0, 6, f"  [!] {text}", fill=True)
        self.ln(2)
        self.set_text_color(30, 30, 30)
        self.set_fill_color(255, 255, 255)

    def info_box(self, text: str):
        self._x()
        self.set_fill_color(235, 245, 255)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 90, 150)
        self.multi_cell(0, 6, text, fill=True)
        self.ln(2)
        self.set_text_color(30, 30, 30)
        self.set_fill_color(255, 255, 255)


# Singleton
report_generator = ReportGenerator()