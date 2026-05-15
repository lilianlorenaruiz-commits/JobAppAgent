# BUG-001: JD Extraction Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer la descripción completa del puesto (≥100 chars) desde LinkedIn para que `cv_rewriter` tenga keywords reales y el ATS score suba de 70% a 95%+.

**Architecture:** LinkedIn lazy-load la descripción via AJAX cuando el usuario hace scroll hasta ese área. El approach actual falla porque: (1) el scroll dura solo 0.8s (el AJAX tarda 2-4s), (2) se vuelve al top antes de que React renderice el contenido, (3) los selectores CSS están desactualizados. La solución usa `wait_for_selector` con timeout real, espera más tiempo en el área de descripción, intenta expandir "Ver más"/"See more", y como último fallback usa `page.inner_text()` sobre el área visible para capturar el texto que LinkedIn ya renderizó.

**Tech Stack:** Python, Playwright sync_api, `agents/applicator.py::_extract_linkedin_job_info`, `_smoke_canal_a.py::_scrape_job_from_url`, 262 tests pasando.

---

## Archivos a modificar

| Archivo | Qué cambia |
|---------|-----------|
| `agents/applicator.py` | `_extract_linkedin_job_info`: nueva estrategia de scroll/wait + expand + inner_text |
| `_smoke_canal_a.py` | `_scrape_job_from_url`: eliminar scroll duplicado |
| `tests/test_applicator_canal_a.py` | `TestExtractLinkedinJobInfo`: tests nuevos para wait_for_selector y expand |

---

## Task 1: Diagnóstico — entender qué DOM entrega LinkedIn

**Propósito:** Antes de implementar, confirmar qué selectores existen en el HTML real. Esta tarea agrega una función de diagnóstico temporal que guarda el HTML para inspección.

**Files:**
- Modify: `agents/applicator.py` (agregar `_dump_linkedin_page_html` temporal)
- Modify: `_smoke_canal_a.py` (llamar al diagnóstico después del scroll)

- [ ] **Step 1: Agregar función de diagnóstico en applicator.py**

Ubica la sección de funciones de debug (cerca de `_screenshot_on_error`, aprox. línea 200) y agrega:

```python
def _dump_linkedin_page_html(page, label: str = "debug") -> str:
    """
    Guarda el HTML completo de la página en output/debug/ para inspección.
    Solo se usa en debugging — llamar manualmente, no en producción.
    Retorna la ruta del archivo guardado.
    """
    import time as _t
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "debug")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"linkedin_{label}_{int(_t.time())}.html")
    try:
        html = page.content()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[DEBUG] HTML guardado: {path}")
    except Exception as e:
        print(f"[DEBUG] Error guardando HTML: {e}")
    return path
```

- [ ] **Step 2: Llamar al diagnóstico en `_smoke_canal_a.py` después del scroll**

En `_scrape_job_from_url`, después de `time.sleep(3)` y antes de llamar a `_extract_linkedin_job_info`, agrega temporalmente:

```python
# DIAGNÓSTICO TEMPORAL — remover tras confirmar selectores
try:
    from agents.applicator import _dump_linkedin_page_html
    _dump_linkedin_page_html(page, label="before_extract")
except Exception:
    pass
```

- [ ] **Step 3: Ejecutar smoke test para capturar el HTML**

```powershell
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python _smoke_canal_a.py https://www.linkedin.com/jobs/view/4409370270
```

Observar el output — debe imprimir la ruta del HTML guardado.
Abrir el archivo en un editor y buscar con Ctrl+F:
- `job-details` — ¿existe este id?
- `description` — ¿qué clases tienen los divs que lo contienen?
- `See more` / `Ver más` — ¿hay un botón para expandir?
- `<script type="application/ld+json">` — ¿está presente con descripción?

Anotar los selectores reales encontrados. Eso define la implementación del Task 2.

---

## Task 2: Fix `_extract_linkedin_job_info` — scroll real + wait + expand

**Root cause confirmado:** LinkedIn hace AJAX lazy-load de la descripción cuando el usuario scrollea hasta ella. El sleep de 0.8s es insuficiente; React tarda 2-4s en renderizar el resultado. Además, el código vuelve al top (scrollTo 0) antes de que el contenido esté listo.

**Files:**
- Modify: `agents/applicator.py:501-644` — reemplazar la función completa

- [ ] **Step 1: Escribir test RED para la nueva estrategia de wait**

En `tests/test_applicator_canal_a.py`, dentro de `TestExtractLinkedinJobInfo`, agregar:

```python
def test_waits_for_description_element_before_extracting(self):
    """Si el selector aparece después de un wait, la descripción se extrae correctamente.

    Simula el comportamiento AJAX de LinkedIn: el elemento no existe al cargar
    la página pero aparece ~2s después del scroll. El fix debe usar
    wait_for_selector en vez de is_visible con timeout corto.
    """
    from agents.applicator import _extract_linkedin_job_info
    from unittest.mock import MagicMock, patch, call
    import time

    _long_desc = (
        "Buscamos Social Analyst con experiencia en redes sociales y analytics. "
        "Responsabilidades: gestionar contenido, analizar métricas, reportar KPIs. "
        "Requisitos: inglés B2, manejo de Meta Business Suite y Google Analytics. " * 2
    )

    page = MagicMock()
    page.title.return_value = "Social Analyst | Publicis Global Delivery (PGD) | LinkedIn"

    # Simula wait_for_selector que completa sin error (elemento apareció)
    page.wait_for_selector.return_value = MagicMock()

    # locator para descripción retorna el texto largo
    desc_locator = MagicMock()
    desc_locator.inner_text.return_value = _long_desc

    def locator_side(sel, **kw):
        if "job-details" in sel or "description" in sel.lower():
            return desc_locator
        loc = MagicMock()
        loc.first.is_visible.return_value = False
        return loc

    page.locator.side_effect = locator_side
    page.evaluate.return_value = ""   # JS y JSON-LD fallan

    result = _extract_linkedin_job_info(page)
    assert len(result["descripcion"]) > 100, (
        "descripcion debe extraerse cuando wait_for_selector completa"
    )
    assert "Social Analyst" in result["descripcion"]


def test_clicks_see_more_to_expand_description(self):
    """Si existe botón 'Ver más'/'See more', hace click para expandir la descripción.

    LinkedIn colapsa descripciones largas. Sin click, el innerText es corto.
    Con click, el texto completo está disponible.
    """
    from agents.applicator import _extract_linkedin_job_info

    _short = "Ver descripción completa..."
    _long_desc = (
        "Responsabilidades completas: gestionar campañas paid social, "
        "analizar performance CTR CPC CPM, reportar a clientes. "
        "Experiencia mínima 2 años en agencias digitales. " * 3
    )

    page = MagicMock()
    page.title.return_value = "Social Analyst | Publicis | LinkedIn"
    page.wait_for_selector.return_value = MagicMock()

    # Locator de descripción: antes de click retorna texto corto, después largo
    click_count = {"n": 0}
    desc_locator = MagicMock()

    def inner_text_side():
        return _long_desc if click_count["n"] > 0 else _short
    desc_locator.inner_text.side_effect = inner_text_side

    # Botón "Ver más" existe
    see_more_btn = MagicMock()
    see_more_btn.is_visible.return_value = True
    def see_more_click():
        click_count["n"] += 1
    see_more_btn.click.side_effect = see_more_click

    def locator_side(sel, **kw):
        if "ver" in sel.lower() or "see" in sel.lower() or "more" in sel.lower():
            return see_more_btn
        if "job-details" in sel or "description" in sel.lower():
            return desc_locator
        loc = MagicMock()
        loc.first.is_visible.return_value = False
        return loc

    page.locator.side_effect = locator_side
    page.evaluate.return_value = ""

    result = _extract_linkedin_job_info(page)
    assert len(result["descripcion"]) > 100, (
        "descripcion debe extraerse después de click en 'Ver más'"
    )


def test_falls_back_to_body_innertext_when_all_selectors_fail(self):
    """Último fallback: page.inner_text('body') captura todo el texto visible.

    Si todos los selectores específicos fallan, el texto de la descripción
    igual está renderizado en el DOM — se puede extraer buscando entre
    el cargo conocido y el footer de LinkedIn.
    """
    from agents.applicator import _extract_linkedin_job_info

    _body_text = (
        "Social Analyst\nPublicis Global Delivery (PGD)\n"
        "Acerca del puesto\n"
        "Buscamos profesional para gestión de redes sociales y analytics. "
        "Requisitos: inglés B2, experiencia en Meta Business Suite. "
        "Ofrecemos contrato indefinido y modalidad híbrida en Bogotá. " * 2
        "\nSolicitar ahora\nLinkedIn"
    )

    page = MagicMock()
    page.title.return_value = "Social Analyst | Publicis Global Delivery (PGD) | LinkedIn"
    page.wait_for_selector.side_effect = Exception("timeout")  # selector no aparece
    page.evaluate.return_value = ""   # JS y JSON-LD fallan

    # Todos los locators fallan
    fail_locator = MagicMock()
    fail_locator.inner_text.side_effect = Exception("not found")
    fail_locator.is_visible.return_value = False
    fail_locator.first.is_visible.return_value = False
    page.locator.return_value = fail_locator

    # Pero page.inner_text('body') retorna el texto completo
    page.inner_text.return_value = _body_text

    result = _extract_linkedin_job_info(page)
    assert len(result["descripcion"]) > 100, (
        "descripcion debe extraerse via page.inner_text('body') como último fallback"
    )
    assert "Publicis" in result["descripcion"] or "Buscamos" in result["descripcion"]
```

- [ ] **Step 2: Verificar que los 3 tests fallan (RED)**

```powershell
python -m pytest tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo::test_waits_for_description_element_before_extracting tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo::test_clicks_see_more_to_expand_description tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo::test_falls_back_to_body_innertext_when_all_selectors_fail -v
```
Esperado: 3 FAIL

- [ ] **Step 3: Reemplazar `_extract_linkedin_job_info` en applicator.py**

Reemplaza la función completa (líneas 501-644) con:

```python
# Selectores de descripción que LinkedIn ha usado históricamente
_JD_SELECTORS = [
    "#job-details",
    ".jobs-description__content",
    ".jobs-box__html-content",
    ".jobs-description-content__text",
    ".jobs-description-content__text--stretch",
    "article.jobs-description__container",
    ".description__text",
    '[data-test-id="job-description"]',
    ".jobs-description",
    ".show-more-less-html__markup",
]

# Botones que colapsan/expanden la descripción en LinkedIn
_SEE_MORE_SELECTORS = [
    "button.jobs-description__footer-button",
    "button[aria-label='Ver más']",
    "button[aria-label='See more']",
    ".jobs-description__footer button",
    "footer.jobs-description__footer button",
    "button.show-more-less-html__button",
]


def _extract_linkedin_job_info(page) -> dict:
    """
    Lee cargo, empresa y descripción de la página LinkedIn actual.

    Estrategia multicapa (en orden de confianza):
    1. page.title() → cargo + empresa (estable ante cambios CSS)
    2. DOM fallback para cargo/empresa si el título no los da
    3. Descripción:
       a. wait_for_selector + inner_text() → espera a que el AJAX cargue
       b. Click "Ver más"/"See more" si el texto está colapsado
       c. page.evaluate() con múltiples querySelector (JS directo al DOM)
       d. JSON-LD structured data (LinkedIn lo incluye para SEO)
       e. page.inner_text('body') → texto completo de la página visible

    Nunca lanza excepción. Retorna dict con cadenas vacías si falla.
    """
    info = {"cargo": "", "empresa": "", "descripcion": ""}
    try:
        # ── 0. Scroll profundo para activar lazy-load AJAX de LinkedIn ─────────
        # LinkedIn no carga la descripción hasta que el usuario scrollea hasta ella.
        # Necesitamos scroll gradual + espera suficiente para el AJAX (2-4s).
        try:
            page.evaluate("window.scrollTo(0, 400)")          # encabezado visible
            time.sleep(0.5)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
            time.sleep(1.0)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
            time.sleep(2.0)  # esperar respuesta AJAX de LinkedIn
        except Exception:
            pass

        # ── 1. Título del tab — más estable que selectores CSS ─────────────────
        try:
            title_info = _parse_title_for_job_info(page.title() or "")
            if title_info["cargo"]:
                info["cargo"] = title_info["cargo"]
            if title_info["empresa"]:
                info["empresa"] = title_info["empresa"]
        except Exception:
            pass

        # ── 2. Fallback DOM para cargo (si title no lo dio) ────────────────────
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

        # ── 3. Fallback DOM para empresa (si title no lo dio) ──────────────────
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

        # ── 4a. wait_for_selector + inner_text() ──────────────────────────────
        # Espera a que el elemento de descripción exista en el DOM (post-AJAX).
        # inner_text() es más fiable que text_content() para contenido React.
        if not info["descripcion"]:
            for sel in _JD_SELECTORS:
                try:
                    page.wait_for_selector(sel, timeout=4_000)
                    el = page.locator(sel).first
                    txt = (el.inner_text(timeout=3_000) or "").strip()
                    if len(txt) > 100:
                        # Intentar expandir "Ver más" si el texto es corto
                        if len(txt) < 300:
                            for btn_sel in _SEE_MORE_SELECTORS:
                                try:
                                    btn = page.locator(btn_sel).first
                                    if btn.is_visible(timeout=500):
                                        btn.click()
                                        time.sleep(1.0)
                                        txt = (el.inner_text(timeout=2_000) or "").strip()
                                        break
                                except Exception:
                                    continue
                        if len(txt) > 100:
                            info["descripcion"] = txt[:3000]
                            break
                except Exception:
                    continue

        # ── 4b. Click "Ver más" explícito + re-extracción ─────────────────────
        if not info["descripcion"]:
            for btn_sel in _SEE_MORE_SELECTORS:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.is_visible(timeout=1_000):
                        btn.click()
                        time.sleep(1.5)
                        # Reintentar extracción post-click
                        for sel in _JD_SELECTORS:
                            try:
                                el = page.locator(sel).first
                                txt = (el.inner_text(timeout=2_000) or "").strip()
                                if len(txt) > 100:
                                    info["descripcion"] = txt[:3000]
                                    break
                            except Exception:
                                continue
                        if info["descripcion"]:
                            break
                except Exception:
                    continue

        # ── 4c. JavaScript evaluation — acceso directo al DOM ─────────────────
        if not info["descripcion"]:
            try:
                desc = page.evaluate("""
                    () => {
                        const candidates = [
                            document.querySelector('#job-details'),
                            document.querySelector('.jobs-description__content'),
                            document.querySelector('.jobs-box__html-content'),
                            document.querySelector('.jobs-description-content__text'),
                            document.querySelector('article.jobs-description__container'),
                            document.querySelector('.description__text'),
                            document.querySelector('[data-test-id="job-description"]'),
                            document.querySelector('.jobs-description'),
                            document.querySelector('.show-more-less-html__markup'),
                        ];
                        for (const el of candidates) {
                            if (el && el.innerText && el.innerText.trim().length > 100) {
                                return el.innerText.trim();
                            }
                        }
                        return '';
                    }
                """)
                if desc and len(desc.strip()) > 100:
                    info["descripcion"] = desc.strip()[:3000]
            except Exception:
                pass

        # ── 4d. JSON-LD — datos estructurados que LinkedIn incluye para SEO ───
        if not info["descripcion"]:
            try:
                ld_desc = page.evaluate("""
                    () => {
                        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                        for (const s of scripts) {
                            try {
                                const data = JSON.parse(s.textContent);
                                if (data.description) return data.description;
                                if (data['@graph']) {
                                    for (const item of data['@graph']) {
                                        if (item.description) return item.description;
                                    }
                                }
                            } catch(e) {}
                        }
                        return '';
                    }
                """)
                if ld_desc and len(ld_desc.strip()) > 100:
                    import html as _html
                    cleaned = _html.unescape(ld_desc).strip()
                    info["descripcion"] = cleaned[:3000]
            except Exception:
                pass

        # ── 4e. page.inner_text('body') — último fallback ─────────────────────
        # Si todo falla, la descripción igual está en el DOM visible.
        # Extraemos todo el texto de la página y descartamos el ruido de nav/footer.
        if not info["descripcion"]:
            try:
                body_text = page.inner_text("body", timeout=5_000)
                if body_text:
                    # Buscar el bloque de descripción entre marcadores conocidos
                    # LinkedIn muestra: [cargo] [empresa] [Acerca del puesto] [descripcion] [Solicitar]
                    markers_start = [
                        "Acerca del puesto", "About the job",
                        "Descripción del empleo", "Job description",
                    ]
                    markers_end = [
                        "Solicitar", "Apply", "Mostrar más empleos", "Show more jobs",
                        "Candidatos que han solicitado", "Competencias",
                    ]
                    text = body_text
                    for marker in markers_start:
                        idx = text.find(marker)
                        if idx != -1:
                            text = text[idx + len(marker):].strip()
                            break
                    for marker in markers_end:
                        idx = text.find(marker)
                        if idx != -1 and idx > 100:
                            text = text[:idx].strip()
                            break
                    if len(text) > 100:
                        info["descripcion"] = text[:3000]
            except Exception:
                pass

    except Exception:
        pass

    return info
```

- [ ] **Step 4: Verificar que los 3 tests nuevos pasan (GREEN)**

```powershell
python -m pytest tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo -v
```
Esperado: todos PASS (incluyendo los 3 nuevos + los existentes)

- [ ] **Step 5: Commit**

```powershell
git add agents/applicator.py tests/test_applicator_canal_a.py
git commit -m "fix(BUG-001): _extract_linkedin_job_info — wait_for_selector + Ver más + inner_text fallback"
```

---

## Task 3: Eliminar scroll duplicado en `_smoke_canal_a.py`

`_scrape_job_from_url` hace scroll antes de llamar a `_extract_linkedin_job_info`, que ahora también hace su propio scroll profundo. El doble scroll es redundante y puede interferir.

**Files:**
- Modify: `_smoke_canal_a.py:57-65` — eliminar el bloque de scroll manual

- [ ] **Step 1: Eliminar el scroll duplicado**

En `_smoke_canal_a.py`, elimina este bloque (aprox. líneas 57-65):

```python
# ELIMINAR ESTO:
# Hacer scroll para disparar lazy-loading de la descripción
try:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)
except Exception:
    pass
```

`_extract_linkedin_job_info` ya hace el scroll completo internamente.

- [ ] **Step 2: También eliminar el diagnóstico temporal del Task 1**

Eliminar del `_smoke_canal_a.py` la llamada a `_dump_linkedin_page_html` agregada en Task 1.

- [ ] **Step 3: Verificar que la suite completa sigue verde**

```powershell
python -m pytest tests/test_applicator_canal_a.py -v --tb=short -q
```
Esperado: todos PASS

- [ ] **Step 4: Commit**

```powershell
git add _smoke_canal_a.py
git commit -m "refactor: eliminar scroll duplicado en _scrape_job_from_url — _extract_linkedin_job_info ya hace scroll"
```

---

## Task 4: Actualizar los mocks existentes para el nuevo contrato de `evaluate()`

La nueva implementación llama a `page.evaluate()` más veces (scroll x3 + JS desc + JSON-LD = 5 calls en vez de 2+1). Los tests existentes que usan `side_effect` con lista fija necesitan actualización.

**Files:**
- Modify: `tests/test_applicator_canal_a.py` — `TestExtractLinkedinJobInfo`

- [ ] **Step 1: Revisar qué tests usan side_effect de evaluate()**

```powershell
python -m pytest tests/test_applicator_canal_a.py::TestExtractLinkedinJobInfo -v --tb=short
```

Si hay failures por `StopIteration` (side_effect se agotó), el mock tiene lista corta.

- [ ] **Step 2: Actualizar el test JSON-LD con los nuevos scroll calls**

La nueva función hace **3 scrolls** (no 2). Actualizar el mock:

```python
# En test_extracts_descripcion_via_json_ld_when_js_fails:
# Antes: page.evaluate.side_effect = [None, None, "", _long_desc]
# Ahora: 3 scrolls + JS vacío + JSON-LD con desc
page.evaluate.side_effect = [None, None, None, "", _long_desc]
```

- [ ] **Step 3: Verificar que todos los tests del módulo pasan**

```powershell
python -m pytest tests/test_applicator_canal_a.py -v -q
```
Esperado: todos PASS

- [ ] **Step 4: Ejecutar suite completa**

```powershell
python -m pytest --tb=short -q
```
Esperado: 265+ tests PASS (262 previos + 3 nuevos)

- [ ] **Step 5: Commit**

```powershell
git add tests/test_applicator_canal_a.py
git commit -m "test: actualizar mocks de evaluate() para 3 scroll calls en _extract_linkedin_job_info"
```

---

## Task 5: Smoke test de validación

Esta es la prueba de fuego — correr el pipeline completo y confirmar que el JD se extrae.

**Files:** ninguno — solo ejecución

- [ ] **Step 1: Ejecutar smoke test desde el directorio correcto**

```powershell
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python _smoke_canal_a.py https://www.linkedin.com/jobs/view/4409370270
```

- [ ] **Step 2: Verificar en el output**

Buscar en PASO 1:
```
[Scrape] JD:  XXX chars extraídos    ← debe ser > 100, idealmente > 500
```

Buscar en PASO 3:
```
ATS Score: XX% | Intentos: N | Pasa: True   ← debe ser ≥ 95%
```

- [ ] **Step 3: Si JD = 0 chars, inspeccionar el HTML guardado (Task 1)**

Si el Task 1 quedó activo, el HTML estará en `output/debug/`. Buscar con Ctrl+F:
- La palabra "Publicis" o "Social Analyst" — ¿el texto de descripción está ahí?
- El selector `id="job-details"` — ¿existe?
- `application/ld+json` — ¿tiene `description`?

Con esa información, ajustar los selectores en `_JD_SELECTORS` y repetir.

- [ ] **Step 4: Push a GitHub**

```powershell
git push
```

---

## Self-Review

**Spec coverage:**
- ✅ JD extraction ≥ 100 chars → Task 2 (wait_for_selector + inner_text)
- ✅ "Ver más"/"See more" button expand → Task 2 (step 3, `_SEE_MORE_SELECTORS`)
- ✅ Fallback page.inner_text('body') → Task 2 (step 3, sección 4e)
- ✅ No romper tests existentes → Task 4
- ✅ Smoke test de validación → Task 5
- ✅ Diagnóstico de DOM → Task 1 (temporal)

**Placeholder scan:** ninguno detectado — todo el código está escrito.

**Type consistency:** `_JD_SELECTORS` y `_SEE_MORE_SELECTORS` son `list[str]` definidos en Task 2, usados solo en Task 2. `_extract_linkedin_job_info` retorna `dict` con keys `cargo`, `empresa`, `descripcion` — consistente con el contrato existente en todo el codebase.
