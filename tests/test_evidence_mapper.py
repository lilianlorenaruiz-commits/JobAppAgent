"""
Tests TDD para evidence_mapper.py.
Todos los tests usan Claude mockeado — no llaman la API real.
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Fixtures ───────────────────────────────────────────────────────────────────

_NARRATIVAS_MINI = {
    "roles": [
        {
            "empresa": "Alcalisa S.A.",
            "logros": [
                "Grew company revenue from USD 1.5M to USD 3.0M in 4 years (+100%), leading brand strategy and trade marketing.",
                "Grew market share from 12% to 18% in Ecuador spirits segment.",
                "Trained 150+ people per year: regional distributors, bartenders, and HORECA staff.",
            ],
        },
        {
            "empresa": "Avanti IT SAS",
            "logros": [
                "Increased client satisfaction by 20 percent through conversational flow optimization.",
                "Implemented chatbot for COMFENALCO EPS — reduced physical load by 80 percent.",
            ],
        },
        {
            "empresa": "Amazon, Colombia",
            "logros": [
                "Narwal: tROAS improved from 1.28x to 3.28x; USD 100,000 attributed sales in 30 days via DSP remarketing.",
                "Designed funnel-based reporting format adopted as internal standard by all Account Executives.",
            ],
        },
    ],
    "plataformas": {
        "meta_ads": {
            "empresas": ["Alcalisa S.A."],
            "logro_destacado": "USD 800 Facebook Ads → +18% ventas Bellows whisky Supermaxi diciembre.",
        }
    },
    "liderazgo": {
        "empresa_y_rol": "Alcalisa S.A. — National Marketing Manager (2013-2018)",
        "logro_coordinacion": "Lanzamiento Secreto Inti: estrategia HORECA → retail. 20+ puntos premium 2015. Codificado en Supermaxi 2016.",
        "capacitacion_anual": "150+ personas/año — distribuidores regionales, bartenders, HORECA hoteles 5 estrellas.",
    },
    "trade_retail": {
        "pl_ventas_anuales": "USD 1.5M (2013) → USD 3.0M (2017)",
        "market_share": "12% (2013) → 18% (2017) — +6 p.p.",
        "activaciones_anuales": "12-15 por año",
    },
    "brand_strategy": {
        "proyecto_mas_grande": "GRC S.A. — creación y posicionamiento de 3 marcas de vino para exportación China y Rusia.",
        "datos_awareness": "Alcalisa: awareness 18% → 34%; share of voice digital 0% → 45%.",
        "lanzamientos_liderados": "8 lanzamientos de productos + 6 campañas 360°.",
    },
}

_JD_RETAIL = (
    "Buscamos Category Manager con experiencia en gestión de categorías, "
    "trade marketing, liderazgo de equipos y planificación de surtido. "
    "Manejo de cadenas retail (Supermaxi, Éxito). Inglés B2 requerido."
)

_JD_WMS = (
    "Se requiere Warehouse Manager con dominio de WMS, gestión de inventario, "
    "logística de última milla y picking. Excel avanzado."
)


def _mock_haiku(skills_text="gestión de categorías\ntrade marketing\nliderazgo de equipos"):
    """
    Mock del cliente: primera llamada = skills, todas las siguientes = NONE.
    Skills con keyword match no consumen llamadas adicionales.
    Skills sin keyword match invocan semantic search → retorna NONE → Tier 3.
    """
    first = MagicMock(content=[MagicMock(text=skills_text)])
    fallback = MagicMock(content=[MagicMock(text="NONE")])
    client = MagicMock()
    client.messages.create.side_effect = [first] + [fallback] * 20
    return client


# ── Tests: _flatten_narrativas ─────────────────────────────────────────────────

class TestFlattenNarrativas:
    def test_returns_list_of_dicts(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        assert isinstance(result, list)
        assert all("rol" in item and "bullet" in item for item in result)

    def test_includes_role_logros(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("tROAS" in b for b in bullets), "Bullets de Amazon no incluidos"
        assert any("chatbot" in b for b in bullets), "Bullets de Avanti IT no incluidos"

    def test_includes_platform_logros(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("Bellows" in b for b in bullets), "Logro de plataforma meta_ads no incluido"

    def test_includes_liderazgo_and_trade(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("Secreto Inti" in b for b in bullets), "Logro de liderazgo no incluido"
        assert any("1.5M" in b for b in bullets), "Dato de trade_retail no incluido"

    def test_empty_narrativas_returns_empty_list(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas({})
        assert result == []


# ── Tests: _c1_active_subject ──────────────────────────────────────────────────

class TestC1ActiveSubject:
    def test_active_verb_grew(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Grew revenue from 1.5M to 3.0M") is True

    def test_active_verb_managed(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Managed 300 B2B accounts across Latin America") is True

    def test_active_verb_implemented(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Implemented chatbot for COMFENALCO EPS") is True

    def test_active_verb_designed(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Designed funnel-based reporting format") is True

    def test_support_verb_supported(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Supported 4 Account Executives with campaign reporting") is False

    def test_empty_bullet(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("") is False

    def test_bullet_with_punctuation(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Trained, mentored, and developed team members") is True


# ── Tests: build_evidence_map ──────────────────────────────────────────────────

class TestBuildEvidenceMap:
    def test_returns_dict(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        assert isinstance(result, dict)

    def test_skills_have_tier_and_evidencia_keys(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        for skill, data in result.items():
            assert "tier" in data, f"Skill '{skill}' sin clave 'tier'"
            assert "evidencia" in data, f"Skill '{skill}' sin clave 'evidencia'"

    def test_tier_values_are_1_2_or_3(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        for skill, data in result.items():
            assert data["tier"] in (1, 2, 3), f"Tier inválido para '{skill}': {data['tier']}"

    def test_tier3_has_empty_evidencia(self):
        from agents.evidence_mapper import build_evidence_map
        responses = [
            MagicMock(content=[MagicMock(text="gestión de inventario WMS\nlogística de última milla")]),
            MagicMock(content=[MagicMock(text="NONE")]),
            MagicMock(content=[MagicMock(text="NONE")]),
        ]
        client = MagicMock()
        client.messages.create.side_effect = responses
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_WMS, _NARRATIVAS_MINI)
        tier3 = {k: v for k, v in result.items() if v["tier"] == 3}
        assert len(tier3) > 0, "JD de WMS debería producir al menos un Tier 3"
        for skill, data in tier3.items():
            assert data["evidencia"] == [], f"Tier 3 '{skill}' debe tener evidencia=[]"

    def test_active_verb_bullet_yields_tier1(self):
        from agents.evidence_mapper import build_evidence_map
        # "trade marketing" hará keyword match con "Grew...trade marketing" (active verb → T1)
        responses = [
            MagicMock(content=[MagicMock(text="trade marketing")]),
        ]
        client = MagicMock()
        client.messages.create.side_effect = responses
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map("trade marketing experience required", _NARRATIVAS_MINI)
        assert result["trade marketing"]["tier"] == 1, (
            f"Bullet 'Grew...trade marketing' (active verb) debe ser Tier 1, "
            f"got {result['trade marketing']['tier']}"
        )

    def test_empty_narrativas_returns_all_tier3(self):
        from agents.evidence_mapper import build_evidence_map
        responses = [
            MagicMock(content=[MagicMock(text="algún skill")]),
        ]
        client = MagicMock()
        client.messages.create.side_effect = responses
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map("some JD text", {})
        assert all(v["tier"] == 3 for v in result.values()), (
            "Con narrativas vacías, todos los skills deben ser Tier 3"
        )


# ── Tests: verify_evidence ─────────────────────────────────────────────────────

class TestVerifyEvidence:
    def test_returns_empty_when_tier1_present_in_cv(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "trade marketing": {
                "tier": 1,
                "evidencia": [{"rol": "Alcalisa", "bullet": "Grew revenue from USD 1.5M to USD 3.0M in 4 years"}],
            }
        }
        cv_text = "WORK EXPERIENCE\n- Grew revenue from USD 1.5M to USD 3.0M in 4 years leading trade marketing"
        result = verify_evidence(cv_text, evidence_map)
        assert result == [], f"No debería haber skills faltantes, got: {result}"

    def test_returns_skill_when_tier1_absent_from_cv(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "trade marketing": {
                "tier": 1,
                "evidencia": [{"rol": "Alcalisa", "bullet": "Grew market share from 12% to 18%"}],
            }
        }
        cv_text = "WORK EXPERIENCE\n- Managed social media campaigns"
        result = verify_evidence(cv_text, evidence_map)
        assert "trade marketing" in result, f"Skill faltante no detectado: {result}"

    def test_ignores_tier2_and_tier3(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "planificación de surtido": {
                "tier": 2,
                "evidencia": [{"rol": "Avanti", "bullet": "Supported retailers with portfolio analysis"}],
            },
            "gestión WMS": {"tier": 3, "evidencia": []},
        }
        cv_text = "No menciona ninguno de estos skills"
        result = verify_evidence(cv_text, evidence_map)
        assert result == [], f"verify_evidence no debe reportar Tier 2/3 como faltantes: {result}"

    def test_empty_evidence_map_returns_empty_list(self):
        from agents.evidence_mapper import verify_evidence
        result = verify_evidence("cualquier CV text", {})
        assert result == []


# ── Tests: load_narrativas ──────────────────────────────────────────────────────

class TestLoadNarrativas:
    def test_returns_dict_when_file_exists(self, tmp_path):
        """load_narrativas(path) retorna un dict cuando el archivo existe."""
        import json
        from agents.evidence_mapper import load_narrativas
        p = tmp_path / "narrativas.json"
        p.write_text(json.dumps({"roles": [], "plataformas": {}}), encoding="utf-8")
        result = load_narrativas(str(p))
        assert isinstance(result, dict)
        assert "roles" in result

    def test_returns_empty_dict_when_file_not_found(self):
        """load_narrativas() retorna {} si el archivo no existe."""
        from agents.evidence_mapper import load_narrativas
        result = load_narrativas("/nonexistent/path/narrativas.json")
        assert result == {}

    def test_returns_empty_dict_on_json_error(self, tmp_path):
        """load_narrativas() retorna {} si el JSON es inválido."""
        from agents.evidence_mapper import load_narrativas
        p = tmp_path / "bad.json"
        p.write_text("not valid json", encoding="utf-8")
        result = load_narrativas(str(p))
        assert result == {}

    def test_default_path_returns_dict(self):
        """load_narrativas() sin path retorna dict (con o sin archivo real)."""
        from agents.evidence_mapper import load_narrativas
        result = load_narrativas()
        assert isinstance(result, dict)
