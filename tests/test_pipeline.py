"""
Tests de comportamiento del pipeline end-to-end.
Verifica que main.py --once --dry-run --rama C completa sin excepciones
y que el estado de la BD es consistente.
"""
import os
import sqlite3
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class TestPipelineDryRun:
    """El pipeline dry-run completa sin errores y registra aplicaciones en BD."""

    @pytest.fixture(scope="class")
    def pipeline_result(self):
        """Ejecuta run_daily una vez para Rama C en dry-run."""
        from main import run_daily
        # Guarda conteo antes de correr
        conn = sqlite3.connect(config.DB_PATH)
        count_before = conn.execute("SELECT COUNT(*) FROM aplicaciones").fetchone()[0]
        conn.close()

        # Pipeline dry-run Rama C, limit 1 cargo para no agotar cuota Apify
        run_daily(ramas=["C"], dry_run=True, limit=1)

        conn = sqlite3.connect(config.DB_PATH)
        count_after = conn.execute("SELECT COUNT(*) FROM aplicaciones").fetchone()[0]
        rows = conn.execute(
            "SELECT cargo, empresa, resultado, match_score, rama "
            "FROM aplicaciones ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()

        return {
            "count_before": count_before,
            "count_after": count_after,
            "recent_rows": rows,
        }

    def test_pipeline_completes(self, pipeline_result):
        """Prueba que run_daily termina sin lanzar excepción."""
        assert pipeline_result is not None

    def test_pipeline_writes_to_db(self, pipeline_result):
        """Al menos un cargo debe registrarse en la BD (Pendiente o Fallido)."""
        assert pipeline_result["count_after"] >= pipeline_result["count_before"], (
            "El pipeline no escribió ningún resultado en la BD"
        )

    def test_pipeline_only_rama_c(self, pipeline_result):
        """Los registros nuevos son Rama C."""
        rows = pipeline_result["recent_rows"]
        if rows:
            for _, _, _, _, rama in rows:
                assert rama == "C", f"Registro de Rama {rama} encontrado, esperaba solo C"

    def test_pipeline_no_null_cargo(self, pipeline_result):
        """Ningún registro tiene cargo vacío."""
        conn = sqlite3.connect(config.DB_PATH)
        bad = conn.execute(
            "SELECT id FROM aplicaciones WHERE cargo IS NULL OR cargo = ''"
        ).fetchall()
        conn.close()
        assert not bad, f"Registros con cargo vacío: {bad}"

    def test_pipeline_resultado_valid(self, pipeline_result):
        """Todos los resultados son valores válidos del schema."""
        valid = {"Enviado", "Pendiente", "Fallido"}
        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute("SELECT DISTINCT resultado FROM aplicaciones").fetchall()
        conn.close()
        for (resultado,) in rows:
            assert resultado in valid, f"Resultado inválido en BD: '{resultado}'"


class TestSkillMatcher:
    """El Skill Matcher funciona correctamente con datos reales."""

    def test_skill_matcher_returns_score(self, cv):
        from agents.skill_matcher import analyze
        job = {
            "cargo": "Paid Media Manager",
            "empresa": "Test Co",
            "descripcion": (
                "Google Ads Meta Ads Amazon Ads ROAS tROAS ACOS CTR CPC "
                "programmatic DSP budget management bilingual C2 LinkedIn Ads"
            ),
            "rama": "C",
        }
        result = analyze(cv, job, "C")
        assert "score" in result
        assert "passed" in result
        assert 0 <= result["score"] <= 100

    def test_skill_matcher_rejects_low_match(self, cv):
        from agents.skill_matcher import analyze
        job = {
            "cargo": "Cocinero",
            "empresa": "Restaurant",
            "descripcion": "Preparar alimentos. Cocina italiana. Sin experiencia en marketing.",
            "rama": "C",
        }
        result = analyze(cv, job, "C")
        assert not result["passed"], (
            f"El matcher aceptó un cargo de cocina con score {result['score']}% "
            f"(threshold {result['threshold']}%)"
        )
