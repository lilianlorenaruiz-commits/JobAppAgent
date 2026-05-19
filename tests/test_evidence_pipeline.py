"""
Tests de integración para el pipeline de evidencia en main.py.

Verifica:
  - build_evidence_map se llama entre analyze y rewrite cuando analyze pasa
  - build_evidence_map NO se llama si analyze falla
  - evidence_map se pasa a rewrite()
  - poor_fit (tier3_count > 5) → rewrite no se llama, motivo correcto
  - 5 Tier 3 skills (exactamente) NO es poor_fit
  - Si build_evidence_map falla → pipeline continúa con evidence_map=None
  - Si falla → rewrite recibe evidence_map=None (usa fallback interno)
"""
import os
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Fixtures ──────────────────────────────────────────────────────────────────

_JOB = {
    "cargo":       "Media Planning Manager",
    "empresa":     "OMD Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "descripcion": (
        "Buscamos Media Planning Manager con experiencia en Google Ads, Meta Ads, "
        "LinkedIn Ads y Amazon Ads. Presupuesto mensual USD 200K. Inglés C1 requerido."
    ),
    "rama":        "C",
    "url":         "https://linkedin.com/jobs/test-001",
}

_CV_DICT = {
    "nombre":      "Lorena Ruiz",
    "experiencia": [
        {
            "cargo":       "Digital Channels Consultant",
            "empresa":     "Avanti IT SAS",
            "fecha":       "August 2021 – April 2025",
            "descripcion": "Gestion de campanas digitales.",
        }
    ],
    "educacion": [],
    "skills":    ["Meta Ads", "Google Ads"],
    "idiomas":   ["Spanish (native)", "English (C2)"],
}


def _fake_analyze_passed(cv, job, rama):
    return {
        "score": 90, "passed": True, "threshold": 75,
        "skills_match": [], "skills_gap": [], "reason": "ok",
    }


def _fake_analyze_failed(cv, job, rama):
    return {
        "score": 50, "passed": False, "threshold": 75,
        "skills_match": [], "skills_gap": [], "reason": "low",
    }


def _fake_rewrite(cv, job, rama, **kwargs):
    return {
        "cv_text":         "LORENA RUIZ\n...",
        "ats_score":       97,
        "keywords_added":  ["paid media"],
        "attempts":        1,
        "passed_ats":      True,
        "poor_fit":        False,
        "poor_fit_reason": "",
    }


def _fake_audit(job, cv_text, evidence_map=None):
    return {
        "audit_score": 96, "verdict": "PASS", "passed_audit": True,
        "keywords_missing": [], "feedback_to_rewriter": "",
    }


def _fake_generate(cv_text, job):
    return "/tmp/fake_cv.pdf"


def _fake_aplicar(job, pdf_path, dry_run=False, cv_text="", job_description=""):
    return {"enviado": False, "canal": "C", "mensaje": "dry_run"}


def _fake_register(*args, **kwargs):
    pass


def _fake_load_narrativas(path=None):
    return {"roles": [], "plataformas": {}}


def _make_poor_fit_map(n_tier3: int) -> dict:
    return {f"skill_{i}": {"tier": 3, "evidencia": []} for i in range(n_tier3)}


_GOOD_EVIDENCE_MAP = {
    "Google Ads": {"tier": 1, "evidencia": [{"rol": "Amazon", "bullet": "Managed campaigns"}]},
}


# ── B1: build_evidence_map se llama entre analyze y rewrite ───────────────────

class TestEvidenceMapCalledInPipeline:

    def test_build_called_when_analyze_passes(self):
        """build_evidence_map se llama cuando analyze pasa el threshold."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", return_value={}) as mock_build,
            patch("main.rewrite", _fake_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        mock_build.assert_called_once()

    def test_build_not_called_when_analyze_fails(self):
        """build_evidence_map NO se llama cuando analyze no pasa."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_failed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map") as mock_build,
            patch("main.register", _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        mock_build.assert_not_called()

    def test_evidence_map_passed_to_rewrite(self):
        """El evidence_map construido por main.py se pasa a rewrite()."""
        from main import _process_job
        captured = {}

        def _capturing_rewrite(cv, job, rama, **kwargs):
            captured["evidence_map"] = kwargs.get("evidence_map")
            return _fake_rewrite(cv, job, rama, **kwargs)

        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", return_value=_GOOD_EVIDENCE_MAP),
            patch("main.rewrite", _capturing_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        assert captured.get("evidence_map") == _GOOD_EVIDENCE_MAP, (
            f"evidence_map no fue pasado a rewrite(). Recibido: {captured.get('evidence_map')}"
        )


# ── B2: poor_fit early exit ────────────────────────────────────────────────────

class TestPoorFitEarlyExit:

    def test_rewrite_not_called_when_6_tier3(self):
        """Con 6 Tier 3 skills (> POOR_FIT_THRESHOLD=5), rewrite() no se llama."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", return_value=_make_poor_fit_map(6)),
            patch("main.rewrite") as mock_rewrite,
            patch("main.register", _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        mock_rewrite.assert_not_called()

    def test_motivo_mentions_poor_fit_when_6_tier3(self):
        """El resultado incluye 'poor fit' en el motivo cuando hay 6 Tier 3 skills."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", return_value=_make_poor_fit_map(6)),
            patch("main.rewrite"),
            patch("main.register", _fake_register),
        ):
            result = _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        assert "poor fit" in result["motivo"].lower(), (
            f"El motivo no menciona 'poor fit': '{result['motivo']}'"
        )

    def test_exactly_5_tier3_is_not_poor_fit(self):
        """5 Tier 3 skills (== POOR_FIT_THRESHOLD) NO es poor_fit — rewrite se llama."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", return_value=_make_poor_fit_map(5)),
            patch("main.rewrite", _fake_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            result = _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        assert result["status"] in ("enviado", "pendiente_envio"), (
            f"5 Tier 3 skills no debe ser poor_fit. Status: {result['status']}, "
            f"motivo: {result.get('motivo')}"
        )


# ── B3: defensive — fallo de evidence_map ─────────────────────────────────────

class TestEvidenceMapDefensive:

    def test_pipeline_continues_when_build_raises(self):
        """Si build_evidence_map lanza excepción, el pipeline continúa sin mapa."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", side_effect=RuntimeError("API error")),
            patch("main.rewrite", _fake_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            result = _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        assert result["status"] in ("enviado", "pendiente_envio"), (
            f"Pipeline debe continuar tras error en evidence_map. Status: {result['status']}"
        )

    def test_rewrite_receives_none_when_build_fails(self):
        """Si build_evidence_map falla, rewrite recibe evidence_map=None (fallback interno)."""
        from main import _process_job
        captured = {}

        def _capturing_rewrite(cv, job, rama, **kwargs):
            captured["evidence_map"] = kwargs.get("evidence_map")
            return _fake_rewrite(cv, job, rama, **kwargs)

        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", _fake_load_narrativas),
            patch("main.build_evidence_map", side_effect=RuntimeError("API error")),
            patch("main.rewrite", _capturing_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        assert captured.get("evidence_map") is None, (
            "Cuando build_evidence_map falla, rewrite debe recibir None para fallback interno. "
            f"Recibido: {captured.get('evidence_map')}"
        )

    def test_pipeline_continues_when_load_narrativas_returns_empty(self):
        """Si load_narrativas retorna {}, skip evidence_map y llama rewrite normalmente."""
        from main import _process_job
        with (
            patch("main.analyze", _fake_analyze_passed),
            patch("main.load_narrativas", return_value={}),
            patch("main.build_evidence_map") as mock_build,
            patch("main.rewrite", _fake_rewrite),
            patch("main.audit", _fake_audit),
            patch("main.generate", _fake_generate),
            patch("main.aplicar", _fake_aplicar),
            patch("main.register", _fake_register),
        ):
            result = _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)
        mock_build.assert_not_called()
        assert result["status"] in ("enviado", "pendiente_envio")
