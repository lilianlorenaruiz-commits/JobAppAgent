"""
PDF Generator — entre Agente 4 y Agente 5
Convierte el CV reescrito (texto plano) a un PDF ATS-friendly.
Nombre de archivo: Lorena Ruiz - [cargo] - [empresa].pdf
Destino: output/cv_optimizados/

ATS-friendly: fuente estándar, sin columnas, sin gráficos, sin headers/footers especiales.
"""
import os
import re
import sys
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Estilos ────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "name",
            fontName="Helvetica-Bold",
            fontSize=16,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "contact": ParagraphStyle(
            "contact",
            fontName="Helvetica",
            fontSize=9,
            spaceAfter=10,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold",
            fontSize=11,
            spaceBefore=10,
            spaceAfter=3,
            textTransform="uppercase",
        ),
        "job_title": ParagraphStyle(
            "job_title",
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=6,
            spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=2,
        ),
        "body_italic": ParagraphStyle(
            "body_italic",
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            spaceAfter=2,
        ),
    }


# ── Conversión texto → Paragraphs ──────────────────────────────────────────────

_SECTION_HEADERS = {
    "PROFESSIONAL PROFILE", "WORK EXPERIENCE", "EDUCATION",
    "SKILLS", "LANGUAGES", "CERTIFICATIONS", "SUMMARY",
    "PERFIL PROFESIONAL", "EXPERIENCIA LABORAL", "EDUCACION",
    "HABILIDADES", "IDIOMAS",
}

_DATE_RE = re.compile(
    r"(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December|Novembe)"
    r"\s+\d{4}",
    re.IGNORECASE,
)


def _text_to_flowables(cv_text: str, styles: dict) -> list:
    flowables = []
    lines = cv_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # Nombre (primera línea)
        if i == 0:
            flowables.append(Paragraph(line, styles["name"]))
            i += 1
            continue

        # Línea de contacto (segunda línea)
        if i == 1:
            flowables.append(Paragraph(line, styles["contact"]))
            i += 1
            continue

        # Headers de sección (TODO CAPS y en lista conocida)
        if line.upper() in _SECTION_HEADERS or (
            line.isupper() and 4 < len(line) < 40
        ):
            flowables.append(Paragraph(line, styles["section"]))
            i += 1
            continue

        # Línea de fecha (empresa o periodo)
        if _DATE_RE.search(line):
            flowables.append(Paragraph(line, styles["body_italic"]))
            i += 1
            continue

        # Línea que parece título de cargo (MAYÚSCULAS o Title Case corto)
        if (
            line.isupper()
            and len(line) > 4
            and not line.upper() in _SECTION_HEADERS
        ):
            flowables.append(Paragraph(line, styles["job_title"]))
            i += 1
            continue

        # Texto normal
        # Escape special ReportLab characters
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        flowables.append(Paragraph(safe, styles["body"]))
        i += 1

    return flowables


# ── Nombre del archivo ─────────────────────────────────────────────────────────

def _safe_filename(s: str) -> str:
    """Elimina caracteres inválidos para nombres de archivo."""
    return re.sub(r'[\\/:*?"<>|]', "", s).strip()


def _output_path(cargo: str, empresa: str) -> str:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    filename = f"Lorena Ruiz - {_safe_filename(cargo)} - {_safe_filename(empresa)}.pdf"
    return os.path.join(config.OUTPUT_DIR, filename)


# ── API pública ────────────────────────────────────────────────────────────────

def generate(cv_text: str, job: dict) -> str:
    """
    Genera el PDF ATS-friendly del CV reescrito.

    Args:
        cv_text: texto plano del CV (output de cv_rewriter.rewrite)
        job:     dict con "cargo" y "empresa"

    Returns:
        Ruta absoluta del PDF generado.
    """
    path   = _output_path(job["cargo"], job.get("empresa", "empresa"))
    styles = _build_styles()

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Lorena Ruiz — {job['cargo']}",
        author="Lorena Ruiz",
    )

    flowables = _text_to_flowables(cv_text, styles)
    doc.build(flowables)
    print(f"[PDFGenerator] PDF guardado: {path}")
    return path


if __name__ == "__main__":
    # Prueba rápida con texto plano de muestra
    sample_text = """LORENA RUIZ
Bogota D.C. | lilianlorena.ruiz@gmail.com | +57 315 256 1884

PROFESSIONAL PROFILE
Senior Brand Strategist with 20+ years of experience in brand strategy, digital transformation,
and B2B/B2C commercial management. Fully bilingual Spanish/English C1.

WORK EXPERIENCE

CAMPAIGN PLANNER CONTRACTOR
AMAZON, COLOMBIA
May 2025 - current working
Campaign Management: Set up and optimized Amazon Ads campaigns across APAC markets.
Data Analysis: Translated performance data into insights to optimize budgets and ROAS.

EDUCATION

MASTER IN MARKETING AND COMMERCIAL MANAGEMENT
Real Centro Universitario Maria Cristina, Madrid, Spain

SKILLS
Brand Strategy, Digital Transformation, Data Analysis, Trade Marketing, Amazon Ads

LANGUAGES
Spanish: 100% | English: 90% (C1)
"""
    test_job = {"cargo": "Brand Strategist Sr.", "empresa": "Grupo Exito Demo"}
    pdf_path = generate(sample_text, test_job)
    print(f"PDF generado en: {pdf_path}")
