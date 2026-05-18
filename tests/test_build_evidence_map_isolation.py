"""
Mapa de pruebas — Aislamiento de build_evidence_map en rewrite()
================================================================
Fix aplicado en commit 847793c: se añadió
    patch("agents.cv_rewriter.build_evidence_map", return_value={})
en TestRewriteRetryLogic._run_rewrite() y test_stops_on_first_pass().

Este archivo verifica los 5 comportamientos que el parche garantiza:

  B1 — rewrite() invoca build_evidence_map exactamente una vez por llamada
  B2 — evidence_map vacío {} → poor_fit=False (0 Tier 3, sin umbral superado)
  B3 — evidence_map vacío no rompe el retry (ATS bajo → ≥ 2 intentos)
  B4 — evidence_map vacío no rompe el stop-on-pass (ATS alto → 1 intento)
  B5 — evidence_mapper._get_client nunca se llama cuando el parche está activo

Diseño: tests de integración contra la interfaz pública rewrite().
No tocan internals — si se renombra _rewrite_once estos tests siguen verdes.

Ciclos RED→GREEN documentados en comentarios de cada clase.
"""
import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Fixtures compartidas ───────────────────────────────────────────────────────

_JOB = {
    "cargo":       "Media Planning Manager",
    "empresa":     "OMD Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "descripcion": (
        "Buscamos Media Planning Manager con experiencia en Google Ads, Meta Ads, "
        "LinkedIn Ads y Amazon Ads. Presupuesto mensual USD 200K. "
        "Inglés C1/C2 indispensable. Bogotá, modalidad híbrida."
    ),
    "rama": "C",
}

_CV_DICT = {
    "nombre":      "Lorena Ruiz",
    "experiencia": [
        {
            "cargo":       "Digital Channels Consultant",
            "empresa":     "Avanti IT SAS",
            "fecha":       "August 2021 – April 2025",
            "descripcion": "Gestión de campañas digitales.",
        }
    ],
    "educacion": [],
    "skills":    ["Meta Ads", "Google Ads", "LinkedIn Ads"],
    "idiomas":   ["Spanish (native)", "English (C2)"],
}

_GOOD_RESPONSE = """\
<CV>
LORENA RUIZ

Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884  |  www.linkedin.com/in/lilianlorenaruiz

PROFESSIONAL PROFILE
Media Planning Manager with 14 years in paid media strategy.

WORK EXPERIENCE

Avanti IT SAS
Digital Channels Consultant
August 2021 – April 2025
- Managed Google Ads, Meta Ads and LinkedIn Ads budgets totalling USD 200K/month.
- Grew ROAS from 2.1x to 3.8x across e-commerce clients within 6 months.

EDUCATION

Master's in Marketing and Commercial Management
2011 – 2012
Real Centro Universitario Maria Cristina, Escuela Europea

SKILLS
- Google Ads, Meta Ads, LinkedIn Ads, Amazon Ads

LANGUAGES
Spanish (native)  |  English C2 Proficient (EF SET certified)
</CV>
<ATS_SCORE>97</ATS_SCORE>
<KEYWORDS>Media Planning Manager, Google Ads, Meta Ads, LinkedIn Ads, Amazon Ads</KEYWORDS>
"""

_LOW_SCORE_RESPONSE = """\
<CV>
LORENA RUIZ

Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884

PROFESSIONAL PROFILE
Marketing professional.

WORK EXPERIENCE

Avanti IT SAS
Consultant
August 2021 – April 2025
- Supported digital campaigns.

EDUCATION

Master's in Marketing
2011 – 2012
</CV>
<ATS_SCORE>72</ATS_SCORE>
<KEYWORDS>marketing, campaigns</KEYWORDS>
"""


def _mock_claude(text: str) -> MagicMock:
    """Devuelve un cliente Anthropic mockeado que responde con `text`."""
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


@contextmanager
def _base_patches(claude_client, evidence_map=None):
    """
    Contexto de parches mínimo para correr rewrite() sin API real.
    evidence_map=None usa {} (comportamiento del fix).
    Uso: with _base_patches(client): ...
    """
    if evidence_map is None:
        evidence_map = {}
    with (
        patch("agents.cv_rewriter._get_client", return_value=claude_client),
        patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
        patch("agents.cv_rewriter.build_evidence_map", return_value=evidence_map),
    ):
        yield


# ── B1: rewrite() invoca build_evidence_map exactamente una vez ───────────────
#
# RED antes del fix: build_evidence_map no estaba mockeado → llamada real → flaky
# GREEN después del fix: parche intercepta la llamada → assert_called_once pasa

class TestBuildEvidenceMapInvocation:
    """B1 — rewrite() invoca build_evidence_map exactamente una vez por llamada."""

    def test_build_evidence_map_called_once_on_pass(self):
        """
        Cuando ATS pasa en el primer intento, build_evidence_map se llama exactamente 1 vez.
        Verifica que el parche tiene efecto real (no se saltea la llamada).
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        mock_bem = MagicMock(return_value={})

        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", mock_bem),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        mock_bem.assert_called_once()

    def test_build_evidence_map_called_once_on_retry(self):
        """
        build_evidence_map se llama una sola vez aunque haya reintentos.
        El evidence map se computa al inicio, no en cada intento.
        """
        from agents.cv_rewriter import rewrite
        responses = iter([_LOW_SCORE_RESPONSE, _GOOD_RESPONSE])
        mock_bem = MagicMock(return_value={})

        def _next_client():
            return _mock_claude(next(responses, _GOOD_RESPONSE))

        with (
            patch("agents.cv_rewriter._get_client", side_effect=_next_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", mock_bem),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        mock_bem.assert_called_once()

    def test_build_evidence_map_receives_job_description(self):
        """
        build_evidence_map recibe la descripción del job como primer argumento.
        Asegura que el contexto correcto llega al mapper.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        mock_bem = MagicMock(return_value={})

        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", mock_bem),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        first_arg = mock_bem.call_args[0][0]
        assert _JOB["descripcion"] in first_arg or first_arg == _JOB["descripcion"], (
            f"build_evidence_map no recibió la descripción del job. "
            f"Recibió: {first_arg[:80]!r}"
        )


# ── B2: evidence_map vacío → poor_fit=False ───────────────────────────────────
#
# RED antes del fix: build_evidence_map real podía devolver Tier 3 → poor_fit=True
# GREEN: {} tiene 0 Tier 3 → poor_fit siempre False con el parche

class TestEmptyEvidenceMapNoPoorFit:
    """B2 — evidence_map vacío {} nunca activa poor_fit=True."""

    def test_poor_fit_false_with_empty_evidence_map(self):
        """
        {} tiene 0 skills Tier 3 → por debajo del POOR_FIT_THRESHOLD (5).
        poor_fit debe ser False (o ausente/False-y).
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)

        with _base_patches(client):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert result.get("poor_fit") is not True, (
            f"poor_fit no debe ser True con evidence_map vacío, got: {result.get('poor_fit')}"
        )

    def test_poor_fit_key_always_present(self):
        """
        rewrite() siempre retorna la clave 'poor_fit', incluso con evidence_map vacío.
        Garantiza backward compatibility con el orquestador.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)

        with _base_patches(client):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert "poor_fit" in result, (
            "La clave 'poor_fit' falta en el resultado de rewrite() con evidence_map vacío"
        )

    def test_result_has_required_keys_with_empty_map(self):
        """
        Con evidence_map vacío, el resultado tiene todas las claves esperadas.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)

        with _base_patches(client):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        required = {"cv_text", "ats_score", "keywords_added", "attempts", "passed_ats", "poor_fit"}
        missing = required - result.keys()
        assert not missing, f"Claves faltantes en resultado de rewrite(): {missing}"


# ── B3: evidence_map vacío no rompe el retry ──────────────────────────────────
#
# RED antes del fix: build_evidence_map real devolvía poor_fit=True en algunos casos
#   → rewrite() salía con attempts=1 → test_retries_when_first_score_low fallaba
# GREEN: {} garantiza poor_fit=False → el loop de reintentos corre normalmente

class TestEmptyEvidenceMapRetry:
    """B3 — evidence_map vacío no impide los reintentos cuando ATS es bajo."""

    def test_retries_when_first_score_low_with_empty_map(self):
        """
        ATS 72 en el primer intento → debe haber ≥ 2 intentos.
        Con evidence_map vacío, poor_fit=False no bloquea el retry.
        """
        from agents.cv_rewriter import rewrite
        responses = iter([_LOW_SCORE_RESPONSE, _GOOD_RESPONSE])

        def _next_client():
            return _mock_claude(next(responses, _GOOD_RESPONSE))

        with (
            patch("agents.cv_rewriter._get_client", side_effect=_next_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value={}),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert result["attempts"] >= 2, (
            f"rewrite() no reintentó con ATS bajo y evidence_map vacío "
            f"(solo {result['attempts']} intento/s)"
        )
        assert result["passed_ats"] is True

    def test_max_attempts_reached_with_empty_map(self):
        """
        Si todos los intentos dan ATS bajo, se agotan los MAX_ATTEMPTS.
        passed_ats=False, attempts == MAX_ATTEMPTS.
        """
        from agents.cv_rewriter import rewrite, MAX_ATTEMPTS

        def _next_client():
            return _mock_claude(_LOW_SCORE_RESPONSE)

        with (
            patch("agents.cv_rewriter._get_client", side_effect=_next_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value={}),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert result["passed_ats"] is False
        assert result["attempts"] == MAX_ATTEMPTS, (
            f"Se esperaban {MAX_ATTEMPTS} intentos, got: {result['attempts']}"
        )


# ── B4: evidence_map vacío no rompe el stop-on-pass ───────────────────────────
#
# RED antes del fix: build_evidence_map real podía tardarse → segunda llamada
#   iniciaba → attempts=2 cuando se esperaba 1
# GREEN: {} es inmediato → el loop se detiene en el primer intento exitoso

class TestEmptyEvidenceMapStopOnPass:
    """B4 — evidence_map vacío no genera intentos extra cuando ATS ya pasó."""

    def test_stops_on_first_pass_with_empty_map(self):
        """
        ATS 97 en primer intento → attempts debe ser exactamente 1.
        El parche hace que build_evidence_map sea instantáneo y determinístico.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)

        with _base_patches(client):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert result["attempts"] == 1, (
            f"rewrite() hizo {result['attempts']} intentos cuando el primero ya pasó ATS. "
            f"Posible causa: build_evidence_map no estaba mockeado → API real → demora → race."
        )

    def test_ats_score_correct_on_first_pass(self):
        """
        El ATS score retornado coincide con lo que Claude respondió (97).
        Verifica que el parche no corrompe el parsing de la respuesta.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)

        with _base_patches(client):
            result = rewrite(_CV_DICT, _JOB, rama="C")

        assert result["ats_score"] == 97, (
            f"ATS score esperado 97, got: {result['ats_score']}"
        )
        assert result["passed_ats"] is True


# ── B5: evidence_mapper._get_client nunca se llama con el parche activo ───────
#
# Este es el comportamiento RAÍZ que causaba los 54 errores intermitentes.
# Si _get_client de evidence_mapper se llama, significa que el parche no está
# interceptando la llamada a build_evidence_map — la API real entraría en juego.

class TestNoRealApiCallsFromEvidenceMapper:
    """B5 — evidence_mapper._get_client nunca es invocado cuando el parche está activo."""

    def test_evidence_mapper_get_client_not_called_on_pass(self):
        """
        Con build_evidence_map mockeado, evidence_mapper._get_client no debe llamarse.
        Si se llama, el parche no está funcionando y la API real entraría.
        """
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        mock_em_client = MagicMock()

        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value={}),
            patch("agents.evidence_mapper._get_client", mock_em_client),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        mock_em_client.assert_not_called(), (
            "evidence_mapper._get_client fue llamado — el parche no está interceptando "
            "build_evidence_map correctamente"
        )

    def test_evidence_mapper_get_client_not_called_on_retry(self):
        """
        Con reintentos activos, evidence_mapper._get_client tampoco debe llamarse.
        """
        from agents.cv_rewriter import rewrite
        responses = iter([_LOW_SCORE_RESPONSE, _GOOD_RESPONSE])
        mock_em_client = MagicMock()

        def _next_client():
            return _mock_claude(next(responses, _GOOD_RESPONSE))

        with (
            patch("agents.cv_rewriter._get_client", side_effect=_next_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value={}),
            patch("agents.evidence_mapper._get_client", mock_em_client),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        mock_em_client.assert_not_called()

    def test_only_cv_rewriter_client_is_called(self):
        """
        La única llamada a la API que debe ocurrir es la del cv_rewriter.
        Verifica que el aislamiento es total: sin fugas hacia otros módulos.
        """
        from agents.cv_rewriter import rewrite
        cv_client = _mock_claude(_GOOD_RESPONSE)
        mock_em_client = MagicMock()

        with (
            patch("agents.cv_rewriter._get_client", return_value=cv_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value={}),
            patch("agents.evidence_mapper._get_client", mock_em_client),
        ):
            rewrite(_CV_DICT, _JOB, rama="C")

        # cv_rewriter._get_client sí debe haberse llamado (para el rewrite real)
        assert cv_client.messages.create.called, (
            "cv_rewriter no llamó a Claude — el test no está ejerciendo el código real"
        )
        # evidence_mapper._get_client NO debe haberse llamado
        mock_em_client.assert_not_called()
