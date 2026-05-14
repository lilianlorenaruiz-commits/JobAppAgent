"""
PDF Generator — Agente 4.5
CV de Lorena Ruiz — diseño monocromático profesional.

Layout (inspirado en template "White and Black Tech Professional Resume"):
  - Nombre grande bold centrado + subtítulo cargo + HR doble en header
  - Secciones: título bold uppercase + línea delgada debajo
  - Experiencia / Educación: cargo bold izquierda | fecha bold derecha (tabla 2 cols)
  - Skills: tabla 3 columnas
  - Bullets con hanging indent
  - Fuente Helvetica estándar — ATS-friendly
"""
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

BLACK = colors.black

_PAGE_W, _PAGE_H = A4
_MARGIN = 1.8 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN  # ~493 pt ≈ 17.4 cm

# ── Secciones conocidas ────────────────────────────────────────────────────────

_SECTIONS = {
    "PROFESSIONAL PROFILE", "WORK EXPERIENCE", "KEY ACHIEVEMENTS",
    "EDUCATION", "SKILLS", "LANGUAGES", "CERTIFICATIONS",
    "ADDITIONAL INFORMATION", "SUMMARY",
    "PERFIL PROFESIONAL", "EXPERIENCIA LABORAL", "EDUCACION",
    "HABILIDADES", "IDIOMAS", "LOGROS PRINCIPALES",
}
_EXP_SECS     = {"WORK EXPERIENCE", "EXPERIENCIA LABORAL"}
_EDU_SECS     = {"EDUCATION", "EDUCACION"}
_PROFILE_SECS = {"PROFESSIONAL PROFILE", "PERFIL PROFESIONAL", "SUMMARY"}
_SKILLS_SECS  = {"SKILLS", "HABILIDADES"}
_LANG_SECS    = {"LANGUAGES", "IDIOMAS"}

_DATE_RE = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(?:20|19)\d{2}"
    r"|(?:20|19)\d{2}\s*[-–]\s*(?:(?:20|19)\d{2}|current|present|presente|actual)",
    re.IGNORECASE,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_section(line: str) -> bool:
    return line.strip().upper() in _SECTIONS


def _has_date(line: str) -> bool:
    return bool(_DATE_RE.search(line))


def _is_bullet(line: str) -> bool:
    return bool(re.match(r"^\s*[•\-\*–·]\s", line))


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\s*[•\-\*–·]\s*", "", line).strip()


def _hr(space_after: int = 4) -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=BLACK, spaceAfter=space_after)


# ── Estilos ────────────────────────────────────────────────────────────────────

def _styles() -> dict:
    return {
        "name": ParagraphStyle("cv_name",
            fontName="Helvetica-Bold", fontSize=22, leading=26,
            alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("cv_subtitle",
            fontName="Helvetica-Bold", fontSize=11, leading=14,
            alignment=TA_CENTER, spaceAfter=6),
        "contact": ParagraphStyle("cv_contact",
            fontName="Helvetica", fontSize=9, leading=12,
            alignment=TA_CENTER, spaceBefore=5, spaceAfter=6),
        "profile": ParagraphStyle("cv_profile",
            fontName="Helvetica", fontSize=9, leading=13,
            alignment=TA_JUSTIFY, spaceAfter=4),
        "section_hdr": ParagraphStyle("cv_section_hdr",
            fontName="Helvetica-Bold", fontSize=10, leading=13,
            alignment=TA_LEFT, spaceBefore=10, spaceAfter=2),
        "role": ParagraphStyle("cv_role",
            fontName="Helvetica-Bold", fontSize=9, leading=12,
            alignment=TA_LEFT, spaceBefore=6, spaceAfter=0),
        "role_date": ParagraphStyle("cv_role_date",
            fontName="Helvetica-Bold", fontSize=9, leading=12,
            alignment=TA_RIGHT, spaceBefore=6, spaceAfter=0),
        "company": ParagraphStyle("cv_company",
            fontName="Helvetica", fontSize=9, leading=12,
            alignment=TA_LEFT, spaceAfter=2),
        "bullet": ParagraphStyle("cv_bullet",
            fontName="Helvetica", fontSize=9, leading=13,
            leftIndent=11, firstLineIndent=-7, spaceAfter=2),
        "body": ParagraphStyle("cv_body",
            fontName="Helvetica", fontSize=9, leading=13,
            alignment=TA_JUSTIFY, spaceAfter=3),
        "skills_item": ParagraphStyle("cv_skills_item",
            fontName="Helvetica", fontSize=9, leading=14, alignment=TA_LEFT),
    }


# ── Componentes de layout ──────────────────────────────────────────────────────

def _role_date_row(role: str, date_str: str, S: dict) -> Table:
    """Tabla 2 columnas: cargo bold izquierda | fecha bold derecha."""
    t = Table(
        [[Paragraph(_safe(role), S["role"]),
          Paragraph(_safe(date_str), S["role_date"])]],
        colWidths=[_CONTENT_W * 0.68, _CONTENT_W * 0.32],
    )
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _skills_grid(skills: list, S: dict) -> Table:
    """Tabla 3 columnas para skills/habilidades."""
    rows = []
    for i in range(0, len(skills), 3):
        chunk = skills[i:i+3]
        while len(chunk) < 3:
            chunk.append("")
        rows.append([Paragraph(_safe(s), S["skills_item"]) for s in chunk])
    cw = _CONTENT_W / 3
    t = Table(rows, colWidths=[cw, cw, cw])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


# ── Parser principal ───────────────────────────────────────────────────────────

def _build_flowables(cv_text: str, job: dict, S: dict) -> list:
    lines = [l.rstrip() for l in cv_text.split("\n")]
    n = len(lines)
    flowables = []
    i = 0
    section = None  # sección activa en uppercase

    # ── Saltar líneas vacías iniciales ─────────────────
    while i < n and not lines[i].strip():
        i += 1

    # ── Nombre (primera línea no vacía) ────────────────
    if i < n:
        flowables.append(Paragraph(_safe(lines[i].strip()), S["name"]))
        i += 1

    # ── Subtítulo: cargo del puesto objetivo ────────────
    cargo = job.get("cargo", "").strip()
    if cargo:
        flowables.append(Paragraph(_safe(cargo.upper()), S["subtitle"]))

    # ── HR tras bloque de nombre ────────────────────────
    flowables.append(_hr(space_after=0))

    # ── Línea de contacto (siguiente línea con | y @/+) ─
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if _is_section(line):
            break
        if "|" in line and ("@" in line or "+" in line or any(c.isdigit() for c in line)):
            flowables.append(Paragraph(_safe(line), S["contact"]))
            i += 1
            break
        i += 1

    # ── Segundo HR (cierra el header) ───────────────────
    flowables.append(_hr(space_after=6))

    # ── Cuerpo principal ────────────────────────────────
    while i < n:
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Header de sección
        if _is_section(line):
            section = line.strip().upper()
            flowables += [
                Paragraph(_safe(line.upper()), S["section_hdr"]),
                _hr(space_after=4),
            ]
            i += 1
            continue

        up = section or ""

        # ── Perfil profesional ──────────────────────────
        if up in _PROFILE_SECS:
            flowables.append(Paragraph(_safe(line), S["profile"]))
            i += 1
            continue

        # ── Skills: tabla 3 columnas ────────────────────
        if up in _SKILLS_SECS:
            skills = [s.strip() for s in re.split(r"[,|]", line) if s.strip()]
            if skills:
                flowables.append(_skills_grid(skills, S))
            i += 1
            continue

        # ── Idiomas: bullet por idioma ──────────────────
        if up in _LANG_SECS:
            parts = [p.strip() for p in re.split(r"\|", line) if p.strip()]
            for p in parts:
                flowables.append(Paragraph("• " + _safe(p), S["bullet"]))
            i += 1
            continue

        # ── Experiencia / Educación ─────────────────────
        if up in (_EXP_SECS | _EDU_SECS):
            if _is_bullet(line):
                flowables.append(Paragraph("• " + _safe(_strip_bullet(line)), S["bullet"]))
                i += 1
                continue

            # Lookahead: buscar fecha en las próximas 3 líneas
            role_title = line
            company    = ""
            date_str   = ""
            j = i + 1

            for look in range(3):
                if j >= n:
                    break
                ahead = lines[j].strip()
                if not ahead or _is_section(ahead) or _is_bullet(ahead):
                    break
                if _has_date(ahead):
                    date_str = ahead
                    if look >= 1:
                        company = lines[i + 1].strip()
                    j += 1
                    break
                j += 1

            if date_str:
                flowables.append(_role_date_row(role_title, date_str, S))
                if company:
                    flowables.append(Paragraph(_safe(company), S["company"]))
                i = j
            else:
                flowables.append(Paragraph(_safe(line), S["body"]))
                i += 1
            continue

        # ── Contenido genérico (KEY ACHIEVEMENTS, etc.) ─
        if _is_bullet(line):
            flowables.append(Paragraph("• " + _safe(_strip_bullet(line)), S["bullet"]))
        else:
            flowables.append(Paragraph(_safe(line), S["body"]))
        i += 1

    return flowables


# ── Nombre de archivo ──────────────────────────────────────────────────────────

def _safe_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", s).strip()


def _output_path(cargo: str, empresa: str) -> str:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    filename = f"Lorena Ruiz - {_safe_filename(cargo)} - {_safe_filename(empresa)}.pdf"
    return os.path.join(config.OUTPUT_DIR, filename)


# ── API pública ────────────────────────────────────────────────────────────────

def generate(cv_text: str, job: dict) -> str:
    """
    Genera el PDF del CV con diseño profesional monocromático.

    Args:
        cv_text: texto plano del CV (output de cv_rewriter.rewrite)
        job:     dict con "cargo" y "empresa"

    Returns:
        Ruta absoluta del PDF generado.
    """
    path = _output_path(job["cargo"], job.get("empresa", "empresa"))
    S    = _styles()

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f"Lorena Ruiz — {job['cargo']}",
        author="Lorena Ruiz",
    )

    doc.build(_build_flowables(cv_text, job, S))
    print(f"[PDFGenerator] PDF guardado: {path}")
    return path


# ── CLI: test visual ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample = """LORENA RUIZ

Bogota D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884

PROFESSIONAL PROFILE
Performance Marketing professional with 14+ years in marketing and digital strategy, including hands-on paid media campaign management across Google Ads, Meta Ads, Amazon Ads, and LinkedIn Ads. Expertise in ROAS and ACOS optimization, programmatic advertising, and data analysis. Fully bilingual Spanish/English (C2 Proficient, EF SET certified).

WORK EXPERIENCE

Paid Media Specialist / Account Manager - LinkedIn Ads (via Teleperformance for LinkedIn Marketing Solutions)
Teleperformance (contract for LinkedIn Marketing Solutions)
February 2026 - Present  |  Bogota, Hybrid
- Manage and optimize LinkedIn Ads campaigns for 300+ B2B enterprise accounts across Latin America with a monthly portfolio of USD 240,000.
- Conduct weekly performance reviews and deliver optimization recommendations in English to Global Account Executives in Singapore, Sydney, and Tokyo.
- Execute Sponsored Content, Lead Gen Forms, and Website Conversion objectives, achieving CPC of USD 0.96 in highly specialized B2B audiences.

Campaign Planner Contractor
Amazon, Colombia
May 2025 - Present  |  Bogota
- Managed Amazon DSP programmatic campaigns for APAC premium brands (Midea, Narwal, Bedsure, Jackery) supporting 4 Global Account Executives.
- Improved Narwal tROAS from 1.28x to 3.28x generating USD 100,000 in attributed sales in 30 days via remarketing optimization and video creative refresh.
- Achieved #1 position for Modelones in Nail Polish category Q3-Q4 2025 on Amazon APAC through Market Research and DSP strategy.

National Marketing Manager
Alcalisa S.A., Quito, Ecuador
November 2013 - November 2018
- Grew company revenue from USD 1.5M to USD 3.0M in 4 years (+100%) leading brand strategy, trade marketing, and digital channel migration.
- Increased brand awareness from 18% to 34% (+16 p.p.) migrating budget from traditional media to digital after Ecuador's Ley de Comunicacion prohibition.
- Grew market share from 12% to 18% (+6 p.p.) ascending to 2nd largest company in Ecuador's national spirits segment.

EDUCATION

Master's in Marketing and Commercial Management
Real Centro Universitario Maria Cristina - Escuela Europea, Madrid, Spain
2010 - 2012

Bachelor's in Social Communication and Journalism
Universidad del Valle, Cali, Colombia
2005 - 2009

SKILLS
Google Ads, Meta Ads, Amazon Ads, LinkedIn Ads, Amazon DSP, Programmatic Advertising, ROAS Optimization, ACOS Optimization, Performance Marketing, Data Analysis, Campaign Management, Budget Management, Tableau, Power BI, Amazon Marketing Cloud

LANGUAGES
Spanish: Native (100%) | English: C2 Proficient (EF SET certified, 73/100, October 2025)
"""

    test_job = {"cargo": "Paid Media Manager", "empresa": "Test Company"}
    path = generate(sample, test_job)
    print(f"\nPDF generado en: {path}")
    print("Abre el archivo para revisar el diseño.")
