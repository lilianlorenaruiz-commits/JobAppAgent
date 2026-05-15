# Canal A — Corrección 4 Bugs Post-Smoke-Test

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir los 4 bugs detectados en el smoke test de 2026-05-14 para que el flujo completo Canal A (extracción de cargo → generación CV → Easy Apply → HITL → submit) funcione sin intervención manual.

**Architecture:** Cuatro fixes independientes en orden de impacto: (1) salario numérico, (2) timeout HITL, (3) extracción de datos del cargo desde LinkedIn, (4) pipeline completo en smoke test. Cada task tiene sus propios tests RED→GREEN antes de tocar producción.

**Tech Stack:** Python 3.11+, Playwright sync_api, Anthropic Claude (cv_rewriter), agents/applicator.py, config.py, _smoke_canal_a.py, config/candidate_profile.json, pytest.

---

## Archivos que se modifican

| Archivo | Qué cambia |
|---|---|
| `config.py` | `HITL_TIMEOUT_S`: 300 → 600 |
| `config/candidate_profile.json` | Ninguno — se usa `salary_cop_monthly` existente |
| `agents/applicator.py` | `_PROFILE_KEYWORD_RULES` salary→`salary_cop_monthly`; nueva función `_extract_linkedin_job_info(page)`; llamada a extracción en `_linkedin_playwright_loop` |
| `_smoke_canal_a.py` | Nuevo flujo: extracción URL → rewrite CV → generate PDF → apply |
| `tests/test_applicator_canal_a.py` | Actualizar test de salario; nuevos tests para `_extract_linkedin_job_info` |
| `tests/test_cv_rewriter_unit.py` | Ninguno |

---

## Task 1 — BUG-001: Salario devuelve número puro, no texto

**Problema evidenciado:** Screenshot muestra campo "¿Cuál es tu aspiración salarial?" con valor "6.500.000 COP / 2.300 USD mensuales" y error "Introduce un número de decimal mayor que 0.0". El campo LinkedIn espera un decimal, no texto.

**Causa raíz:** `_PROFILE_KEYWORD_RULES` mapea keywords de salario a `"salary_text"` → "6.500.000 COP / 2.300 USD mensuales". Debe mapear a `"salary_cop_monthly"` → "6500000".

**Files:**
- Modify: `agents/applicator.py` — `_PROFILE_KEYWORD_RULES` línea 156
- Modify: `tests/test_applicator_canal_a.py` — `TestMatchProfileQuestion` (actualizar expectativa)

- [ ] **Step 1: Confirmar que el test existente espera `salary_text` (debe PASAR antes del cambio)**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python -m pytest tests/test_applicator_canal_a.py::TestMatchProfileQuestion::test_salary_question_returns_profile_answer -v
```
Expected: PASS (el test actual espera `salary_text`)

- [ ] **Step 2: Actualizar el test para esperar `salary_cop_monthly`**

En `tests/test_applicator_canal_a.py`, busca `TestMatchProfileQuestion` y reemplaza los dos tests de salario:

```python
def test_salary_question_returns_profile_answer(self):
    from agents.applicator import _match_profile_question
    ans = _match_profile_question("¿Cuál es tu aspiración salarial?", _PROFILE)
    # Debe devolver el número COP puro para que el campo numérico de LinkedIn lo acepte
    assert ans == _PROFILE["salary_cop_monthly"]

def test_pretension_keyword_matches_salary(self):
    from agents.applicator import _match_profile_question
    ans = _match_profile_question("Pretensión económica mensual", _PROFILE)
    assert ans == _PROFILE["salary_cop_monthly"]
```

- [ ] **Step 3: Verificar que el test ahora FALLA (RED)**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestMatchProfileQuestion::test_salary_question_returns_profile_answer tests/test_applicator_canal_a.py::TestMatchProfileQuestion::test_pretension_keyword_matches_salary -v
```
Expected: FAIL — "assert '6.500.000 COP / 2.300 USD mensuales' == '6500000'"

- [ ] **Step 4: Implementar fix en `agents/applicator.py`**

Localiza `_PROFILE_KEYWORD_RULES` en `agents/applicator.py` (alrededor de línea 154). Cambia la primera regla de `"salary_text"` a `"salary_cop_monthly"`:

```python
_PROFILE_KEYWORD_RULES = [
    # Salario / pretensión → número COP puro (campo numérico LinkedIn)
    (["salarial", "salario", "pretensión", "pretension", "remuneraci", "compensation",
      "salary", "wage", "económi"],                                    "salary_cop_monthly"),
    # Reubicación (antes que ciudad)
    (["reubicar", "reubicaci", "relocat", "traslad"],                 "willing_to_relocate"),
    # Ciudad / ubicación
    (["ciudad", "city", "ubicaci", "location", "resid", "vives"],     "city"),
    # ... resto igual que antes
```

Solo cambia `"salary_text"` → `"salary_cop_monthly"` en la primera entrada. El resto de la lista no cambia.

- [ ] **Step 5: Verificar GREEN**

```bash
python -m pytest tests/test_applicator_canal_a.py -v --tb=short
```
Expected: 46 passed

- [ ] **Step 6: Full suite**

```bash
python -m pytest -q
```
Expected: 219 passed

- [ ] **Step 7: Commit**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "fix(bug-001): salary field returns numeric COP value for LinkedIn forms

Campo aspiracion salarial en LinkedIn Colombia espera numero decimal.
_PROFILE_KEYWORD_RULES: salary_text -> salary_cop_monthly (6500000).
Evidencia: screenshot review 1778807853 muestra error de validacion JS.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2 — BUG-003: HITL timeout 5 min → 10 min

**Problema:** Formulario tarda ~3 min en navegar. Lorena recibe screenshot y tiene solo ~2 min para revisar y responder SI. Con 10 min tiene tiempo suficiente.

**Files:**
- Modify: `config.py` — `HITL_TIMEOUT_S`

- [ ] **Step 1: Confirmar valor actual**

```bash
python -c "import config; print(config.HITL_TIMEOUT_S)"
```
Expected: `300`

- [ ] **Step 2: Cambiar en `config.py`**

Localiza la línea `HITL_TIMEOUT_S = 300` en `config.py` y cámbiala a:

```python
HITL_TIMEOUT_S = 600    # 10 min — tiempo suficiente para revisar tras ~3 min de formulario
```

- [ ] **Step 3: Verificar**

```bash
python -c "import importlib, config; importlib.reload(config); print(config.HITL_TIMEOUT_S)"
```
Expected: `600`

- [ ] **Step 4: Tests no se rompen**

```bash
python -m pytest -q
```
Expected: 219 passed (ningún test hardcodea 300)

- [ ] **Step 5: Commit**

```bash
git add config.py
git commit -m "fix(bug-003): HITL timeout 5min -> 10min

Formulario LinkedIn Easy Apply tarda ~3 min en navegar los pasos.
Con 300s quedaban solo ~2 min para revision en Telegram — insuficiente.
600s da margen comodo de ~7 min para revision y respuesta SI/NO.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3 — BUG-004: Extraer cargo/empresa/descripción de la página LinkedIn

**Problema:** El applicator navega a la URL pero no lee el contenido de la oferta. El smoke test usa placeholders "Cargo LinkedIn". El smart fill no tiene JD real.

**Solución:** Función `_extract_linkedin_job_info(page)` que lee la página mientras está abierta en `_linkedin_playwright_loop`, antes de hacer click en Easy Apply.

**Files:**
- Modify: `agents/applicator.py` — nueva función + llamada en `_linkedin_playwright_loop`
- Modify: `tests/test_applicator_canal_a.py` — tests para `_extract_linkedin_job_info`

- [ ] **Step 1: Escribir tests RED para `_extract_linkedin_job_info`**

Al final de `tests/test_applicator_canal_a.py`, agregar:

```python
# ── Ciclo 29: _extract_linkedin_job_info ──────────────────────────────────────

class TestExtractLinkedinJobInfo:
    """_extract_linkedin_job_info lee cargo, empresa y descripción de la página."""

    def _mock_page_with_content(self, cargo="Product Manager",
                                 empresa="Falabella", desc="Descripción del cargo."):
        page = MagicMock()

        def _locator_side_effect(selector, **kwargs):
            loc = MagicMock()
            loc.first.is_visible.return_value = True
            if "h1" in selector:
                loc.first.text_content.return_value = cargo
            elif "company" in selector or "org-name" in selector:
                loc.first.text_content.return_value = empresa
            elif "description" in selector or "box__html" in selector:
                loc.first.text_content.return_value = desc
            else:
                loc.first.is_visible.return_value = False
                loc.first.text_content.return_value = ""
            return loc

        page.locator.side_effect = _locator_side_effect
        return page

    def test_returns_dict_with_three_keys(self):
        from agents.applicator import _extract_linkedin_job_info
        page = self._mock_page_with_content()
        result = _extract_linkedin_job_info(page)
        assert "cargo" in result
        assert "empresa" in result
        assert "descripcion" in result

    def test_extracts_cargo_from_h1(self):
        from agents.applicator import _extract_linkedin_job_info
        page = self._mock_page_with_content(cargo="Media Planning Manager")
        result = _extract_linkedin_job_info(page)
        assert result["cargo"] == "Media Planning Manager"

    def test_extracts_empresa(self):
        from agents.applicator import _extract_linkedin_job_info
        page = self._mock_page_with_content(empresa="OMD Colombia")
        result = _extract_linkedin_job_info(page)
        assert result["empresa"] == "OMD Colombia"

    def test_extracts_descripcion(self):
        from agents.applicator import _extract_linkedin_job_info
        page = self._mock_page_with_content(desc="Requisitos: Google Ads, Meta Ads.")
        result = _extract_linkedin_job_info(page)
        assert "Google Ads" in result["descripcion"]

    def test_descripcion_truncated_at_3000_chars(self):
        from agents.applicator import _extract_linkedin_job_info
        long_desc = "X" * 5000
        page = self._mock_page_with_content(desc=long_desc)
        result = _extract_linkedin_job_info(page)
        assert len(result["descripcion"]) <= 3000

    def test_does_not_raise_when_page_throws(self):
        from agents.applicator import _extract_linkedin_job_info
        page = MagicMock()
        page.locator.side_effect = Exception("Playwright error")
        result = _extract_linkedin_job_info(page)
        assert result == {"cargo": "", "empresa": "", "descripcion": ""}

    def test_returns_empty_strings_when_elements_not_visible(self):
        from agents.applicator import _extract_linkedin_job_info
        page = MagicMock()
        loc = MagicMock()
        loc.first.is_visible.return_value = False
        page.locator.return_value = loc
        result = _extract_linkedin_job_info(page)
        assert result["cargo"] == ""
        assert result["empresa"] == ""
        assert result["descripcion"] == ""
```

- [ ] **Step 2: Verificar RED**

```bash
python -m pytest tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo -v
```
Expected: FAIL — "ImportError: cannot import name '_extract_linkedin_job_info'"

- [ ] **Step 3: Implementar `_extract_linkedin_job_info` en `agents/applicator.py`**

Agregar ANTES de `_linkedin_playwright_loop` (alrededor de línea 296):

```python
def _extract_linkedin_job_info(page) -> dict:
    """
    Lee cargo, empresa y descripción de la página LinkedIn actual.
    Usa múltiples selectores con fallback — LinkedIn cambia su HTML frecuentemente.
    Nunca lanza excepción. Retorna dict con cadenas vacías si falla.
    """
    info = {"cargo": "", "empresa": "", "descripcion": ""}
    try:
        # Cargo: h1 del panel de detalle (LinkedIn usa distintas clases según versión)
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

        # Empresa
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

        # Descripción (cuerpo completo de la oferta)
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

- [ ] **Step 4: Integrar la extracción en `_linkedin_playwright_loop`**

En `_linkedin_playwright_loop`, después de `_human_pause(1.0, 2.0)` que sigue al `page.goto(...)` (alrededor de línea 332) y ANTES del bloque "Verificar que la página cargó", agregar:

```python
            # ── 1b. Extraer info del cargo de la página ──────────────────────
            # Lee cargo, empresa y descripción desde el HTML de LinkedIn.
            # Enriquece job_description si llegó vacío (ej: desde smoke test).
            _job_info = _extract_linkedin_job_info(page)
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

- [ ] **Step 5: Verificar GREEN**

```bash
python -m pytest tests/test_applicator_canal_a.py -v --tb=short
```
Expected: 53 passed (46 anteriores + 7 nuevos)

- [ ] **Step 6: Full suite**

```bash
python -m pytest -q
```
Expected: 226 passed

- [ ] **Step 7: Commit**

```bash
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "feat(bug-004): extraer cargo/empresa/JD de la pagina LinkedIn

Nueva funcion _extract_linkedin_job_info(page) lee el HTML de la oferta
con multiples selectores CSS con fallback (LinkedIn cambia su HTML).
Se llama en _linkedin_playwright_loop justo despues de page.goto(),
enriqueciendo job_description si llego vacio desde el smoke test.
Resultado: smart fill recibe el JD real para contextualizar respuestas.
7 tests nuevos — 226/226 GREEN.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4 — BUG-002: Pipeline completo en smoke test

**Problema:** `_smoke_canal_a.py` llama `apply()` con un PDF estático (Rappi) sin conocer el cargo real. Debe ejecutar el mismo pipeline que `main.py`: extraer JD → rewrite CV → generate PDF → apply.

**Solución:** El smoke test usa `_extract_linkedin_job_info` via una sesión Playwright breve, luego reescribe el CV con esa info, genera el PDF, y finalmente llama `apply()` con todo correcto.

**Files:**
- Modify: `_smoke_canal_a.py` — reemplazar flujo estático por pipeline completo

> **NOTA:** Este task NO agrega tests unitarios nuevos — el pipeline (parse_cv, rewrite, generate) ya está probado en sus propios tests. Lo que cambia es el script de smoke test.

- [ ] **Step 1: Leer el estado actual del smoke test**

```bash
python -c "
import sys, os
sys.path.insert(0, r'C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent')
import config
print('OUTPUT_DIR:', config.OUTPUT_DIR)
print('CV_PATH:', config.CV_PATH)
"
```
Verificar que las rutas existen antes de continuar.

- [ ] **Step 2: Reemplazar `_smoke_canal_a.py` con el flujo completo**

Reemplaza el contenido completo del archivo:

```python
"""
Smoke test Nivel 3 — Canal A real con pipeline completo.

Flujo:
  1. Extraer cargo, empresa y descripción de la URL de LinkedIn (Playwright breve)
  2. Reescribir CV adaptado a ese cargo (Claude API — puede tardar 2-4 min)
  3. Generar PDF del CV reescrito
  4. Aplicar via Easy Apply (Playwright + HITL Telegram)

Uso:
  python _smoke_canal_a.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.cv_parser import parse_cv
from agents.cv_rewriter import rewrite
from agents.pdf_generator import generate
from agents.applicator import apply, _extract_linkedin_job_info

# ── URL de prueba — reemplazar con oferta real de LinkedIn Easy Apply ───────
TEST_URL  = "https://www.linkedin.com/jobs/view/4407519233/"
TEST_RAMA = "C"   # A=Consultoría  B=Retail  C=Paid Media

# ─────────────────────────────────────────────────────────────────────────────

def _scrape_job_from_url(url: str) -> dict:
    """
    Abre la URL en el browser con sesión persistente, extrae cargo/empresa/JD,
    cierra el browser y retorna un dict de job.
    Sesión breve — el profile lock se libera antes de llamar apply().
    """
    from playwright.sync_api import sync_playwright
    job = {"url": url, "cargo": "", "empresa": "", "descripcion": "",
           "modalidad": "Híbrido", "ubicacion": "Bogotá D.C.", "rama": TEST_RAMA, "score": 90}
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                config.PLAYWRIGHT_USER_DATA_DIR,
                headless=False,
                slow_mo=300,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            print(f"  [Scrape] Navegando a {url}")
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            time.sleep(3)  # render completo de componentes LinkedIn

            info = _extract_linkedin_job_info(page)
            job["cargo"]      = info["cargo"]      or "Cargo LinkedIn"
            job["empresa"]    = info["empresa"]     or "Empresa LinkedIn"
            job["descripcion"] = info["descripcion"] or ""

            print(f"  [Scrape] Cargo:   {job['cargo']}")
            print(f"  [Scrape] Empresa: {job['empresa']}")
            print(f"  [Scrape] JD:      {len(job['descripcion'])} chars extraídos")
            ctx.close()
    except Exception as e:
        print(f"  [Scrape] Error al extraer info: {e} — usando placeholders")
    return job


def main():
    print("=" * 60)
    print("SMOKE TEST — CANAL A (pipeline completo)")
    print("=" * 60)
    print(f"URL:    {TEST_URL}")
    print(f"Rama:   {TEST_RAMA}")
    print(f"HITL:   {'ACTIVADO (' + str(config.HITL_TIMEOUT_S // 60) + ' min)' if config.HITL_ENABLED else 'DESACTIVADO'}")
    print()

    # ── 1. Extraer info del cargo ─────────────────────────────────────────────
    print("PASO 1 — Extrayendo info del cargo desde LinkedIn...")
    job = _scrape_job_from_url(TEST_URL)
    print()

    # ── 2. Leer CV base ───────────────────────────────────────────────────────
    print("PASO 2 — Leyendo CV base desde PDF...")
    try:
        cv = parse_cv()
        print(f"  CV listo: {cv['nombre']} | {len(cv['experiencia'])} roles")
    except Exception as e:
        print(f"  ERROR parse_cv: {e}")
        sys.exit(1)
    print()

    # ── 3. Reescribir CV adaptado al cargo ────────────────────────────────────
    print(f"PASO 3 — Reescribiendo CV para '{job['cargo']}' @ '{job['empresa']}'...")
    print("  (Claude API — puede tardar 2-4 minutos)")
    try:
        rewrite_result = rewrite(cv, job, rama=TEST_RAMA)
        print(f"  ATS Score: {rewrite_result['ats_score']}% | "
              f"Intentos: {rewrite_result['attempts']} | "
              f"Pasa: {rewrite_result['passed_ats']}")
        if not rewrite_result["passed_ats"]:
            print("  ADVERTENCIA: ATS < 95% — CV puede no estar optimizado")
    except Exception as e:
        print(f"  ERROR cv_rewriter: {e}")
        sys.exit(1)
    cv_text = rewrite_result["cv_text"]
    print()

    # ── 4. Generar PDF ────────────────────────────────────────────────────────
    print("PASO 4 — Generando PDF...")
    try:
        pdf_path = generate(cv_text, job)
        print(f"  PDF generado: {os.path.basename(pdf_path)}")
    except Exception as e:
        print(f"  ERROR pdf_generator: {e}")
        sys.exit(1)
    print()

    # ── 5. Aplicar — Easy Apply ───────────────────────────────────────────────
    print("PASO 5 — Aplicando via Canal A (Easy Apply)...")
    print("  Browser abriendo LinkedIn...")
    if config.HITL_ENABLED:
        print(f"  Telegram recibirá screenshot para aprobación ({config.HITL_TIMEOUT_S // 60} min timeout)")
    print()

    result = apply(
        job, pdf_path,
        dry_run=False,
        cv_text=cv_text,
        job_description=job.get("descripcion", ""),
    )

    # ── Resultado ─────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESULTADO FINAL:")
    print(f"  Cargo:   {job['cargo']} @ {job['empresa']}")
    print(f"  Canal:   {result['canal']}")
    print(f"  Enviado: {result['enviado']}")
    print(f"  Mensaje: {result['mensaje']}")
    print("=" * 60)
    print()
    print("Checklist de verificación:")
    print("  [ ] ¿Se extrajo cargo y empresa correctamente?")
    print("  [ ] ¿El CV reescrito menciona keywords del cargo?")
    print("  [ ] ¿El PDF generado se subió al formulario?")
    print("  [ ] ¿Se llenaron teléfono y email?")
    print("  [ ] ¿El campo de aspiración salarial aceptó el número? (sin error rojo)")
    print("  [ ] ¿Telegram recibió el screenshot de Review?")
    if config.HITL_ENABLED:
        print("  [ ] ¿Lorena respondió SI y se hizo submit?")
    else:
        print("  [ ] ¿Submit automático ejecutado?")
    print()
    if result["enviado"]:
        print("✅ SMOKE TEST COMPLETO — CANAL A APROBADO")
    else:
        print("⚠️  Smoke test completado — revisar checklist arriba")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verificar que el smoke test arranca sin errores de importación**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python -c "import _smoke_canal_a; print('Imports OK')"
```
Expected: `Imports OK` (sin errores de importación)

- [ ] **Step 4: Verificar que los tests existentes siguen pasando**

```bash
python -m pytest -q
```
Expected: 226 passed

- [ ] **Step 5: Commit**

```bash
git add _smoke_canal_a.py
git commit -m "feat(bug-002): smoke test con pipeline completo

_smoke_canal_a.py ahora ejecuta el flujo real de produccion:
  1. Extrae cargo/empresa/JD de la URL con Playwright (_scrape_job_from_url)
  2. parse_cv() -> rewrite() con el JD real -> generate() PDF adaptado
  3. apply() con el PDF correcto y job_description real

Elimina el PDF estatico de Rappi y los placeholders Cargo/Empresa LinkedIn.
El smoke test ahora representa exactamente lo que hace main.py en produccion.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Verificación Final

- [ ] **Full suite completa**

```bash
python -m pytest -q
```
Expected: 226 passed

- [ ] **Smoke test dry-run de importaciones**

```bash
python -c "
import _smoke_canal_a
import agents.applicator as a
print('_extract_linkedin_job_info:', callable(a._extract_linkedin_job_info))
import config
print('HITL_TIMEOUT_S:', config.HITL_TIMEOUT_S)
from agents.applicator import _PROFILE_KEYWORD_RULES
salary_rule = _PROFILE_KEYWORD_RULES[0]
print('salary rule key:', salary_rule[1])
assert salary_rule[1] == 'salary_cop_monthly', 'BUG-001 no aplicado'
assert config.HITL_TIMEOUT_S == 600, 'BUG-003 no aplicado'
print('OK — todos los fixes verificados')
"
```
Expected: Imprime `salary rule key: salary_cop_monthly`, `HITL_TIMEOUT_S: 600`, `OK`

- [ ] **Actualizar contexto_sesion.md**

Actualizar en `docs/contexto_sesion.md`:
- Tests: 219 → 226
- Agregar sección de bugs post-smoke corregidos

---

## Orden de ejecución

```
Task 1 (BUG-001 salario)      → 10 min
Task 2 (BUG-003 timeout)      →  5 min
Task 3 (BUG-004 extracción)   → 20 min
Task 4 (BUG-002 smoke test)   → 15 min
Verificación final             →  5 min
Total estimado:               ~55 min
```
