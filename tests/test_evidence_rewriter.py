"""
Tests para las modificaciones del cv_rewriter con evidence mapping.
Verifica:
  - Reglas 7 y 10 problemáticas eliminadas de _SYSTEM
  - EVIDENCE MAP llega al prompt de Claude
  - Tier 3 marcado para omitir en el prompt
  - poor_fit=True cuando hay más de POOR_FIT_THRESHOLD Tier 3
  - poor_fit=False cuando hay pocos Tier 3
  - rewrite() siempre retorna clave 'poor_fit'
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB = {
    "cargo": "Category Manager",
    "empresa": "Falabella",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "descripcion": (
        "Buscamos Category Manager con experiencia en gestión de categorías, "
        "trade marketing, liderazgo de equipos y planificación de surtido."
    ),
    "rama": "B",
}

_CV_DICT = {
    "nombre": "Lorena Ruiz",
    "experiencia": [
        {"cargo": "National Marketing Manager", "empresa": "Alcalisa S.A.",
         "fecha": "2013 – 2018", "descripcion": "Trade marketing."}
    ],
    "educacion": [],
    "skills": ["Trade Marketing", "Category Management"],
    "idiomas": ["Spanish (native)", "English (C2)"],
}

_GOOD_RESPONSE = """\
<CV>
LORENA RUIZ

Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884  |  www.linkedin.com/in/lilianlorenaruiz

PROFESSIONAL PROFILE
Trade Marketing and Category Management professional with 14 years of experience.

WORK EXPERIENCE

Alcalisa S.A.
National Marketing Manager
2013 – 2018
- Grew market share from 12% to 18% in Ecuador spirits segment through category management.
- Led trade marketing activations across Supermaxi, Coral, Tía, and Santa María.

EDUCATION

Diploma in AI and Community Management
Aug 2023 – Nov 2023
Universidad del Valle, Cali, Colombia

Advanced Certificate in Retail and Trade Marketing
2017 – 2017
EDES Business School, Retail Institute Spain and Latam, Quito, Ecuador

Master's in Marketing and Commercial Management
2011 – 2012
Real Centro Universitario Maria Cristina, Escuela Europea

Bachelor's in Social Communication and Journalism
2005 – 2011
Universidad del Valle, Cali, Colombia

SKILLS
- Trade Marketing, Category Management

LANGUAGES
Spanish (native)  |  English C2 Proficient (EF SET certified)
</CV>
<ATS_SCORE>96</ATS_SCORE>
<KEYWORDS>Category Manager, gestión de categorías, trade marketing, liderazgo</KEYWORDS>
"""

_EVIDENCE_MAP_FEW_TIER3 = {
    "gestión de categorías": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Grew market share from 12% to 18% in Ecuador spirits segment."}],
    },
    "trade marketing": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Led trade marketing activations across Supermaxi, Coral."}],
    },
    "liderazgo de equipos": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Trained 150+ people per year: distributors and HORECA staff."}],
    },
    "gestión de inventario WMS": {"tier": 3, "evidencia": []},   # solo 1 Tier 3
}

_POOR_FIT_MAP = {f"skill_{i}": {"tier": 3, "evidencia": []} for i in range(6)}  # 6 Tier 3


def _mock_claude(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


# ── Tests: _SYSTEM no tiene reglas problemáticas ───────────────────────────────

class TestSystemPromptRules:
    def test_rule7_keyword_injection_removed(self):
        """Regla 7 original 'Inject keywords from the job description' debe estar eliminada."""
        from agents.cv_rewriter import _SYSTEM
        assert "Inject keywords from the job description" not in _SYSTEM, (
            "Regla 7 de keyword injection sigue en _SYSTEM — debe eliminarse."
        )

    def test_rule10_mirror_title_removed(self):
        """Regla 10 original 'Mirror the exact job-title language' debe estar eliminada."""
        from agents.cv_rewriter import _SYSTEM
        assert "Mirror the exact job-title language" not in _SYSTEM, (
            "Regla 10 de mirror title sigue en _SYSTEM — debe eliminarse."
        )

    def test_evidence_map_instruction_present(self):
        """_SYSTEM debe instruir a usar SOLO el EVIDENCE MAP."""
        from agents.cv_rewriter import _SYSTEM
        assert "EVIDENCE MAP" in _SYSTEM, (
            "_SYSTEM no menciona EVIDENCE MAP — la instrucción de evidencia falta."
        )


# ── Tests: evidence_map llega al prompt de Claude ─────────────────────────────

class TestEvidenceMapInPrompt:
    def test_evidence_map_in_prompt(self):
        """El prompt enviado a Claude debe incluir el EVIDENCE MAP."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=None,
                          evidence_map=_EVIDENCE_MAP_FEW_TIER3, auditor_feedback="")
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "EVIDENCE MAP" in user_content, "EVIDENCE MAP no está en el prompt enviado a Claude"

    def test_tier1_skills_in_prompt(self):
        """Los skills Tier 1 aparecen en el prompt con su evidencia."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=None,
                          evidence_map=_EVIDENCE_MAP_FEW_TIER3, auditor_feedback="")
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "gestión de categorías" in user_content, "Skill Tier 1 no llega al prompt"

    def test_tier3_skill_labeled_omit_in_prompt(self):
        """Los skills Tier 3 están marcados para omitir en el prompt."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=None,
                          evidence_map=_EVIDENCE_MAP_FEW_TIER3, auditor_feedback="")
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "gestión de inventario WMS" in user_content, "Skill Tier 3 no llega al prompt"
        assert "omit" in user_content.lower() or "Tier 3" in user_content, (
            "Skill Tier 3 no está marcado para omitir en el prompt"
        )

    def test_no_keyword_density_in_retry(self):
        """El retry no debe usar 'Increase keyword density'."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=80,
                          evidence_map=_EVIDENCE_MAP_FEW_TIER3, auditor_feedback="")
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Increase keyword density" not in user_content, (
            "El retry sigue usando 'Increase keyword density' — debe eliminarse."
        )


# ── Tests: poor_fit flag ───────────────────────────────────────────────────────

class TestPoorFitFlag:
    def test_poor_fit_true_when_many_tier3(self):
        """rewrite() retorna poor_fit=True cuando hay más de 5 Tier 3."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_POOR_FIT_MAP),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert result.get("poor_fit") is True, (
            f"poor_fit debe ser True con 6 skills Tier 3, got: {result.get('poor_fit')}"
        )

    def test_poor_fit_false_when_few_tier3(self):
        """rewrite() no flagea poor_fit cuando hay pocos Tier 3."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_EVIDENCE_MAP_FEW_TIER3),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert result.get("poor_fit") is not True, (
            f"poor_fit no debe ser True con solo 1 Tier 3, got: {result.get('poor_fit')}"
        )

    def test_result_always_has_poor_fit_key(self):
        """rewrite() siempre retorna la clave 'poor_fit'."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_EVIDENCE_MAP_FEW_TIER3),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert "poor_fit" in result, "La clave 'poor_fit' falta en el resultado de rewrite()"
