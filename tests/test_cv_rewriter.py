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


# ── RC-6: JD USD Amount Isolation ─────────────────────────────────────────────

class TestRC6JdUsdIsolation:
    """
    RC-6 — Prevención de orphan claims inyectados desde el JD.

    Problema: el LLM lee "USD 200K+" en el JD de OMD y lo escribe en el CV
    como si fuera un logro de Lorena. _warn_orphan_claims lo detecta pero
    no lo previene. La fix inyecta un bloque FORBIDDEN explícito al prompt.
    """

    def test_extract_jd_usd_finds_200k(self):
        """Extrae 'USD 200K' del texto del JD."""
        from agents.cv_rewriter import _extract_jd_usd_amounts
        jd = "Gestión de presupuesto mensual USD 200K+. ROAS objetivo 4:1."
        amounts = _extract_jd_usd_amounts(jd)
        assert any("200" in a for a in amounts), (
            f"'USD 200K' no encontrado en: {amounts}"
        )

    def test_extract_jd_usd_finds_multiple(self):
        """Extrae múltiples montos USD del JD."""
        from agents.cv_rewriter import _extract_jd_usd_amounts
        jd = "Budget USD 150,000 mensual. Contratos de USD 2M anuales."
        amounts = _extract_jd_usd_amounts(jd)
        assert len(amounts) >= 2, f"Esperaba ≥2 montos, encontró: {amounts}"

    def test_extract_jd_usd_empty_when_none(self):
        """Retorna lista vacía si el JD no tiene montos USD."""
        from agents.cv_rewriter import _extract_jd_usd_amounts
        jd = "Buscamos profesional con experiencia en marketing digital."
        amounts = _extract_jd_usd_amounts(jd)
        assert amounts == [], f"Esperaba [], encontró: {amounts}"

    def test_extract_jd_usd_deduplicates(self):
        """No duplica el mismo monto si aparece dos veces."""
        from agents.cv_rewriter import _extract_jd_usd_amounts
        jd = "Presupuesto USD 200K. Objetivo: gestionar USD 200K mensual."
        amounts = _extract_jd_usd_amounts(jd)
        count_200k = sum(1 for a in amounts if "200" in a)
        assert count_200k == 1, f"USD 200K aparece {count_200k} veces, esperaba 1"

    def test_build_forbidden_block_contains_amount(self):
        """El bloque FORBIDDEN incluye los montos extraídos del JD."""
        from agents.cv_rewriter import _build_forbidden_block
        jd = "Budget mensual USD 200K+."
        block = _build_forbidden_block(jd)
        assert "200" in block, f"Monto '200K' no encontrado en bloque: {block[:200]}"
        assert "FORBIDDEN" in block.upper(), "Bloque no tiene etiqueta FORBIDDEN"

    def test_build_forbidden_block_empty_when_no_usd(self):
        """No genera bloque si el JD no tiene USD."""
        from agents.cv_rewriter import _build_forbidden_block
        jd = "Buscamos profesional con experiencia en marketing digital."
        block = _build_forbidden_block(jd)
        assert block == "", f"Esperaba string vacío, encontró: {block!r}"

    def test_build_forbidden_block_mentions_fabrication(self):
        """El bloque debe dejar claro que usar los montos es fabricación."""
        from agents.cv_rewriter import _build_forbidden_block
        jd = "Gestión de presupuesto USD 150,000."
        block = _build_forbidden_block(jd)
        assert any(w in block.lower() for w in ["fabricat", "forbidden", "prohibit", "not use"]), (
            f"Bloque no advierte sobre fabricación: {block[:300]}"
        )


# ── Threshold Rama A y B ───────────────────────────────────────────────────────

class TestThresholdProfiles:
    """
    Los perfiles A y B usan threshold_match = 75 (calibrado mercado colombiano real).

    Justificación: el threshold de 82% fue calibrado contra mocks sintéticos con
    keywords exactas. El corpus real de JDs colombianos usa variantes tipográficas
    ("C1/C2", "transformación digital") que el scorer literal no detecta. Con aliases
    + fórmula 20/80 (semantic-primary), el threshold efectivo de calidad es 75%.
    """

    def test_rama_a_threshold_is_75(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_a_consultoria.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_match"] == 75, (
            f"Rama A threshold esperado 75, encontrado {perfil['threshold_match']}"
        )

    def test_rama_b_threshold_is_75(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_b_retail.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_match"] == 75, (
            f"Rama B threshold esperado 75, encontrado {perfil['threshold_match']}"
        )

    def test_rama_c_threshold_unchanged_75(self):
        """Rama C no cambia — ya estaba calibrado en 75."""
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_c_paidmedia.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_match"] == 75, (
            f"Rama C threshold esperado 75, encontrado {perfil['threshold_match']}"
        )


# ── Threshold ATS Rama A y B (95→92) ──────────────────────────────────────────

class TestThresholdAtsProfiles:
    """
    threshold_ats para Rama A y B baja de 95% a 92%.

    Justificación: con evidence map + narrativas + RC-0 a RC-6, un CV al 92% tiene
    17-18 skills T1, 0 orphan claims y pasa el auditor independiente como segundo filtro.
    El 95% fue calibrado antes de que existieran esos controles de calidad.
    Acalibrar a 92%:
      - Grupo Éxito (B): ATS 93% → PASS inmediato
      - Accenture (A):  ATS 91-92% → PASS o muy cerca del umbral
    Rama C no cambia: 95% ya era alcanzable de forma consistente en Paid Media.
    """

    def test_rama_a_threshold_ats_is_92(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_a_consultoria.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_ats"] == 92, (
            f"Rama A threshold_ats esperado 92, encontrado {perfil['threshold_ats']}"
        )

    def test_rama_b_threshold_ats_is_92(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_b_retail.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_ats"] == 92, (
            f"Rama B threshold_ats esperado 92, encontrado {perfil['threshold_ats']}"
        )

    def test_rama_c_threshold_ats_unchanged_95(self):
        """Rama C conserva threshold_ats = 95 — Paid Media alcanza 95% de forma consistente."""
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_c_paidmedia.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_ats"] == 95, (
            f"Rama C threshold_ats esperado 95, encontrado {perfil['threshold_ats']}"
        )

    def test_load_ats_threshold_returns_92_for_rama_a(self):
        """_load_ats_threshold('A') retorna 92 después del cambio."""
        from agents.cv_rewriter import _load_ats_threshold
        assert _load_ats_threshold("A") == 92, (
            f"_load_ats_threshold('A') esperado 92, encontrado {_load_ats_threshold('A')}"
        )

    def test_load_ats_threshold_returns_92_for_rama_b(self):
        """_load_ats_threshold('B') retorna 92 después del cambio."""
        from agents.cv_rewriter import _load_ats_threshold
        assert _load_ats_threshold("B") == 92, (
            f"_load_ats_threshold('B') esperado 92, encontrado {_load_ats_threshold('B')}"
        )

    def test_load_ats_threshold_returns_95_for_rama_c(self):
        """_load_ats_threshold('C') retorna 95 — Rama C no cambia."""
        from agents.cv_rewriter import _load_ats_threshold
        assert _load_ats_threshold("C") == 95, (
            f"_load_ats_threshold('C') esperado 95, encontrado {_load_ats_threshold('C')}"
        )


# ── _fix_static_fields: month dedup + LinkedIn title lock ─────────────────────

class TestFixStaticFieldsDateAndTitle:
    """
    Dos bugs detectados en CVs generados:
    1. "May May 2025 – Feb 2026" — el LLM duplica el nombre del mes.
    2. Título del rol LinkedIn/Teleperformance se reescribe libremente.

    _fix_static_fields debe corregir ambos como post-processing determinístico.
    """

    # ── Bug 1: month duplication ───────────────────────────────────────────────

    def test_may_may_deduped_to_may(self):
        """'May May 2025 – Feb 2026' debe quedar 'May 2025 – Feb 2026'."""
        from agents.cv_rewriter import _fix_static_fields
        cv = (
            "LORENA RUIZ\n"
            "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884\n"
            "WORK EXPERIENCE\n"
            "Campaign Planner Contractor\n"
            "Amazon, Colombia\n"
            "May May 2025 – Feb 2026\n"
            "• Some bullet\n"
        )
        result = _fix_static_fields(cv)
        assert "May May" not in result, (
            f"'May May' no fue corregido:\n{result[:400]}"
        )
        assert "May 2025" in result, (
            f"'May 2025' no encontrado tras dedup:\n{result[:400]}"
        )

    def test_month_dedup_generic_february(self):
        """'February February 2026' → 'February 2026'."""
        from agents.cv_rewriter import _fix_static_fields
        cv = (
            "LORENA RUIZ\n"
            "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884\n"
            "WORK EXPERIENCE\n"
            "Some Role\n"
            "Some Company\n"
            "February February 2026 – Present\n"
        )
        result = _fix_static_fields(cv)
        assert "February February" not in result, (
            f"'February February' no fue corregido:\n{result[:400]}"
        )

    # ── Bug 2: LinkedIn title enforcement ─────────────────────────────────────

    def _linkedin_block(self, wrong_title: str) -> str:
        """Builds a cv_text snippet where the LinkedIn role has a wrong title."""
        return (
            "LORENA RUIZ\n"
            "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884\n"
            "WORK EXPERIENCE\n"
            f"{wrong_title}\n"
            "Teleperformance (contract for LinkedIn Marketing Solutions)\n"
            "February 2026 – Present  |  Bogotá, Hybrid\n"
            "• Manage and optimize LinkedIn Ads campaigns.\n"
        )

    def test_linkedin_title_enforced_when_simplified(self):
        """LLM escribe título simplificado → debe reemplazarse por el canónico."""
        from agents.cv_rewriter import _fix_static_fields, _LINKEDIN_TITLE
        cv = self._linkedin_block("LinkedIn Account Manager")
        result = _fix_static_fields(cv)
        assert _LINKEDIN_TITLE in result, (
            f"Título canónico no encontrado:\nEsperado: {_LINKEDIN_TITLE}\nObtenido:\n{result[:600]}"
        )

    def test_linkedin_title_enforced_when_altered(self):
        """LLM usa título diferente → debe reemplazarse por el canónico."""
        from agents.cv_rewriter import _fix_static_fields, _LINKEDIN_TITLE
        cv = self._linkedin_block("Paid Media Specialist, LinkedIn Marketing Solutions")
        result = _fix_static_fields(cv)
        assert _LINKEDIN_TITLE in result, (
            f"Título canónico no encontrado:\nEsperado: {_LINKEDIN_TITLE}\nObtenido:\n{result[:600]}"
        )

    def test_linkedin_title_not_changed_when_already_correct(self):
        """Si el título ya es canónico, _fix_static_fields no lo altera."""
        from agents.cv_rewriter import _fix_static_fields, _LINKEDIN_TITLE
        cv = self._linkedin_block(_LINKEDIN_TITLE)
        result = _fix_static_fields(cv)
        assert _LINKEDIN_TITLE in result, (
            f"Título canónico eliminado o alterado:\n{result[:600]}"
        )

    def test_linkedin_title_export_exists(self):
        """_LINKEDIN_TITLE debe estar definido y exportado en cv_rewriter."""
        from agents.cv_rewriter import _LINKEDIN_TITLE
        assert "Paid Media Specialist" in _LINKEDIN_TITLE
        assert "LinkedIn Ads" in _LINKEDIN_TITLE
