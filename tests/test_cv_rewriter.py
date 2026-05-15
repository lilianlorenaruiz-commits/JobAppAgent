"""
Tests de comportamiento del CV Rewriter.
Verifica mediante la interfaz pública (texto del CV generado), no internals.

Ciclos RED-GREEN:
  1. LinkedIn section no tiene Global AEs APAC
  2. Funnel format / 30% review time aparece en Amazon, no en LinkedIn
  3. LinkedIn section solo tiene Latin America
  4. Datos Amazon correctamente atribuidos (tROAS, APAC, marcas)
  5. Contacto: email correcto, sin URL de LinkedIn
  6. Amazon date es Present, no fecha inventada
  7. Education incluye fechas de los 4 títulos
"""
import re
import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_section(cv_text: str, employer_marker: str, next_markers: list[str]) -> str:
    """
    Extrae el bloque de texto de un rol dado su empresa/cargo.
    Busca desde el primer `employer_marker` hasta el primero de `next_markers`.
    """
    start = cv_text.find(employer_marker)
    if start == -1:
        return ""
    end = len(cv_text)
    for marker in next_markers:
        idx = cv_text.find(marker, start + len(employer_marker))
        if idx != -1 and idx < end:
            end = idx
    return cv_text[start:end]


def _linkedin_section(cv_text: str) -> str:
    return _extract_section(
        cv_text,
        employer_marker="Teleperformance",
        next_markers=["Amazon", "Avanti", "Alcalisa", "GRC"],
    )


def _amazon_section(cv_text: str) -> str:
    # "Amazon, Colombia" es el marcador de la empresa en WORK EXPERIENCE
    # Evita matchear "Amazon Ads" que aparece en el perfil
    return _extract_section(
        cv_text,
        employer_marker="Amazon, Colombia",
        next_markers=["Avanti", "Alcalisa", "GRC", "EDUCATION"],
    )


def _education_section(cv_text: str) -> str:
    # _fix_static_fields normalizes the header to "EDUCATION", but try variants as fallback.
    for marker in ("EDUCATION", "ACADEMIC BACKGROUND", "ACADEMIC TRAINING", "ACADEMIC"):
        section = _extract_section(cv_text, marker, ["SKILLS", "LANGUAGES"])
        if section:
            return section
    # Last-resort fallback: education is always at the end — use last 1400 chars
    return cv_text[-1400:] if len(cv_text) > 1400 else cv_text


# ── Ciclo 1 RED→GREEN: LinkedIn no tiene AEs APAC ─────────────────────────────

class TestLinkedInSectionPurity:
    """La sección LinkedIn/Teleperformance no debe contener datos APAC ni AEs Amazon."""

    def test_linkedin_no_singapore(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert section, "No se encontró sección de Teleperformance/LinkedIn en el CV"
        assert "Singapore" not in section, (
            "CONTAMINACIÓN: 'Singapore' apareció en la sección LinkedIn.\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_no_sydney(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "Sydney" not in section, (
            "CONTAMINACIÓN: 'Sydney' apareció en la sección LinkedIn.\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_no_tokyo(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "Tokyo" not in section, (
            "CONTAMINACIÓN: 'Tokyo' apareció en la sección LinkedIn.\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_no_apac(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "APAC" not in section, (
            "CONTAMINACIÓN: 'APAC' apareció en la sección LinkedIn (debe ser Latin America).\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_no_global_account_executives(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "Global Account Executive" not in section, (
            "CONTAMINACIÓN: 'Global Account Executives' (Amazon) apareció en sección LinkedIn.\n"
            f"Sección:\n{section}"
        )


# ── Ciclo 2 RED→GREEN: Funnel format en Amazon, no en LinkedIn ─────────────────

class TestFunnelFormatAttribution:
    """El logro del funnel format (30% review time) pertenece a Amazon, no a LinkedIn."""

    def test_funnel_format_not_in_linkedin(self, cv_text_grupo_red):
        linkedin = _linkedin_section(cv_text_grupo_red)
        has_funnel = any(
            kw in linkedin
            for kw in ["funnel-based reporting", "funnel format", "30 percent", "review time"]
        )
        assert not has_funnel, (
            "CONTAMINACIÓN: logro del funnel format (Amazon) apareció en sección LinkedIn.\n"
            f"Sección LinkedIn:\n{linkedin}"
        )

    def test_funnel_format_in_amazon(self, cv_text_grupo_red):
        amazon = _amazon_section(cv_text_grupo_red)
        assert amazon, "No se encontró sección de Amazon en el CV"
        has_funnel = any(
            kw in amazon
            for kw in ["funnel", "reporting format", "review time", "30 percent", "CPC Team"]
        )
        assert has_funnel, (
            "El logro del funnel format / 30% review time no aparece en la sección Amazon.\n"
            f"Sección Amazon:\n{amazon}"
        )


# ── Ciclo 3 RED→GREEN: LinkedIn tiene datos correctos ─────────────────────────

class TestLinkedInCorrectData:
    """La sección LinkedIn debe tener Latin America y datos reales de ThinkOnward."""

    def test_linkedin_has_latin_america(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        # El CV puede redactarse en inglés ("Latin America"/"LATAM") o en español
        # ("América Latina"/"Latinoamérica") según el idioma del JD detectado (BUG-B fix).
        has_region = any(
            kw.lower() in section.lower()
            for kw in ["latin america", "latam", "américa latina",
                        "america latina", "latinoamérica", "latinoamerica"]
        )
        assert has_region, (
            "La sección LinkedIn no menciona Latin America ni América Latina.\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_has_portfolio_usd(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "240" in section, (
            "La sección LinkedIn no menciona el portfolio de USD 240,000.\n"
            f"Sección:\n{section}"
        )

    def test_linkedin_has_300_accounts(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "300" in section, (
            "La sección LinkedIn no menciona las 300 cuentas B2B.\n"
            f"Sección:\n{section}"
        )


# ── Ciclo 4 RED→GREEN: Amazon tiene datos APAC correctos ──────────────────────

class TestAmazonSectionCorrectData:
    """La sección Amazon debe tener datos APAC reales: tROAS, Narwal, APAC."""

    def test_amazon_has_troas(self, cv_text_grupo_red):
        section = _amazon_section(cv_text_grupo_red)
        assert "tROAS" in section or "ROAS" in section, (
            "La sección Amazon no tiene datos de tROAS.\n"
            f"Sección:\n{section}"
        )

    def test_amazon_has_narwal(self, cv_text_grupo_red):
        section = _amazon_section(cv_text_grupo_red)
        assert "Narwal" in section, (
            "La sección Amazon no tiene el caso Narwal.\n"
            f"Sección:\n{section}"
        )

    def test_amazon_has_apac(self, cv_text_grupo_red):
        section = _amazon_section(cv_text_grupo_red)
        assert "APAC" in section, (
            "La sección Amazon no menciona APAC.\n"
            f"Sección:\n{section}"
        )

    def test_amazon_date_is_feb_2026(self, cv_text_grupo_red):
        """El rol Amazon terminó en Feb 2026 — su end date DEBE ser 'Feb 2026', nunca 'Present'."""
        section = _amazon_section(cv_text_grupo_red)
        assert "Feb 2026" in section, (
            "La sección Amazon no muestra 'Feb 2026' como end date.\n"
            f"Sección:\n{section[:300]}"
        )
        assert "Present" not in section, (
            "FECHA INCORRECTA: 'Present' apareció en la sección Amazon (el rol ya terminó).\n"
            f"Sección:\n{section[:300]}"
        )

    def test_amazon_no_latin_america(self, cv_text_grupo_red):
        section = _amazon_section(cv_text_grupo_red)
        assert "Latin America" not in section, (
            "CONTAMINACIÓN inversa: 'Latin America' (LinkedIn) apareció en sección Amazon.\n"
            f"Sección:\n{section}"
        )


# ── Ciclo 5 RED→GREEN: Contacto correcto ──────────────────────────────────────

class TestContactInfo:
    """La línea de contacto debe ser exactamente la provista — el LLM no puede modificarla."""

    def test_contact_has_correct_email(self, cv_text_grupo_red):
        assert "lilian@lorena-ruiz.com" in cv_text_grupo_red, (
            "CONTACTO INCORRECTO: el LLM cambió 'lilian@lorena-ruiz.com'.\n"
            f"Primeras 400 chars:\n{cv_text_grupo_red[:400]}"
        )

    def test_contact_has_linkedin_url(self, cv_text_grupo_red):
        assert "linkedin.com/in/lilianlorenaruiz" in cv_text_grupo_red, (
            "CONTACTO INCOMPLETO: falta 'www.linkedin.com/in/lilianlorenaruiz' en la línea de contacto.\n"
            f"Primeras 400 chars:\n{cv_text_grupo_red[:400]}"
        )


# ── Ciclo 6 RED→GREEN: Education tiene fechas ──────────────────────────────────

class TestEducationDates:
    """La sección EDUCATION debe incluir fechas de los 4 títulos."""

    def test_education_has_ai_diploma_year(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "2023" in edu, (
            "EDUCATION no incluye el año 2023 (Diploma en IA, Universidad del Valle).\n"
            f"Sección:\n{edu}"
        )

    def test_education_has_masters_year(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "2012" in edu, (
            "EDUCATION no incluye 2012 (Master, Real Centro Universitario 2011–2012).\n"
            f"Sección:\n{edu}"
        )

    def test_education_has_bachelors_start_year(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "2005" in edu, (
            "EDUCATION no incluye el año de inicio del Bachelor (2005–2011).\n"
            f"Sección:\n{edu}"
        )


# ── Ciclo 8 RED→GREEN: Educación — títulos exactos ────────────────────────────

class TestEducationExactTitles:
    """
    Los 4 títulos de grado deben aparecer EXACTAMENTE como los especificó Lorena.
    El bug previo: el parse del PDF corrompía 'DIPLOMA IN IA' y fusionaba
    el título del Certificate con la institución en una misma línea.
    La solución (hardcode en _fix_static_fields) es inmune a lo que haga el LLM.
    """

    def test_diploma_title_exact(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "Diploma in AI and Community Management" in edu, (
            "EDUCATION no tiene el título correcto del Diploma.\n"
            f"Sección:\n{edu}"
        )

    def test_certificate_title_exact(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "Advanced Certificate in Retail and Trade Marketing" in edu, (
            "EDUCATION no tiene el título correcto del Certificate.\n"
            f"Sección:\n{edu}"
        )

    def test_masters_title_exact(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "Master's in Marketing and Commercial Management" in edu, (
            "EDUCATION no tiene el título correcto del Master's.\n"
            f"Sección:\n{edu}"
        )

    def test_bachelors_title_exact(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        assert "Bachelor's in Social Communication and Journalism" in edu, (
            "EDUCATION no tiene el título correcto del Bachelor's.\n"
            f"Sección:\n{edu}"
        )

    def test_no_corrupted_diploma(self, cv_text_grupo_red):
        """El PDF parse generaba 'DIPLOMA IN IA' (garbled) — no debe aparecer."""
        edu = _education_section(cv_text_grupo_red)
        assert "DIPLOMA IN IA AND COMMUNITY" not in edu, (
            "CONTAMINACIÓN: aparece el título corrupto del PDF parse.\n"
            f"Sección:\n{edu}"
        )

    def test_certificate_title_not_merged_with_institution(self, cv_text_grupo_red):
        """El PDF parse fusionaba título Certificate + 'EDES Business School, Retail' en una línea."""
        edu = _education_section(cv_text_grupo_red)
        for line in edu.split("\n"):
            if "Certificate" in line and "EDES" in line:
                pytest.fail(
                    f"Título del Certificate está fusionado con la institución:\n'{line}'"
                )

    def test_all_four_institutions_present(self, cv_text_grupo_red):
        edu = _education_section(cv_text_grupo_red)
        for inst in ("Universidad del Valle", "EDES Business School", "Real Centro Universitario"):
            assert inst in edu, (
                f"Institución '{inst}' no encontrada en EDUCATION.\n"
                f"Sección:\n{edu}"
            )


# ── Ciclo 9 RED→GREEN: Rol LinkedIn — fecha y estado ─────────────────────────

class TestLinkedInRoleDate:
    """El rol LinkedIn/Teleperformance (el más reciente) debe tener fecha 'February 2026 – Present'."""

    def test_linkedin_year_2026_present(self, cv_text_grupo_red):
        section = _linkedin_section(cv_text_grupo_red)
        assert "2026" in section, (
            "La sección LinkedIn no menciona el año 2026 (inicio Feb 2026).\n"
            f"Sección:\n{section[:400]}"
        )

    def test_linkedin_is_current_role(self, cv_text_grupo_red):
        """El rol LinkedIn es el actual — debe mostrar 'Present'."""
        section = _linkedin_section(cv_text_grupo_red)
        assert "Present" in section, (
            "La sección LinkedIn no muestra 'Present' (es el rol activo).\n"
            f"Sección:\n{section[:400]}"
        )


# ── Ciclo 10 RED→GREEN: Estructura del CV — secciones estándar ────────────────

class TestCVSectionStructure:
    """El CV generado contiene las 5 secciones estándar en el texto plano."""

    def test_professional_profile_present(self, cv_text_grupo_red):
        assert "PROFESSIONAL PROFILE" in cv_text_grupo_red.upper(), (
            "Falta sección PROFESSIONAL PROFILE"
        )

    def test_work_experience_present(self, cv_text_grupo_red):
        assert "WORK EXPERIENCE" in cv_text_grupo_red.upper(), (
            "Falta sección WORK EXPERIENCE"
        )

    def test_education_section_present(self, cv_text_grupo_red):
        assert "EDUCATION" in cv_text_grupo_red.upper(), (
            "Falta sección EDUCATION"
        )

    def test_skills_section_present(self, cv_text_grupo_red):
        assert "SKILLS" in cv_text_grupo_red.upper(), (
            "Falta sección SKILLS"
        )

    def test_languages_section_present(self, cv_text_grupo_red):
        assert "LANGUAGES" in cv_text_grupo_red.upper(), (
            "Falta sección LANGUAGES"
        )

    def test_candidate_name_present(self, cv_text_grupo_red):
        assert "LORENA RUIZ" in cv_text_grupo_red.upper(), (
            "Nombre 'LORENA RUIZ' no encontrado en el CV"
        )

    def test_five_employers_present(self, cv_text_grupo_red):
        """Los 5 empleadores deben estar presentes en el CV."""
        for employer in ("Teleperformance", "Amazon", "Avanti", "Alcalisa", "GRC"):
            assert employer in cv_text_grupo_red, (
                f"Empleador '{employer}' no encontrado en el CV"
            )
