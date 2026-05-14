"""
Ciclo 12 RED→GREEN: Narrative Builder — integridad de datos.
Verifica que narrativas_lorena.json tiene la estructura correcta,
que los bullets por rol están separados (sin cross-contaminación),
y que el Amazon date fue corregido a 'Feb 2026'.

Tests sin LLM: validan solo la carga de datos JSON.
"""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NARRATIVAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "narrativas", "narrativas_lorena.json",
)


@pytest.fixture(scope="module")
def narrativas() -> dict:
    with open(NARRATIVAS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── TestNarrativasStructure ────────────────────────────────────────────────────

class TestNarrativasStructure:
    """El JSON de narrativas tiene todas las claves esperadas."""

    def test_json_loads(self, narrativas):
        assert isinstance(narrativas, dict)

    def test_has_roles(self, narrativas):
        assert "roles" in narrativas
        assert len(narrativas["roles"]) >= 2

    def test_has_bullets_validados(self, narrativas):
        assert "bullets_validados" in narrativas

    def test_bullets_validados_has_all_ramas(self, narrativas):
        bv = narrativas["bullets_validados"]
        for rama in ("A", "B", "C"):
            assert rama in bv, f"bullets_validados falta rama '{rama}'"

    def test_has_bullets_por_rol(self, narrativas):
        assert "bullets_por_rol" in narrativas

    def test_bullets_por_rol_has_amazon_and_linkedin(self, narrativas):
        bpr = narrativas["bullets_por_rol"]
        assert "amazon" in bpr, "bullets_por_rol falta clave 'amazon'"
        assert "linkedin_teleperformance" in bpr, (
            "bullets_por_rol falta clave 'linkedin_teleperformance'"
        )

    def test_rama_c_has_minimum_bullets(self, narrativas):
        bullets_c = narrativas["bullets_validados"].get("C", [])
        assert len(bullets_c) >= 15, (
            f"Rama C tiene muy pocos bullets validados: {len(bullets_c)} (mínimo 15)"
        )


# ── TestAmazonDateCorrect ──────────────────────────────────────────────────────

class TestAmazonDateCorrect:
    """
    Amazon fecha debe ser 'May 2025 – Feb 2026' (el rol terminó cuando empezó LinkedIn).
    Este test fallaría si alguien revierte la corrección en narrativas_lorena.json.
    """

    def test_amazon_role_date_is_feb_2026(self, narrativas):
        amazon_role = next(
            (r for r in narrativas["roles"] if "Amazon" in r.get("empresa", "")),
            None,
        )
        assert amazon_role is not None, "Rol Amazon no encontrado en narrativas"
        fecha = amazon_role.get("fecha", "")
        assert "Feb 2026" in fecha, (
            f"Fecha Amazon incorrecta: '{fecha}' — debe contener 'Feb 2026'"
        )
        assert "Present" not in fecha, (
            f"Fecha Amazon contiene 'Present': '{fecha}' — el rol ya terminó"
        )

    def test_linkedin_role_date_is_present(self, narrativas):
        """El rol LinkedIn (Teleperformance) es el activo — debe mostrar Present."""
        linkedin_role = next(
            (r for r in narrativas["roles"] if "Teleperformance" in r.get("empresa", "")),
            None,
        )
        assert linkedin_role is not None, "Rol LinkedIn/Teleperformance no encontrado"
        fecha = linkedin_role.get("fecha", "")
        assert "Present" in fecha, (
            f"Fecha LinkedIn/Teleperformance incorrecta: '{fecha}' — debe contener 'Present'"
        )


# ── TestBulletsRoleSeparation ──────────────────────────────────────────────────

class TestBulletsRoleSeparation:
    """
    Los bullets de Amazon y LinkedIn no deben mezclarse (cross-contaminación).
    Amazon bullets deben mencionar APAC/ROAS/DSP.
    LinkedIn bullets NO deben mencionar Singapore/Sydney/Tokyo/APAC.
    """

    def test_amazon_bullets_mention_apac_or_dsp(self, narrativas):
        # bullets_por_rol["amazon"] es un dict: {"empresa":..., "mercado":..., "bullets":[...]}
        amazon_entry = narrativas["bullets_por_rol"].get("amazon", {})
        amazon_bullets = amazon_entry.get("bullets", []) if isinstance(amazon_entry, dict) else amazon_entry
        assert amazon_bullets, "bullets_por_rol.amazon.bullets está vacío"
        combined = " ".join(amazon_bullets)
        has_apac_context = any(
            kw in combined
            for kw in ["APAC", "DSP", "tROAS", "ROAS", "Narwal", "Singapore", "Sydney"]
        )
        assert has_apac_context, (
            "bullets de Amazon no mencionan contexto APAC/DSP:\n" + combined[:400]
        )

    def test_linkedin_bullets_no_apac(self, narrativas):
        linkedin_entry = narrativas["bullets_por_rol"].get("linkedin_teleperformance", {})
        linkedin_bullets = linkedin_entry.get("bullets", []) if isinstance(linkedin_entry, dict) else linkedin_entry
        assert linkedin_bullets, "bullets_por_rol.linkedin_teleperformance.bullets está vacío"
        combined = " ".join(linkedin_bullets)
        for kw in ("Singapore", "Sydney", "Tokyo", "APAC"):
            assert kw not in combined, (
                f"CONTAMINACIÓN: '{kw}' apareció en bullets de LinkedIn/Teleperformance:\n"
                + combined[:400]
            )

    def test_linkedin_bullets_mention_latin_america(self, narrativas):
        linkedin_entry = narrativas["bullets_por_rol"].get("linkedin_teleperformance", {})
        linkedin_bullets = linkedin_entry.get("bullets", []) if isinstance(linkedin_entry, dict) else linkedin_entry
        combined = " ".join(linkedin_bullets)
        assert "Latin America" in combined or "LATAM" in combined, (
            "bullets de LinkedIn no mencionan Latin America:\n" + combined[:400]
        )
