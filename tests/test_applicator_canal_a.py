"""
Ciclo 19 RED→GREEN: Canal A smart fill
  - _get_field_question() extrae pregunta de placeholder / aria-label / label
  - _generate_field_answer() llama a Claude con la pregunta + CV + JD
  - _fill_free_text_fields() detecta campos vacíos y los llena

Ciclo 20 RED→GREEN: send_screenshot_for_approval_sync
  - envía foto con urllib.request (sin asyncio)
  - fallback a texto si no hay imagen

Ciclo 21 RED→GREEN: _apply_linkedin() v2
  - acepta cv_text y job_description
  - llama _fill_free_text_fields() en cada paso del modal
  - HITL_ENABLED=True: screenshot → Telegram → SI → Submit
  - HITL_ENABLED=True: screenshot → Telegram → NO → browser abierto
  - HITL_ENABLED=False: submit directo sin Telegram
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB_A = {
    "cargo":   "Paid Media Manager",
    "empresa": "Rappi",
    "url":     "https://www.linkedin.com/jobs/view/1234567890",
    "rama":    "A",
    "score":   91,
}
_CV = "Lorena Ruiz. 14 años en paid media. Meta Ads, Google Ads. Presupuestos USD 240K."
_JD = "We need a Paid Media Manager with Meta Ads and Google Ads experience."


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_claude(text: str):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _mock_field(placeholder="", aria_label="", field_id="", value="", visible=True):
    field = MagicMock()
    field.is_visible.return_value = visible
    field.get_attribute.side_effect = lambda attr, **kw: {
        "placeholder": placeholder,
        "aria-label":  aria_label,
        "id":          field_id,
    }.get(attr, "")
    field.input_value.return_value = value
    field.text_content.return_value = value
    return field


def _mock_linkedin_ctx(submit_visible=True):
    """Mock completo de sync_playwright para LinkedIn Easy Apply."""
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/jobs/view/123"

    # Submit button behavior controlado por parámetro
    submit_loc = MagicMock()
    submit_loc.is_visible.return_value = submit_visible

    # Locator genérico retorna visible=True para Easy Apply btn y modal
    generic_loc = MagicMock()
    generic_loc.first.is_visible.return_value = True
    generic_loc.first.wait_for = MagicMock()
    generic_loc.first = submit_loc if submit_visible else generic_loc.first

    # Locator para "already applied" texts → is_visible=False (trabajo sin aplicar en tests)
    _already_applied_texts = {"solicitud enviada", "application submitted", "ya aplicaste"}
    not_applied_loc = MagicMock()
    not_applied_loc.first.is_visible.return_value = False

    def _locator_side_effect(selector, **kwargs):
        sel_lower = str(selector).lower()
        if any(t in sel_lower for t in _already_applied_texts):
            return not_applied_loc
        return generic_loc

    mock_page.locator.side_effect = _locator_side_effect

    mock_page.screenshot.return_value = None
    mock_page.wait_for_event.side_effect = Exception("closed")

    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx

    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__.return_value = mock_pw_instance
    mock_pw_cm.__exit__.return_value = False

    return mock_pw_cm, mock_ctx, mock_page


# ── Ciclo 19: _get_field_question ─────────────────────────────────────────────

class TestGetFieldQuestion:

    def test_returns_placeholder_when_present(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field(placeholder="¿Por qué quieres este cargo?")
        result = _get_field_question(page, field)
        assert "cargo" in result or "Por qué" in result

    def test_returns_aria_label_when_no_placeholder(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field(aria_label="Years of experience")
        result = _get_field_question(page, field)
        assert "experience" in result.lower() or "Years" in result

    def test_returns_string_when_no_context(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field()
        page.locator.return_value.first.is_visible.return_value = False
        result = _get_field_question(page, field)
        assert isinstance(result, str)

    def test_does_not_raise_on_exception(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = MagicMock()
        field.get_attribute.side_effect = Exception("playwright error")
        result = _get_field_question(page, field)
        assert isinstance(result, str)


# ── Ciclo 19: _generate_field_answer ──────────────────────────────────────────

class TestGenerateFieldAnswer:

    def test_returns_string(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("14 años de experiencia en paid media.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _generate_field_answer("Años de experiencia", _CV, _JD)
        assert isinstance(result, str)

    def test_max_150_chars(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("x" * 300)
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _generate_field_answer("Pregunta", _CV, _JD)
        assert len(result) <= 150

    def test_returns_empty_when_anthropic_none(self):
        from agents.applicator import _generate_field_answer
        with patch("agents.applicator.anthropic", None):
            result = _generate_field_answer("Pregunta", _CV, _JD)
        assert result == ""

    def test_prompt_includes_question(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("respuesta")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_field_answer("¿Cuál es tu mayor fortaleza?", _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "fortaleza" in call_args

    def test_prompt_includes_cv_text(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("respuesta")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_field_answer("Pregunta", _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "Lorena Ruiz" in call_args or "paid media" in call_args.lower()

    # ── Ciclo 22 ──────────────────────────────────────────────────────────────

    def test_returns_empty_string_when_claude_raises(self):
        """Si la API de Anthropic lanza excepción, retorna '' sin propagar.
        El perfil candidata se parchea vacío para forzar el path de Claude."""
        from agents.applicator import _generate_field_answer
        boom_client = MagicMock()
        boom_client.messages.create.side_effect = Exception("API rate limit")
        with (
            patch("agents.applicator._load_candidate_profile", return_value={}),
            patch("agents.applicator.anthropic") as mock_ant,
        ):
            mock_ant.Anthropic.return_value = boom_client
            result = _generate_field_answer("¿Cuántos años de experiencia?", _CV, _JD)
        assert result == ""


# ── Ciclo 19: _fill_free_text_fields ──────────────────────────────────────────

class TestFillFreeTextFields:

    def test_returns_zero_when_no_fields(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        page.locator.return_value.all.return_value = []
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result == 0

    def test_fills_visible_empty_field(self):
        from agents.applicator import _fill_free_text_fields
        field = _mock_field(placeholder="¿Por qué este cargo?", value="")
        page  = MagicMock()
        page.locator.return_value.all.return_value = [field]
        client = _mock_claude("Me apasiona el paid media.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result >= 1
        field.fill.assert_called_once()

    def test_skips_already_filled_field(self):
        from agents.applicator import _fill_free_text_fields
        field = _mock_field(placeholder="¿Por qué?", value="Ya tengo texto")
        page  = MagicMock()
        page.locator.return_value.all.return_value = [field]
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            _fill_free_text_fields(page, _CV, _JD)
        field.fill.assert_not_called()

    def test_returns_zero_when_anthropic_none(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        with patch("agents.applicator.anthropic", None):
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result == 0

    def test_does_not_raise_on_playwright_error(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        page.locator.side_effect = Exception("playwright crash")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            result = _fill_free_text_fields(page, _CV, _JD)
        assert isinstance(result, int)

    # ── Ciclo 23 ──────────────────────────────────────────────────────────────

    def test_does_not_fill_when_answer_is_empty(self):
        """Si Claude devuelve '' (excepción o sin anthropic), field.fill() NO se llama.
        El perfil candidata se parchea vacío para forzar el path de Claude."""
        from agents.applicator import _fill_free_text_fields
        field = _mock_field(placeholder="¿Por qué este cargo?", value="")
        page  = MagicMock()
        page.locator.return_value.all.return_value = [field]
        # Claude responde vacío; perfil vacío para no hacer match antes
        with (
            patch("agents.applicator._load_candidate_profile", return_value={}),
            patch("agents.applicator.anthropic") as mock_ant,
        ):
            mock_ant.Anthropic.return_value = _mock_claude("")
            _fill_free_text_fields(page, _CV, _JD)
        field.fill.assert_not_called()


# ── Ciclo 20: send_screenshot_for_approval_sync ───────────────────────────────

class TestSendScreenshotSync:

    def test_sends_photo_when_image_exists(self, tmp_path):
        img = tmp_path / "shot.png"
        img.write_bytes(b"\x89PNG\r\n")
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"{}")))
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("agents.telegram_hitl.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                send_screenshot_for_approval_sync(str(img), _JOB_A)
        assert mock_open.called
        req_arg = mock_open.call_args[0][0]
        assert "sendPhoto" in req_arg.full_url

    def test_sends_text_when_no_image(self):
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"{}")))
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("agents.telegram_hitl.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                send_screenshot_for_approval_sync("no_existe.png", _JOB_A)
        req_arg = mock_open.call_args[0][0]
        assert "sendMessage" in req_arg.full_url

    def test_does_not_raise_on_network_error(self):
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        with patch("agents.telegram_hitl.urllib.request.urlopen", side_effect=Exception("timeout")):
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                try:
                    send_screenshot_for_approval_sync("no.png", _JOB_A)
                except Exception:
                    pytest.fail("send_screenshot_for_approval_sync no debe propagar excepciones")


# ── Ciclo 21: _apply_linkedin() v2 ────────────────────────────────────────────

class TestApplyLinkedinCanalAV2:

    # ── Ciclo 25 ──────────────────────────────────────────────────────────────

    # ── Ciclo 26 ──────────────────────────────────────────────────────────────

    def test_no_easy_apply_calls_apply_web_AFTER_playwright_context_closes(self):
        """
        Cuando no hay Easy Apply, _apply_web debe llamarse DESPUÉS de que el
        contexto sync_playwright haya cerrado — no desde adentro.
        Verifica que _apply_web recibe la llamada y puede abrir su propio
        sync_playwright sin conflicto de asyncio.
        """
        from agents.applicator import apply

        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/jobs/view/123"

        no_btn = MagicMock()
        no_btn.is_visible.return_value = False
        mock_page.locator.return_value.first = no_btn
        # get_by_role también debe devolver is_visible=False para simular ausencia del botón
        mock_page.get_by_role.return_value.first.is_visible.return_value = False
        # .filter(has_text=...).first.wait_for() debe lanzar para indicar timeout sin botón
        mock_page.locator.return_value.filter.return_value.first.wait_for.side_effect = Exception("Timeout: no button")
        mock_page.locator.return_value.filter.return_value.first.is_visible.return_value = False

        mock_ctx = MagicMock()
        mock_ctx.pages = [mock_page]

        pw_exited = []  # rastrea si __exit__ fue llamado antes de _apply_web

        class TrackingPWCM:
            def __enter__(self_cm):
                return MagicMock(
                    chromium=MagicMock(
                        launch_persistent_context=MagicMock(return_value=mock_ctx)
                    )
                )
            def __exit__(self_cm, *args):
                pw_exited.append(True)
                return False

        apply_web_called_after_exit = []

        def fake_apply_web(job, pdf_path):
            apply_web_called_after_exit.append(bool(pw_exited))
            return {"enviado": False, "canal": "B", "url": job["url"], "mensaje": "ok"}

        with (
            patch("agents.applicator.sync_playwright", return_value=TrackingPWCM()),
            patch("agents.applicator._apply_web", side_effect=fake_apply_web),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False)

        # _apply_web fue llamado DESPUÉS de que sync_playwright hizo __exit__
        assert apply_web_called_after_exit == [True], (
            "_apply_web fue llamado DENTRO del contexto Playwright (bug asyncio)"
        )
        assert result["canal"] == "B"

    def test_no_easy_apply_button_falls_back_to_canal_b(self):
        """
        Si ningún selector de Easy Apply está visible, _apply_linkedin
        delega en _apply_web y el resultado tiene canal 'B'.
        """
        from agents.applicator import apply
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/jobs/view/123"

        # Todos los is_visible() devuelven False → ningún botón encontrado
        no_btn = MagicMock()
        no_btn.is_visible.return_value = False
        mock_page.locator.return_value.first = no_btn
        # get_by_role también debe devolver is_visible=False
        mock_page.get_by_role.return_value.first.is_visible.return_value = False
        # .filter(has_text=...).first.wait_for() debe lanzar para indicar timeout sin botón
        mock_page.locator.return_value.filter.return_value.first.wait_for.side_effect = Exception("Timeout: no button")
        mock_page.locator.return_value.filter.return_value.first.is_visible.return_value = False

        mock_ctx = MagicMock()
        mock_ctx.pages = [mock_page]

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx

        mock_pw_cm = MagicMock()
        mock_pw_cm.__enter__.return_value = mock_pw_instance
        mock_pw_cm.__exit__.return_value = False

        canal_b_result = {
            "enviado": False, "canal": "B",
            "url": _JOB_A["url"], "mensaje": "Browser abierto Canal B",
        }

        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator._apply_web", return_value=canal_b_result) as mock_web,
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False)

        mock_web.assert_called_once()
        assert result["canal"] == "B"

    def test_accepts_cv_text_and_job_description(self):
        from agents.applicator import apply
        result = apply(_JOB_A, "cv.pdf", dry_run=True, cv_text=_CV, job_description=_JD)
        assert result["canal"] == "A"

    def test_dry_run_does_not_call_fill_free_text(self):
        from agents.applicator import apply
        with patch("agents.applicator._fill_free_text_fields") as mock_fill:
            apply(_JOB_A, "cv.pdf", dry_run=True, cv_text=_CV, job_description=_JD)
        mock_fill.assert_not_called()

    def test_hitl_enabled_sends_screenshot_before_submit(self):
        from agents.applicator import apply
        mock_pw_cm, _, mock_page = _mock_linkedin_ctx()
        mock_page.locator.return_value.first.is_visible.return_value = True
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync") as mock_shot,
            patch("agents.applicator.wait_for_approval", return_value=True),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        mock_shot.assert_called_once()

    def test_hitl_si_returns_enviado_true(self):
        from agents.applicator import apply
        mock_pw_cm, _, mock_page = _mock_linkedin_ctx()
        mock_page.locator.return_value.first.is_visible.return_value = True
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync"),
            patch("agents.applicator.wait_for_approval", return_value=True),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        assert result["enviado"] is True
        assert result["canal"] == "A"

    def test_hitl_no_returns_enviado_false(self):
        from agents.applicator import apply
        mock_pw_cm, _, mock_page = _mock_linkedin_ctx()
        mock_page.locator.return_value.first.is_visible.return_value = True
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync"),
            patch("agents.applicator.wait_for_approval", return_value=False),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        assert result["enviado"] is False
        assert "HITL" in result["mensaje"] or "cancel" in result["mensaje"].lower()

    # ── Ciclo 24 ──────────────────────────────────────────────────────────────

    def test_login_wall_returns_enviado_false_with_message(self):
        """
        Si LinkedIn redirige a /login o /authwall, el agente retorna
        enviado=False con un mensaje claro — sin crash.
        """
        from agents.applicator import apply
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/login"  # sesión expirada

        mock_ctx = MagicMock()
        mock_ctx.pages = [mock_page]

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx

        mock_pw_cm = MagicMock()
        mock_pw_cm.__enter__.return_value = mock_pw_instance
        mock_pw_cm.__exit__.return_value = False

        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = True
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False)

        assert result["enviado"] is False
        assert result["canal"] == "A"
        assert "sesión" in result["mensaje"].lower() or "login" in result["mensaje"].lower()

    def test_hitl_disabled_no_screenshot_sent(self):
        from agents.applicator import apply
        mock_pw_cm, _, mock_page = _mock_linkedin_ctx()
        mock_page.locator.return_value.first.is_visible.return_value = True
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync") as mock_shot,
            patch("agents.applicator.wait_for_approval") as mock_wait,
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED             = False
            mock_cfg.HITL_TIMEOUT_S           = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            mock_cfg.APPLICANT_PHONE          = "+57 315 256 1884"
            mock_cfg.APPLICANT_EMAIL          = "test@test.com"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        mock_shot.assert_not_called()
        mock_wait.assert_not_called()
        assert result["enviado"] is True


# ── Ciclo 27: candidate_profile.json — respuestas estructuradas ───────────────

_PROFILE = {
    "salary_text":              "6.500.000 COP / 2.300 USD mensuales",
    "salary_cop_monthly":       "6500000",
    "salary_usd_monthly":       "2300",
    "city":                     "Bogotá D.C., Colombia",
    "country":                  "Colombia",
    "willing_to_travel":        "Sí",
    "willing_to_relocate":      "No",
    "availability":             "Inmediata",
    "has_vehicle":              "Sí",
    "currently_employed":       "Sí",
    "work_authorization":       "Sí",
    "requires_visa_sponsorship": "No",
    "night_shifts":             "No, disponible lunes a viernes en horario regular",
    "hybrid_available":         "Sí",
    "background_check":         "Sí",
    "english_level":            "C2 - Proficiencia completa",
    "years_experience":         "14",
}


class TestMatchProfileQuestion:

    def test_salary_question_returns_profile_answer(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Cuál es tu aspiración salarial?", _PROFILE)
        # Debe devolver número COP puro — el campo numérico de LinkedIn lo acepta
        assert ans == _PROFILE["salary_cop_monthly"]

    def test_pretension_keyword_matches_salary(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("Pretensión económica mensual", _PROFILE)
        assert ans == _PROFILE["salary_cop_monthly"]

    def test_city_question_returns_bogota(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿En qué ciudad vives actualmente?", _PROFILE)
        assert "Bogotá" in ans

    def test_travel_question_returns_si(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Estás dispuesto a viajar?", _PROFILE)
        assert ans == "Sí"

    def test_relocation_question_returns_no(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Puedes reubicarte a otra ciudad?", _PROFILE)
        assert ans == "No"

    def test_availability_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Cuándo podría comenzar a trabajar con nosotros?", _PROFILE)
        assert ans == "Inmediata"

    def test_background_check_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question(
            "¿Estaría dispuesto a someterse a una verificación de antecedentes?", _PROFILE
        )
        assert ans == "Sí"

    def test_english_question_returns_level(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Cuál es tu nivel de inglés?", _PROFILE)
        assert "C2" in ans

    def test_vehicle_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Tienes vehículo propio?", _PROFILE)
        assert ans == "Sí"

    def test_night_shifts_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Disponible para trabajar en turnos nocturnos?", _PROFILE)
        assert "No" in ans

    def test_hybrid_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Puede trabajar en modalidad híbrida?", _PROFILE)
        assert ans == "Sí"

    def test_visa_sponsorship_question(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Requiere patrocinio de visa en el futuro?", _PROFILE)
        assert ans == "No"

    def test_unknown_question_returns_empty_string(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Tienes mascota?", _PROFILE)
        assert ans == ""

    def test_matching_is_case_insensitive(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("SALARIO ESPERADO", _PROFILE)
        assert ans == _PROFILE["salary_cop_monthly"]

    def test_empty_profile_returns_empty_string(self):
        from agents.applicator import _match_profile_question
        ans = _match_profile_question("¿Cuál es tu aspiración salarial?", {})
        assert ans == ""


class TestGenerateFieldAnswerWithProfile:

    def test_profile_answer_used_without_calling_claude(self):
        """Cuando la pregunta coincide con el perfil, Claude NO se llama."""
        from agents.applicator import _generate_field_answer
        with (
            patch("agents.applicator._load_candidate_profile", return_value=_PROFILE),
            patch("agents.applicator.anthropic") as mock_ant,
        ):
            result = _generate_field_answer("¿Cuál es tu aspiración salarial?", _CV, _JD)
        mock_ant.Anthropic.assert_not_called()
        assert result == _PROFILE["salary_cop_monthly"]

    def test_falls_back_to_claude_for_unknown_question(self):
        """Para preguntas no reconocidas, se llama Claude normalmente."""
        from agents.applicator import _generate_field_answer
        with (
            patch("agents.applicator._load_candidate_profile", return_value=_PROFILE),
            patch("agents.applicator.anthropic") as mock_ant,
        ):
            mock_ant.Anthropic.return_value = _mock_claude("Tengo experiencia en paid media.")
            result = _generate_field_answer("Describe tu experiencia más relevante", _CV, _JD)
        mock_ant.Anthropic.assert_called_once()
        assert isinstance(result, str)

    def test_profile_answer_truncated_to_150_chars(self):
        """Las respuestas del perfil también respetan el límite de 150 chars."""
        from agents.applicator import _generate_field_answer
        long_profile = {**_PROFILE, "salary_text": "X" * 200}
        with patch("agents.applicator._load_candidate_profile", return_value=long_profile):
            result = _generate_field_answer("¿Cuál es tu aspiración salarial?", _CV, _JD)
        assert len(result) <= 150
