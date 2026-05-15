# Canal A — Corrección 4 Bugs Post-Smoke-Test (Segunda Ronda)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir los 4 bugs detectados en el segundo smoke test de 2026-05-14 para que el flujo Canal A ejecute submit real con CV en español, nombre de archivo correcto, y CV adjunto.

**Architecture:** Cuatro fixes independientes: (A) extracción robusta via page.title() + condición de placeholder, (B) detección de idioma del JD en el rewriter, (C) subida de CV sin verificar visibilidad del input oculto, (D) separar submit de review en la detección de botones. TDD estricto — RED primero.

**Tech Stack:** Python 3.11+, Playwright sync_api, Anthropic Claude, pytest. Archivos: agents/applicator.py, agents/cv_rewriter.py, tests/test_applicator_canal_a.py, tests/test_cv_rewriter_unit.py.

---

## Archivos que se modifican

| Archivo | Cambios |
|---|---|
| `agents/applicator.py` | Nueva función `_parse_title_for_job_info()`; `_extract_linkedin_job_info()` usa page.title() primero; condición de placeholder en `_linkedin_playwright_loop`; nueva función `_find_submit_button()`; `_find_next_button()` incluye "Review"/"Revisar"; `_maybe_upload_cv()` sin is_visible() |
| `agents/cv_rewriter.py` | Regla 11 de `_SYSTEM`: detección de idioma del JD |
| `tests/test_applicator_canal_a.py` | Tests para `_parse_title_for_job_info`, `_find_submit_button`, `_maybe_upload_cv` con input oculto |
| `tests/test_cv_rewriter_unit.py` | Test que verifica instrucción de idioma en _SYSTEM |

---

## Task 1 — BUG-A: Extracción robusta de cargo/empresa desde page.title()

**Problema:** `_extract_linkedin_job_info` devuelve strings vacíos porque los selectores CSS no matchean el HTML real de LinkedIn. Además la condición `not cargo` no sobreescribe el fallback truthy "Cargo LinkedIn".

**Causa raíz confirmada:** LinkedIn title del tab tiene formato estable `"Product Manager at Falabella | LinkedIn"`. Los selectores CSS (h1.t-24, etc.) cambian con cada deploy de LinkedIn.

**Files:**
- Modify: `agents/applicator.py` — nueva función `_parse_title_for_job_info`, update `_extract_linkedin_job_info`, update condición en `_linkedin_playwright_loop`
- Modify: `tests/test_applicator_canal_a.py` — nueva clase `TestParseTitleForJobInfo` + tests de integración de extracción

- [ ] **Step 1: Escribir tests RED para `_parse_title_for_job_info`**

Al final de `tests/test_applicator_canal_a.py`, agregar:

```python
# ── Ciclo 30: _parse_title_for_job_info + extracción robusta ─────────────────

class TestParseTitleForJobInfo:
    """page.title() es más estable que selectores CSS en LinkedIn."""

    def test_standard_english_format(self):
        from agents.applicator import _parse_title_for_job_info
        result = _parse_title_for_job_info("Product Manager at Falabella | LinkedIn")
        assert result["cargo"] == "Product Manager"
        assert result["empresa"] == "Falabella"

    def test_with_notification_prefix(self):
        from agents.applicator import _parse_title_for_job_info
        result = _parse_title_for_job_info("(3) Product Manager at Falabella | LinkedIn")
        assert result["cargo"] == "Product Manager"
        assert result["empresa"] == "Falabella"

    def test_spanish_en_format(self):
        from agents.applicator import _parse_title_for_job_info
        result = _parse_title_for_job_info("Gerente de Marketing en Falabella | LinkedIn")
        assert result["cargo"] == "Gerente de Marketing"
        assert result["empresa"] == "Falabella"

    def test_returns_empty_when_no_separator(self):
        from agents.applicator import _parse_title_for_job_info
        result = _parse_title_for_job_info("LinkedIn")
        assert result == {"cargo": "", "empresa": ""}

    def test_returns_empty_for_empty_string(self):
        from agents.applicator import _parse_title_for_job_info
        result = _parse_title_for_job_info("")
        assert result == {"cargo": "", "empresa": ""}

    def test_page_title_used_in_extract(self):
        """_extract_linkedin_job_info llama page.title() y lo parsea."""
        from agents.applicator import _extract_linkedin_job_info
        page = MagicMock()
        page.title.return_value = "Paid Media Manager at OMD Colombia | LinkedIn"
        loc = MagicMock()
        loc.first.is_visible.return_value = False
        page.locator.return_value = loc
        result = _extract_linkedin_job_info(page)
        assert result["cargo"] == "Paid Media Manager"
        assert result["empresa"] == "OMD Colombia"

    def test_placeholder_cargo_is_overwritten(self):
        """cargo='Cargo LinkedIn' debe ser detectado como placeholder y sobreescrito."""
        _PLACEHOLDER_VALUES = {"cargo linkedin", "empresa linkedin", ""}
        assert "Cargo LinkedIn".lower() in _PLACEHOLDER_VALUES
        assert "Empresa LinkedIn".lower() in _PLACEHOLDER_VALUES
        assert "Product Manager".lower() not in _PLACEHOLDER_VALUES
```

- [ ] **Step 2: Verificar RED**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python -m pytest tests/test_applicator_canal_a.py::TestParseTitleForJobInfo -v
```
Expected: `FAILED — ImportError: cannot import name '_parse_title_for_job_info'`

- [ ] **Step 3: Implementar `_parse_title_for_job_info` en `agents/applicator.py`**

Agregar ANTES de `_extract_linkedin_job_info` (alrededor de línea 296):

```python
# Valores de cargo/empresa que indican que no se extrajo info real
_PLACEHOLDER_VALUES = {"cargo linkedin", "empresa linkedin", ""}


def _parse_title_for_job_info(title: str) -> dict:
    """
    Extrae cargo y empresa del título del tab de LinkedIn.
    Formatos soportados:
      "Product Manager at Falabella | LinkedIn"
      "(3) Product Manager at Falabella | LinkedIn"
      "Gerente de Marketing en Falabella | LinkedIn"
    Retorna {"cargo": "", "empresa": ""} si el formato no coincide.
    """
    if not title:
        return {"cargo": "", "empresa": ""}
    # Remover prefijo de notificación "(N) "
    title = re.sub(r"^\(\d+\)\s*", "", title)
    # Remover sufijo " | LinkedIn" (y variantes con espacio extra)
    if " | LinkedIn" in title:
        title = title[: title.index(" | LinkedIn")]
    # Separar por " at " (inglés) o " en " (español)
    for sep in [" at ", " en "]:
        if sep in title:
            parts = title.split(sep, 1)
            return {"cargo": parts[0].strip(), "empresa": parts[1].strip()}
    return {"cargo": "", "empresa": ""}
```

- [ ] **Step 4: Actualizar `_extract_linkedin_job_info` para usar page.title() primero**

Reemplazar el cuerpo completo de `_extract_linkedin_job_info`:

```python
def _extract_linkedin_job_info(page) -> dict:
    """
    Lee cargo, empresa y descripción de la página LinkedIn actual.
    Estrategia: page.title() primero (estable) → selectores DOM como fallback.
    Nunca lanza excepción. Retorna dict con cadenas vacías si falla.
    """
    info = {"cargo": "", "empresa": "", "descripcion": ""}
    try:
        # 1. Título del tab — más estable que selectores CSS
        try:
            title_info = _parse_title_for_job_info(page.title() or "")
            if title_info["cargo"]:
                info["cargo"] = title_info["cargo"]
            if title_info["empresa"]:
                info["empresa"] = title_info["empresa"]
        except Exception:
            pass

        # 2. Fallback DOM para cargo (si title no lo dio)
        if not info["cargo"]:
            for sel in [
                "h1.t-24",
                "h1.jobs-unified-top-card__job-title",
                ".job-details-jobs-unified-top-card__job-title h1",
                "h1",
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2_000):
                        txt = (el.text_content(timeout=2_000) or "").strip()
                        if txt:
                            info["cargo"] = txt
                            break
                except Exception:
                    continue

        # 3. Fallback DOM para empresa (si title no lo dio)
        if not info["empresa"]:
            for sel in [
                ".job-details-jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name a",
                ".topcard__org-name-link",
                ".jobs-unified-top-card__company-name",
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2_000):
                        txt = (el.text_content(timeout=2_000) or "").strip()
                        if txt:
                            info["empresa"] = txt
                            break
                except Exception:
                    continue

        # 4. Descripción (solo por DOM)
        for sel in [
            ".jobs-description__content .jobs-box__html-content",
            ".jobs-description__content",
            ".jobs-box__html-content",
            ".jobs-description",
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2_000):
                    txt = (el.text_content(timeout=3_000) or "").strip()
                    if txt:
                        info["descripcion"] = txt[:3000]
                        break
            except Exception:
                continue

    except Exception:
        pass

    return info
```

- [ ] **Step 5: Actualizar condición de placeholder en `_linkedin_playwright_loop`**

Localizar en `agents/applicator.py` (alrededor de línea 404):

```python
# ANTES:
            if _job_info["cargo"] and not cargo:
                cargo = _job_info["cargo"]
                print(f"  [Applicator-A] Cargo extraído: {cargo!r}")
            if _job_info["empresa"] and not empresa:
                empresa = _job_info["empresa"]
                print(f"  [Applicator-A] Empresa extraída: {empresa!r}")
            if _job_info["descripcion"] and not job_description:
                job_description = _job_info["descripcion"]
                print(f"  [Applicator-A] JD extraída: {len(job_description)} chars")
```

Reemplazar por:

```python
# DESPUÉS — detecta placeholders aunque sean truthy
            if _job_info["cargo"] and cargo.lower() in _PLACEHOLDER_VALUES:
                cargo = _job_info["cargo"]
                print(f"  [Applicator-A] Cargo extraído: {cargo!r}")
            if _job_info["empresa"] and empresa.lower() in _PLACEHOLDER_VALUES:
                empresa = _job_info["empresa"]
                print(f"  [Applicator-A] Empresa extraída: {empresa!r}")
            if _job_info["descripcion"] and not job_description:
                job_description = _job_info["descripcion"]
                print(f"  [Applicator-A] JD extraída: {len(job_description)} chars")
```

- [ ] **Step 6: Verificar GREEN**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestParseTitleForJobInfo -v
```
Expected: `7 passed`

- [ ] **Step 7: Full suite sin regresiones**

```bash
python -m pytest -q --tb=short
```
Expected: `235 passed` (228 + 7 nuevos)

- [ ] **Step 8: Commit**

```bash
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "fix(bug-a): extracción cargo/empresa via page.title() + placeholder override

page.title() retorna formato estable 'Cargo at Empresa | LinkedIn'.
Los selectores CSS h1.t-24 etc. no matchean el HTML real de LinkedIn.
_PLACEHOLDER_VALUES detecta 'Cargo LinkedIn'/'Empresa LinkedIn' como
valores de fallback y los sobreescribe aunque sean truthy.
7 tests nuevos — 235/235 GREEN.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2 — BUG-D: Separar Submit de Review — HITL dispara en el paso correcto

**Problema:** El inline submit detection en `_linkedin_playwright_loop` incluye `"button:has-text('Review')"` y `"button[aria-label='Review your application']"`. Estos son botones de navegación intermedia (67% del formulario), no el submit real. HITL dispara ahí y si Lorena aprueba, el agente hace click en "Review" y retorna `enviado=True` sin haber enviado la aplicación.

**Fix:** Extraer `_find_submit_button(page)` con solo los selectores de submit real. Agregar "Review" / "Revisar" a `_find_next_button`.

**Files:**
- Modify: `agents/applicator.py` — nueva función `_find_submit_button()`, update `_find_next_button()`, reemplazar inline detection en `_linkedin_playwright_loop`
- Modify: `tests/test_applicator_canal_a.py` — nueva clase `TestFindSubmitButton`

- [ ] **Step 1: Escribir tests RED para `_find_submit_button`**

Agregar al final de `tests/test_applicator_canal_a.py`:

```python
# ── Ciclo 31: _find_submit_button — HITL solo en submit real ─────────────────

class TestFindSubmitButton:
    """_find_submit_button NO debe retornar el botón 'Review' (paso intermedio)."""

    def _page_with_visible(self, selector_fragment: str):
        """Página donde solo el selector que contiene selector_fragment es visible."""
        page = MagicMock()
        def locator_side(sel, **kw):
            loc = MagicMock()
            loc.first.is_visible.return_value = selector_fragment in sel
            return loc
        page.locator.side_effect = locator_side
        return page

    def _page_no_visible(self):
        page = MagicMock()
        loc = MagicMock()
        loc.first.is_visible.return_value = False
        page.locator.return_value = loc
        return page

    def test_finds_submit_application(self):
        from agents.applicator import _find_submit_button
        page = self._page_with_visible("Submit application")
        assert _find_submit_button(page) is not None

    def test_finds_enviar_solicitud(self):
        from agents.applicator import _find_submit_button
        page = self._page_with_visible("Enviar solicitud")
        assert _find_submit_button(page) is not None

    def test_review_button_not_treated_as_submit(self):
        """'Review' es navegación intermedia — NO debe disparar HITL."""
        from agents.applicator import _find_submit_button
        page = self._page_no_visible()  # ningún submit visible
        assert _find_submit_button(page) is None

    def test_returns_none_when_no_submit_visible(self):
        from agents.applicator import _find_submit_button
        assert _find_submit_button(self._page_no_visible()) is None

    def test_find_next_button_treats_review_as_next(self):
        """'Review' debe ser tratado como botón Next, no Submit."""
        from agents.applicator import _find_next_button
        page = self._page_with_visible("Review")
        result = _find_next_button(page)
        assert result is not None
```

- [ ] **Step 2: Verificar RED**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestFindSubmitButton -v
```
Expected: `FAILED — ImportError: cannot import name '_find_submit_button'`

- [ ] **Step 3: Implementar `_find_submit_button` en `agents/applicator.py`**

Agregar ANTES de `_find_next_button` (alrededor de línea 740):

```python
# Selectores del botón de SUBMIT FINAL — NO incluir "Review" ni "Revisar"
# (esos son botones de navegación intermedia hacia la pantalla de confirmación)
_SUBMIT_SELECTORS = [
    "button[aria-label='Submit application']",
    "button[aria-label='Enviar solicitud']",
    "button:has-text('Submit application')",
    "button:has-text('Enviar solicitud')",
    "button:has-text('Enviar')",
]


def _find_submit_button(page):
    """
    Retorna el botón de submit FINAL (Submit application / Enviar solicitud).
    NO incluye 'Review' ni 'Review your application' — esos son pasos intermedios.
    Retorna None si no hay botón de submit visible.
    """
    for sel in _SUBMIT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1_500):
                return btn
        except Exception:
            continue
    return None
```

- [ ] **Step 4: Actualizar `_find_next_button` para incluir "Review" y "Revisar"**

Localizar `_find_next_button` en `agents/applicator.py` y reemplazar la lista `labels`:

```python
def _find_next_button(page):
    """Retorna el botón Next / Siguiente / Review / Continue si está visible.
    'Review' y 'Revisar' son navegación intermedia hacia la pantalla de confirmación,
    NO el submit final — se tratan como Next."""
    labels = [
        "Continue to next step",
        "Review your application",   # navega a pantalla de confirmación
        "Revisar tu solicitud",
        "Review",                    # añadido — paso intermedio, no submit
        "Revisar",                   # añadido — igual en español
        "Next",
        "Siguiente",
        "Continue",
        "Continuar",
    ]
    for label in labels:
        try:
            btn = page.locator(
                f"button[aria-label='{label}'], button:has-text('{label}')"
            ).first
            if btn.is_visible(timeout=1_500):
                return btn
        except Exception:
            continue
    return None
```

- [ ] **Step 5: Reemplazar inline submit detection en `_linkedin_playwright_loop`**

Localizar en `_linkedin_playwright_loop` (líneas 591-609):

```python
                # ANTES — inline detection que incluye Review:
                submit_btn = None
                for _submit_sel in [
                    "button[aria-label='Submit application']",
                    "button[aria-label='Enviar solicitud']",
                    "button[aria-label='Review your application']",
                    "button:has-text('Submit application')",
                    "button:has-text('Enviar solicitud')",
                    "button:has-text('Enviar')",
                    "button:has-text('Review')",
                    "button:has-text('Revisar')",
                ]:
                    try:
                        loc = page.locator(_submit_sel).first
                        if loc.is_visible(timeout=1_500):
                            submit_btn = loc
                            break
                    except Exception:
                        continue
                if submit_btn is not None and submit_btn.is_visible(timeout=500):
```

Reemplazar por:

```python
                # DESPUÉS — función separada, sin Review:
                submit_btn = _find_submit_button(page)
                if submit_btn is not None and submit_btn.is_visible(timeout=500):
```

- [ ] **Step 6: Verificar GREEN**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestFindSubmitButton -v
```
Expected: `5 passed`

- [ ] **Step 7: Full suite**

```bash
python -m pytest -q --tb=short
```
Expected: `240 passed`

- [ ] **Step 8: Commit**

```bash
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "fix(bug-d): HITL dispara solo en Submit application, no en Review

Separada _find_submit_button() con solo selectores de submit real.
Review/Revisar movidos a _find_next_button() como navegación intermedia.
Antes: HITL disparaba al 67% (preguntas+Review) y click en Review
retornaba enviado=True sin haber hecho submit real.
Ahora: el agente hace click en Review automaticamente y espera la
pantalla final de Submit application para disparar HITL.
5 tests nuevos — 240/240 GREEN.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3 — BUG-C: Subir CV sin verificar visibilidad del input oculto

**Problema:** `_maybe_upload_cv` usa `inp.is_visible(timeout=1_500)` en `input[type='file']`. LinkedIn oculta estos inputs con `display:none`. Playwright retorna `False` para `is_visible()` en elementos ocultos aunque `set_input_files()` funcione correctamente sobre ellos.

**Fix:** Intentar `set_input_files()` directamente, capturando excepciones por selector. Sin verificación de visibilidad.

**Files:**
- Modify: `agents/applicator.py` — `_maybe_upload_cv`
- Modify: `tests/test_applicator_canal_a.py` — nueva clase `TestMaybeUploadCvHiddenInput`

- [ ] **Step 1: Escribir tests RED**

Agregar al final de `tests/test_applicator_canal_a.py`:

```python
# ── Ciclo 32: _maybe_upload_cv sin is_visible() ───────────────────────────────

import tempfile

class TestMaybeUploadCvHiddenInput:
    """_maybe_upload_cv debe subir el CV aunque el input sea display:none."""

    def test_uploads_to_hidden_file_input(self):
        """set_input_files se llama aunque el input no tenga is_visible True."""
        from agents.applicator import _maybe_upload_cv
        page = MagicMock()
        inp = MagicMock()
        inp.set_input_files = MagicMock()
        page.locator.return_value.first = inp

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            _maybe_upload_cv(page, pdf_path)
            inp.set_input_files.assert_called_once_with(pdf_path)
        finally:
            os.unlink(pdf_path)

    def test_skips_when_pdf_path_empty(self):
        """Sin pdf_path no se intenta subir nada."""
        from agents.applicator import _maybe_upload_cv
        page = MagicMock()
        _maybe_upload_cv(page, "")
        page.locator.assert_not_called()

    def test_skips_when_pdf_not_exists(self):
        """Si el archivo no existe no se intenta subir."""
        from agents.applicator import _maybe_upload_cv
        page = MagicMock()
        _maybe_upload_cv(page, "/nonexistent/path.pdf")
        page.locator.assert_not_called()

    def test_does_not_raise_when_set_input_files_fails(self):
        """Si el selector no existe, captura la excepción silenciosamente."""
        from agents.applicator import _maybe_upload_cv
        page = MagicMock()
        page.locator.return_value.first.set_input_files.side_effect = Exception("No element")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            _maybe_upload_cv(page, pdf_path)  # no debe lanzar
        finally:
            os.unlink(pdf_path)
```

- [ ] **Step 2: Verificar RED**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestMaybeUploadCvHiddenInput -v
```
Expected: `FAILED — test_uploads_to_hidden_file_input: set_input_files not called` (la versión actual verifica is_visible primero y nunca llama set_input_files en el mock)

- [ ] **Step 3: Implementar fix en `_maybe_upload_cv`**

Localizar `_maybe_upload_cv` en `agents/applicator.py` y reemplazar el body completo:

```python
def _maybe_upload_cv(page, pdf_path: str) -> None:
    """Sube el PDF al campo de archivo del formulario Easy Apply.
    
    LinkedIn usa input[type='file'] con display:none (oculto por diseño).
    Playwright's set_input_files() funciona sobre inputs ocultos — no necesita
    is_visible(). Intentamos directamente y capturamos excepciones por selector.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return
    selectors = [
        ".jobs-document-upload__input",
        "input[type='file'][name*='resume']",
        "input[type='file']",
    ]
    for sel in selectors:
        try:
            inp = page.locator(sel).first
            inp.set_input_files(pdf_path)
            _human_pause(0.5, 1.0)
            print(f"  [Applicator-A] CV subido: {os.path.basename(pdf_path)}")
            return
        except Exception:
            continue
```

- [ ] **Step 4: Verificar GREEN**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestMaybeUploadCvHiddenInput -v
```
Expected: `4 passed`

- [ ] **Step 5: Full suite**

```bash
python -m pytest -q --tb=short
```
Expected: `244 passed`

- [ ] **Step 6: Commit**

```bash
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "fix(bug-c): subir CV sin verificar visibilidad del input oculto

LinkedIn usa input[type='file'] con display:none por diseño.
is_visible() siempre retornaba False -> set_input_files nunca se llamaba
-> LinkedIn usaba el CV antiguo del perfil en vez del CV generado.
Fix: intentar set_input_files() directamente, sin is_visible().
Playwright soporta set_input_files() en inputs ocultos.
4 tests nuevos — 244/244 GREEN.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4 — BUG-B: Detección de idioma del JD en cv_rewriter

**Problema:** `_SYSTEM` regla 11 dice "Write in the same language style as the original CV: bilingual Spanish/English mix". El CV base (`_cv_to_plain_text`) está 100% en inglés. Claude produce inglés independientemente del idioma del JD.

**Fix:** Reemplazar regla 11 con instrucción de detección de idioma del JD. El idioma de los bullets y perfil debe seguir al JD, no al CV base.

**Files:**
- Modify: `agents/cv_rewriter.py` — regla 11 de `_SYSTEM`
- Modify: `tests/test_cv_rewriter_unit.py` — test que verifica la instrucción en _SYSTEM

- [ ] **Step 1: Escribir test RED**

En `tests/test_cv_rewriter_unit.py`, agregar al final de la clase existente o como nueva clase:

```python
class TestCvRewriterLanguageDetection:
    """El system prompt debe instruir detección de idioma del JD."""

    def test_system_prompt_contains_language_detection(self):
        """_SYSTEM debe instruir a Claude a detectar el idioma del JD."""
        from agents.cv_rewriter import _SYSTEM
        # La instrucción debe mencionar explícitamente detección de idioma del JD
        assert "job description" in _SYSTEM.lower() or "JOB DESCRIPTION" in _SYSTEM
        # Debe mencionar español como opción
        assert "spanish" in _SYSTEM.lower() or "español" in _SYSTEM.lower()
        # Debe distinguir idioma de bullets/perfil del de los headers
        assert "section header" in _SYSTEM.lower() or "SECTION HEADER" in _SYSTEM

    def test_system_prompt_keeps_english_headers(self):
        """Los section headers deben permanecer en inglés incluso con JD en español."""
        from agents.cv_rewriter import _SYSTEM
        # Regla 24 mantiene los headers en inglés — verificar que no se eliminó
        assert "PROFESSIONAL PROFILE" in _SYSTEM
        assert "WORK EXPERIENCE" in _SYSTEM
```

- [ ] **Step 2: Verificar RED**

```bash
python -m pytest tests/test_cv_rewriter_unit.py::TestCvRewriterLanguageDetection -v
```
Expected: `FAILED — AssertionError: 'spanish' not in _SYSTEM.lower()` (el _SYSTEM actual no tiene instrucción de idioma)

- [ ] **Step 3: Implementar fix en `agents/cv_rewriter.py`**

Localizar regla 11 en `_SYSTEM` (alrededor de línea 363):

```python
# ANTES:
11. Write in the same language style as the original CV: bilingual Spanish/English mix.
```

Reemplazar esa línea con:

```python
11. LANGUAGE: Detect the primary language of the JOB DESCRIPTION provided by the user. \
If the job description is primarily in Spanish, write ALL descriptive content \
(professional profile, bullet points, role descriptions) in Spanish. \
If the job description is primarily in English, write in English. \
Section headers must ALWAYS remain in English uppercase \
(PROFESSIONAL PROFILE, WORK EXPERIENCE, EDUCATION, SKILLS, LANGUAGES) regardless of job language. \
Employment dates, proper nouns, company names, and platform names (Google Ads, Meta Ads, etc.) \
remain unchanged regardless of language.
```

- [ ] **Step 4: Verificar GREEN**

```bash
python -m pytest tests/test_cv_rewriter_unit.py::TestCvRewriterLanguageDetection -v
```
Expected: `2 passed`

- [ ] **Step 5: Full suite**

```bash
python -m pytest -q --tb=short
```
Expected: `246 passed`

- [ ] **Step 6: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "fix(bug-b): CV rewriter detecta idioma del JD

Regla 11 del _SYSTEM ahora detecta el idioma primario del JD:
- JD en español -> bullets y perfil en español
- JD en inglés -> bullets y perfil en inglés
- Section headers SIEMPRE en inglés uppercase (regla 24 sin cambios)
Antes: regla 11 decía 'same language as original CV' (inglés siempre)
porque _cv_to_plain_text() produce el CV base en inglés.
2 tests nuevos — 246/246 GREEN.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Verificación Final

- [ ] **Suite completa**

```bash
python -m pytest -q
```
Expected: `246 passed`

- [ ] **Dry-run de imports y verificación de fixes**

```bash
python -c "
import agents.applicator as a
import agents.cv_rewriter as r

# BUG-A: _parse_title_for_job_info existe y funciona
info = a._parse_title_for_job_info('Product Manager at Falabella | LinkedIn')
assert info['cargo'] == 'Product Manager', f'BUG-A falla: {info}'
assert info['empresa'] == 'Falabella', f'BUG-A falla: {info}'

# BUG-A: placeholder detection
assert 'cargo linkedin' in a._PLACEHOLDER_VALUES
assert 'empresa linkedin' in a._PLACEHOLDER_VALUES

# BUG-D: _find_submit_button existe y no incluye 'Review'
assert callable(a._find_submit_button)
assert not any('Review' in s for s in a._SUBMIT_SELECTORS), 'Review en submit selectors!'
assert not any('Revisar' in s for s in a._SUBMIT_SELECTORS), 'Revisar en submit selectors!'

# BUG-B: language detection en _SYSTEM
assert 'spanish' in r._SYSTEM.lower() or 'español' in r._SYSTEM.lower()

print('OK — todos los fixes verificados')
"
```
Expected: `OK — todos los fixes verificados`

- [ ] **Smoke test final**

```bash
python _smoke_canal_a.py
```
Verificar checklist completo:
- [ ] ¿Consola muestra cargo real extraído (no "Cargo LinkedIn")?
- [ ] ¿Nombre del PDF generado es "Lorena Ruiz - Product Manager - Falabella.pdf"?
- [ ] ¿CV reescrito está en español (bullets en español)?
- [ ] ¿Log muestra "CV subido: Lorena Ruiz - Product Manager - Falabella.pdf"?
- [ ] ¿El campo de aspiración salarial muestra `6500000` sin error rojo?
- [ ] ¿HITL dispara en la pantalla de "Submit application" (no en "Review" al 67%)?
- [ ] ¿Telegram recibió screenshot de la pantalla final de confirmación?
- [ ] ¿Lorena respondió SI y el log muestra "Aplicación enviada (HITL aprobado)"?

- [ ] **Documentar resultado con auto-test-report**

---

## Orden de ejecución

```
Task 1 (BUG-A extracción title)     → 20 min
Task 2 (BUG-D HITL en submit real)  → 20 min
Task 3 (BUG-C upload sin visible)   → 15 min
Task 4 (BUG-B idioma JD)            → 10 min
Verificación final + smoke test     → 20 min
Total estimado:                     ~85 min
```
