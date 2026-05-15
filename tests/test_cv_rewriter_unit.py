"""
Ciclo 28 RED→GREEN: Tests unitarios del CV Rewriter con Claude mockeado.

Verifica que:
  - _rewrite_once pasa cargo, empresa y descripcion al prompt de Claude
  - _rewrite_once parsea correctamente <CV>, <ATS_SCORE>, <KEYWORDS>
  - rewrite() reintenta si ATS < 95%
  - rewrite() se detiene cuando ATS >= 95%
  - rewrite() retorna la forma correcta del dict
  - main.py pasa "descripcion" (no "description") al aplicar

Estos tests NO llaman la API real — usan Claude mockeado.
"""
import os
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
            "cargo":      "Digital Channels Consultant",
            "empresa":    "Avanti IT SAS",
            "fecha":      "August 2021 – April 2025",
            "descripcion": "Gestion de campanas digitales.",
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

Paid Media Specialist / Account Manager, LinkedIn Ads (via Teleperformance for LinkedIn Marketing Solutions)
Teleperformance (contract for LinkedIn Marketing Solutions)
February 2026 – Present  |  Bogotá, Hybrid
- Manage 300 B2B enterprise accounts across Latin America.

Amazon, Colombia
Campaign Planner Contractor
May 2025 – Feb 2026
- Managed tROAS campaigns for APAC brands including Narwal.

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
- Google Ads, Meta Ads y LinkedIn Ads
- Amazon Ads, DSP, AMC

LANGUAGES
Spanish (native)  |  English C2 Proficient (EF SET certified)
</CV>
<ATS_SCORE>97</ATS_SCORE>
<KEYWORDS>Media Planning, Google Ads, Meta Ads, LinkedIn Ads, Amazon Ads, presupuesto USD 200K</KEYWORDS>
"""

_LOW_SCORE_RESPONSE = """\
<CV>
LORENA RUIZ
lilian@lorena-ruiz.com

PROFESSIONAL PROFILE
Marketing professional.

WORK EXPERIENCE

Avanti IT SAS
August 2021 – April 2025
- Digital marketing campaigns.

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
- Marketing

LANGUAGES
Spanish
</CV>
<ATS_SCORE>72</ATS_SCORE>
<KEYWORDS>marketing</KEYWORDS>
"""


def _mock_claude_response(text: str):
    """Retorna un mock del Anthropic client que devuelve `text` como respuesta."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ── Ciclo 28a: _rewrite_once pasa el job al prompt ────────────────────────────

class TestRewriteOncePrompt:
    """_rewrite_once incluye cargo, empresa y descripcion en el mensaje al LLM."""

    def _call_rewrite_once(self, mock_client):
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="C")
        with patch("agents.cv_rewriter._get_client", return_value=mock_client):
            return _rewrite_once(cv_plain, _JOB, previous_score=None)

    def test_prompt_includes_cargo(self):
        """El cargo del trabajo debe aparecer en el prompt enviado a Claude."""
        client = _mock_claude_response(_GOOD_RESPONSE)
        self._call_rewrite_once(client)
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "Media Planning Manager" in user_content, (
            f"'Media Planning Manager' (cargo) no encontrado en el prompt.\n"
            f"Prompt:\n{user_content[:500]}"
        )

    def test_prompt_includes_empresa(self):
        """La empresa debe aparecer en el prompt."""
        client = _mock_claude_response(_GOOD_RESPONSE)
        self._call_rewrite_once(client)
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "OMD Colombia" in user_content, (
            f"'OMD Colombia' (empresa) no encontrado en el prompt.\n"
            f"Prompt:\n{user_content[:500]}"
        )

    def test_prompt_includes_descripcion(self):
        """La descripcion del trabajo debe aparecer en el prompt."""
        client = _mock_claude_response(_GOOD_RESPONSE)
        self._call_rewrite_once(client)
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "Google Ads" in user_content, (
            f"La descripción del trabajo no llegó al prompt de Claude.\n"
            f"Prompt:\n{user_content[:500]}"
        )

    def test_prompt_includes_cv_text(self):
        """El CV base debe estar en el prompt."""
        client = _mock_claude_response(_GOOD_RESPONSE)
        self._call_rewrite_once(client)
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "LORENA RUIZ" in user_content, (
            "El texto del CV no está en el prompt enviado a Claude."
        )


# ── Ciclo 28b: _rewrite_once parsea la respuesta correctamente ────────────────

class TestRewriteOnceParsing:
    """_rewrite_once extrae correctamente CV, ATS score y keywords de la respuesta."""

    def _run(self, response_text: str) -> dict:
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="C")
        client = _mock_claude_response(response_text)
        with patch("agents.cv_rewriter._get_client", return_value=client):
            return _rewrite_once(cv_plain, _JOB, previous_score=None)

    def test_parses_cv_text(self):
        result = self._run(_GOOD_RESPONSE)
        assert "LORENA RUIZ" in result["cv_text"], "cv_text no fue extraído del bloque <CV>"

    def test_parses_ats_score(self):
        result = self._run(_GOOD_RESPONSE)
        assert result["ats_score"] == 97, f"ATS score incorrecto: {result['ats_score']}"

    def test_parses_keywords(self):
        result = self._run(_GOOD_RESPONSE)
        assert "Media Planning" in result["keywords_added"], (
            f"Keywords no parseadas: {result['keywords_added']}"
        )

    def test_returns_cv_plain_when_no_cv_tag(self):
        """Si Claude no usa el tag <CV>, retorna el texto base sin romper."""
        broken_response = "<ATS_SCORE>70</ATS_SCORE><KEYWORDS>nada</KEYWORDS>"
        result = self._run(broken_response)
        assert result["cv_text"]  # no vacío
        assert result["ats_score"] == 70

    def test_fix_static_fields_applied(self):
        """_fix_static_fields se aplica: el email correcto aparece en el resultado."""
        result = self._run(_GOOD_RESPONSE)
        assert "lilian@lorena-ruiz.com" in result["cv_text"], (
            "_fix_static_fields no se aplicó — email no encontrado"
        )


# ── Ciclo 28c: rewrite() gestiona reintentos ──────────────────────────────────

class TestRewriteRetryLogic:
    """rewrite() reintenta hasta MAX_ATTEMPTS cuando ATS < 95%, se detiene cuando >= 95%."""

    def _run_rewrite(self, side_effects: list[str]) -> dict:
        """Corre rewrite() con respuestas sucesivas de Claude."""
        from agents.cv_rewriter import rewrite
        clients_iter = iter([_mock_claude_response(r) for r in side_effects])

        def _fake_get_client():
            try:
                return next(clients_iter)
            except StopIteration:
                return _mock_claude_response(_GOOD_RESPONSE)

        with (
            patch("agents.cv_rewriter._get_client", side_effect=_fake_get_client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
        ):
            return rewrite(_CV_DICT, _JOB, rama="C")

    def test_returns_dict_with_correct_keys(self):
        result = self._run_rewrite([_GOOD_RESPONSE])
        for key in ("cv_text", "ats_score", "keywords_added", "attempts", "passed_ats"):
            assert key in result, f"Clave '{key}' falta en resultado de rewrite()"

    def test_passed_ats_true_when_score_gte_95(self):
        result = self._run_rewrite([_GOOD_RESPONSE])  # ATS 97
        assert result["passed_ats"] is True
        assert result["ats_score"] == 97

    def test_passed_ats_false_when_score_lt_95(self):
        result = self._run_rewrite([_LOW_SCORE_RESPONSE, _LOW_SCORE_RESPONSE, _LOW_SCORE_RESPONSE])
        assert result["passed_ats"] is False
        assert result["ats_score"] == 72

    def test_stops_on_first_pass(self):
        """Si el primer intento pasa 95%, no debe haber un segundo intento."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude_response(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="C")
        assert result["attempts"] == 1, (
            f"rewrite() intentó {result['attempts']} veces cuando el primer intento ya pasó ATS"
        )

    def test_retries_when_first_score_low(self):
        """Si el primer intento no pasa, rewrite() debe intentar más de una vez."""
        result = self._run_rewrite([_LOW_SCORE_RESPONSE, _GOOD_RESPONSE])
        assert result["attempts"] >= 2, (
            f"rewrite() no reintentó cuando el primer ATS era bajo (solo {result['attempts']} intento/s)"
        )
        assert result["passed_ats"] is True


# ── Ciclo 28d: Bug main.py — descripcion vs description ───────────────────────

class TestMainJobDescriptionKey:
    """main.py debe pasar job['descripcion'] (no 'description') al aplicar."""

    def test_process_job_passes_descripcion_to_applicator(self):
        """
        _process_job() debe pasar job['descripcion'] como job_description al Applicator.
        Bug encontrado: job.get('description', '') — clave incorrecta, siempre devuelve ''.
        """
        from main import _process_job

        captured = {}

        def _fake_aplicar(job, pdf_path, dry_run=False, cv_text="", job_description=""):
            captured["job_description"] = job_description
            return {"enviado": False, "canal": "C", "mensaje": "dry_run"}

        def _fake_analyze(cv, job, rama):
            return {"score": 90, "passed": True, "threshold": 85, "keywords": []}

        def _fake_rewrite(cv, job, rama, **kwargs):
            return {
                "cv_text": "LORENA RUIZ\n...",
                "ats_score": 97,
                "keywords_added": ["paid media"],
                "attempts": 1,
                "passed_ats": True,
            }

        def _fake_audit(job, cv_text):
            return {
                "audit_score": 96,
                "verdict": "PASS",
                "passed_audit": True,
                "keywords_missing": [],
                "feedback_to_rewriter": "",
            }

        def _fake_generate(cv_text, job):
            return "/tmp/fake_cv.pdf"

        def _fake_register(*args, **kwargs):
            pass

        with (
            patch("main.analyze",   _fake_analyze),
            patch("main.rewrite",   _fake_rewrite),
            patch("main.audit",     _fake_audit),
            patch("main.generate",  _fake_generate),
            patch("main.aplicar",   _fake_aplicar),
            patch("main.register",  _fake_register),
        ):
            _process_job(_CV_DICT, _JOB, rama="C", dry_run=True)

        assert captured.get("job_description") == _JOB["descripcion"], (
            f"_process_job pasó job_description='{captured.get('job_description')[:50]}...' "
            f"en vez del contenido real de job['descripcion'].\n"
            f"Posible causa: main.py usa job.get('description') en vez de job.get('descripcion')."
        )
