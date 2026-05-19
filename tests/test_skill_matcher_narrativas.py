"""
TDD — Skill Matcher: Narrativas Supplement (2026-05-19)

Verifica que _cv_to_text() incorpora bullets de narrativas_lorena.json
para capturar contexto sectorial que el PDF genérico omite.

Problema original:
  - Alcalisa S.A. aparece en el PDF como "brand strategy and portfolio management"
  - No menciona: licores, spirits, HORECA, Supermaxi, aguardiente, etc.
  - El keyword scorer nunca conecta a Lorena con JDs del sector
  - DISLICORES (licores) → 57% falso negativo; debería ser 80%+

Fix:
  - _cv_to_text(cv, narrativas) suplementa con bullets_por_rol de narrativas
  - Todos los keywords sectoriales verificados quedan en el texto del CV
  - El keyword scorer y el scorer semántico tienen contexto real
"""
import pytest
from agents.skill_matcher import _cv_to_text


# ── Fixtures ───────────────────────────────────────────────────────────────────

_CV_MINIMAL = {
    "nombre": "Lorena Ruiz",
    "experiencia": [
        {
            "cargo": "National Marketing Manager",
            "empresa": "Alcalisa S.A.",
            "fecha": "2013-2018",
            "descripcion": "Brand strategy and portfolio management.",
        }
    ],
    "educacion": [],
    "skills": ["Marketing", "Strategy"],
    "idiomas": ["Spanish", "English"],
}

_NARRATIVAS_ALCALISA = {
    "bullets_por_rol": {
        "alcalisa": {
            "empresa": "Alcalisa S.A.",
            "bullets": [
                "Grew company revenue from USD 1.5M to USD 3.0M managing spirits portfolio.",
                "Achieved 100% portfolio codification across Supermaxi, Coral, Tia in HORECA channel.",
                "Led 12-15 point-of-sale activations per year for licores and spirits brands.",
                "Managed a team of 12 direct reports and coordinated 3 external agencies.",
            ],
        }
    }
}

_NARRATIVAS_ENZALSARTE = {
    "bullets_por_rol": {
        "enzalsarte": {
            "empresa": "Enzalsarte (marca propia)",
            "periodo": "Marzo 2020 – Agosto 2021",
            "bullets": [
                "Founded artisanal bread brand Enzalsarte with 17 SKUs using zero-kilometer ingredients.",
                "Built D2C delivery model via WhatsApp for 40 client families in retiree community.",
                "Generated COP 10M/month (~USD 2,600) in revenue — profitable from launch.",
            ],
        }
    }
}

_NARRATIVAS_MULTI = {
    "bullets_por_rol": {
        "alcalisa": {
            "empresa": "Alcalisa S.A.",
            "bullets": [
                "Grew spirits portfolio in HORECA — Supermaxi, Coral, Tia.",
                "Managed licores budget USD 350K–450K per year.",
            ],
        },
        "enzalsarte": {
            "empresa": "Enzalsarte (marca propia)",
            "periodo": "Marzo 2020 – Agosto 2021",
            "bullets": [
                "Founded artisanal bakery brand. D2C via WhatsApp. 40 families.",
            ],
        },
        "amazon": {
            "empresa": "Amazon, Colombia",
            "bullets": [
                "Amazon DSP programmatic campaigns for APAC premium brands.",
                "tROAS Narwal 1.28x → 3.28x in 30 days.",
            ],
        },
    }
}


# ── Tests: backward compat (sin narrativas) ────────────────────────────────────

class TestCvToTextBackwardCompat:

    def test_works_without_narrativas_arg(self):
        """Sin pasar narrativas, funciona igual que antes."""
        text = _cv_to_text(_CV_MINIMAL)
        assert "Lorena Ruiz" in text
        assert "Alcalisa S.A." in text

    def test_works_with_none_narrativas(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas=None)
        assert "Lorena Ruiz" in text
        assert isinstance(text, str)

    def test_works_with_empty_narrativas(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas={})
        assert "Lorena Ruiz" in text

    def test_works_with_narrativas_missing_bullets_por_rol(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas={"_version": "test-only"})
        assert "Lorena Ruiz" in text

    def test_returns_string_always(self):
        for nar in [None, {}, _NARRATIVAS_ALCALISA]:
            result = _cv_to_text(_CV_MINIMAL, narrativas=nar)
            assert isinstance(result, str), f"No retornó string con narrativas={nar!r}"


# ── Tests: keywords sectoriales Alcalisa ──────────────────────────────────────

class TestCvToTextAlcalisaKeywords:

    def test_includes_spirits_keyword(self):
        """'spirits' debe aparecer — el PDF genérico no lo incluye."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)
        assert "spirits" in text.lower(), (
            "Keyword 'spirits' no encontrado — el matcher fallará JDs de licores"
        )

    def test_includes_horeca_keyword(self):
        """'HORECA' es un keyword crítico para JDs de licores/trade marketing."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)
        assert "HORECA" in text, (
            "Keyword 'HORECA' no encontrado — el matcher fallará JDs del sector"
        )

    def test_includes_supermaxi_keyword(self):
        """Chains de retail deben aparecer para JDs de trade marketing."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)
        assert "Supermaxi" in text

    def test_includes_licores_keyword(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)
        assert "licores" in text.lower()

    def test_includes_team_leadership_keyword(self):
        """Bullet de 12 reportes directos debe aparecer en el texto."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)
        assert "12" in text and ("direct reports" in text or "team" in text.lower())


# ── Tests: keywords Enzalsarte (emprendimiento / D2C) ─────────────────────────

class TestCvToTextEnzalsarteKeywords:

    def test_includes_artisanal_keyword(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ENZALSARTE)
        assert "artisanal" in text.lower() or "Enzalsarte" in text

    def test_includes_d2c_keyword(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ENZALSARTE)
        assert "D2C" in text or "WhatsApp" in text

    def test_includes_periodo_when_present(self):
        """El período del rol aparece en el texto (relevante para auditor de gaps)."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ENZALSARTE)
        assert "2020" in text or "2021" in text

    def test_includes_revenue_figure(self):
        """Métrica de facturación debe aparecer."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ENZALSARTE)
        assert "10M" in text or "2,600" in text or "USD" in text


# ── Tests: múltiples roles en narrativas ──────────────────────────────────────

class TestCvToTextMultipleRoles:

    def test_includes_bullets_from_all_roles(self):
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_MULTI)
        assert "HORECA" in text           # Alcalisa
        assert "artisanal" in text.lower() or "WhatsApp" in text  # Enzalsarte
        assert "Amazon DSP" in text       # Amazon

    def test_text_longer_with_narrativas(self):
        """El texto con narrativas debe ser significativamente más largo."""
        text_sin = _cv_to_text(_CV_MINIMAL)
        text_con = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_MULTI)
        assert len(text_con) > len(text_sin) * 1.5, (
            f"Texto con narrativas ({len(text_con)} chars) no es "
            f"50%+ más largo que sin narrativas ({len(text_sin)} chars)"
        )

    def test_empresa_names_appear_in_text(self):
        """Los nombres de empresa de bullets_por_rol aparecen como headers."""
        text = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_MULTI)
        assert "Alcalisa S.A." in text
        assert "Enzalsarte" in text
        assert "Amazon" in text

    def test_roles_with_no_bullets_skipped_gracefully(self):
        """Un rol sin bullets no genera errores ni texto vacío."""
        nar = {
            "bullets_por_rol": {
                "vacio": {
                    "empresa": "Empresa Sin Bullets",
                    "bullets": [],
                },
                "alcalisa": _NARRATIVAS_ALCALISA["bullets_por_rol"]["alcalisa"],
            }
        }
        text = _cv_to_text(_CV_MINIMAL, narrativas=nar)
        assert "HORECA" in text  # Alcalisa sí tiene bullets
        # No debe crashear por el rol vacío


# ── Test de integración: keyword score mejora con narrativas ──────────────────

class TestKeywordScoreImprovement:
    """
    Verifica que el keyword scorer detecta más skills cuando
    _cv_to_text incluye las narrativas.
    """

    def test_licores_jd_scores_higher_with_narrativas(self):
        """
        _keyword_score busca en (cv_text + jd). El fix mejora el score cuando
        los skills_target NO están en el JD pero SÍ en el CV con narrativas.

        Escenario: JD de bebidas/distribución que NO usa los mismos keywords
        exactos (usa sinónimos/sector), pero skills_target son los keywords
        que sí están en las narrativas de Alcalisa.
        """
        from agents.skill_matcher import _keyword_score

        # Skills que Alcalisa tiene en narrativas pero el JD NO menciona directamente
        skills_target = ["licores", "spirits", "HORECA", "Supermaxi"]

        text_sin = _cv_to_text(_CV_MINIMAL)
        text_con = _cv_to_text(_CV_MINIMAL, narrativas=_NARRATIVAS_ALCALISA)

        # JD que NO menciona esos keywords — así el score viene del CV, no del JD
        jd = "Buscamos gerente de marketing para empresa de bebidas y distribución nacional."

        score_sin, matched_sin, gaps_sin = _keyword_score(text_sin, jd, skills_target)
        score_con, matched_con, gaps_con = _keyword_score(text_con, jd, skills_target)

        assert score_con > score_sin, (
            f"Score con narrativas ({score_con}%) no mejora vs sin narrativas ({score_sin}%). "
            f"Matched sin narrativas: {matched_sin} | con narrativas: {matched_con}"
        )
        # Con narrativas debe matchear al menos spirits, HORECA y Supermaxi
        assert score_con >= 60, (
            f"Score con narrativas solo {score_con}% — debería superar 60% "
            f"con bullets de Alcalisa en el CV. Matched: {matched_con}"
        )
        # Sin narrativas no debería matchear ninguno (JD no los menciona,
        # y el PDF genérico tampoco)
        assert score_sin == 0, (
            f"Score sin narrativas debería ser 0% (ni el JD ni el PDF mencionan "
            f"los keywords sectoriales). Matched: {matched_sin}"
        )
