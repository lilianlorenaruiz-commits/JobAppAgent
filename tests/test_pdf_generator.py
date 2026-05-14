"""
Tests de comportamiento del PDF Generator.
Verifica: archivo generado, nombre correcto, ≤ 2 páginas.
"""
import os
import pytest


JOB_GRUPO_RED = {
    "cargo":   "Trafficker Digital Senior Bilingüe",
    "empresa": "Grupo RED",
    "url":     "https://linkedin.com/jobs/dry-C-grupo-red",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama":    "C",
    "descripcion": (
        "Paid media Google Ads Meta Ads Amazon Ads LinkedIn Ads "
        "ROAS ACOS tROAS CTR CPC DPV NTB programmatic DSP AMC bilingual C2"
    ),
}

EXPECTED_PDF_NAME = "Lorena Ruiz - Trafficker Digital Senior Bilingüe - Grupo RED.pdf"


@pytest.fixture(scope="module")
def pdf_path(cv_text_grupo_red):
    from agents.pdf_generator import generate
    path = generate(cv_text_grupo_red, JOB_GRUPO_RED)
    return path


class TestPDFGenerator:
    """El PDF generado existe, tiene el nombre correcto y es ≤ 2 páginas."""

    def test_pdf_file_exists(self, pdf_path):
        assert os.path.exists(pdf_path), f"PDF no generado en: {pdf_path}"

    def test_pdf_filename_correct(self, pdf_path):
        name = os.path.basename(pdf_path)
        assert name == EXPECTED_PDF_NAME, (
            f"Nombre incorrecto: '{name}'\nEsperado: '{EXPECTED_PDF_NAME}'"
        )

    def test_pdf_is_not_empty(self, pdf_path):
        # ReportLab genera PDFs de texto compactos: rango real observado 2.6KB–10.7KB
        size = os.path.getsize(pdf_path)
        assert size > 2_000, f"PDF sospechosamente pequeño: {size} bytes"

    def test_pdf_max_two_pages(self, pdf_path):
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        pages = len(reader.pages)
        assert pages <= 2, (
            f"CV tiene {pages} páginas — debe caber en máximo 2 páginas A4"
        )

    def test_pdf_at_least_one_page(self, pdf_path):
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        assert len(reader.pages) >= 1


# ── Ciclo 11 RED→GREEN: Contenido del PDF ─────────────────────────────────────

@pytest.fixture(scope="module")
def pdf_text(pdf_path):
    """Extrae todo el texto del PDF para assertions de contenido."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestPDFContent:
    """El PDF contiene los datos clave que no deben perderse en el render."""

    def test_pdf_contains_candidate_name(self, pdf_text):
        assert "LORENA RUIZ" in pdf_text.upper(), (
            "Nombre 'LORENA RUIZ' no encontrado en el PDF extraído"
        )

    def test_pdf_contains_contact_email(self, pdf_text):
        assert "lilian@lorena-ruiz.com" in pdf_text, (
            "Email de contacto no encontrado en el PDF"
        )

    def test_pdf_contains_amazon_feb_2026(self, pdf_text):
        assert "Feb 2026" in pdf_text, (
            "Fecha Amazon 'Feb 2026' no encontrada en el PDF — posible regresión"
        )

    def test_pdf_contains_diploma_keyword(self, pdf_text):
        assert "Diploma" in pdf_text, (
            "Título 'Diploma' no encontrado en PDF — education section posiblemente ausente"
        )

    def test_pdf_size_reasonable(self, pdf_path):
        """PDF debe tener entre 5KB y 500KB — fuera de ese rango sugiere corrupción."""
        size = os.path.getsize(pdf_path)
        assert 5_000 <= size <= 500_000, (
            f"Tamaño del PDF fuera de rango razonable: {size} bytes"
        )
