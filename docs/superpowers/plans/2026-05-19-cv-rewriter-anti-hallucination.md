# CV Rewriter Anti-Hallucination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar 5 vectores de alucinación y fragilidad en `cv_rewriter.py` — incluyendo hardcodear el rol de Amazon (igual que LinkedIn) para que su fecha y estructura no dependan nunca del PDF fuente.

**Architecture:** Cuatro capas de corrección (hardcodeo del rol Amazon, sanitización del input al LLM, regla de prompt, post-procesamiento determinístico) más un logger diagnóstico. Sin archivos nuevos — todos los cambios van en `agents/cv_rewriter.py` y `tests/test_cv_rewriter_unit.py`.

**Tech Stack:** Python 3.11 / pytest / re / anthropic

---

## Diagnóstico del PDF fuente real (ejecutado 2026-05-19)

`parse_cv()` sobre `Lorena_Ruiz_CV.pdf` extrae:

| Rol | Fecha en PDF | Descripcion real | Estado |
|-----|-------------|-----------------|--------|
| Amazon | `"May 2025 - current working"` | Genérica ("Set up and optimized Amazon Ads across APAC") | ❌ Fecha incorrecta — debe ser `May 2025 – Feb 2026`. La descripción genérica no incluye logros. |
| Avanti | `"August 2021 - April 2025"` | Correcta: chatbot consulting, government sector, sin paid media | ✅ Descripcion del PDF OK — pero igual debe strippearse (RC-1) para que contenido venga de bullets_por_rol |
| Alcalisa | 2013-2018 | Genérica estratégica | ✅ Historial correcto |
| GRC | 2012-2013 | Genérica | ⚠️ Nombre parseado como "RC S.A." — ya corregido por `_fix_static_fields()` |
| Teleperformance/LinkedIn | **NO está en el PDF** | — | ✅ Ya hardcodeado en `_cv_to_plain_text()` |

**Conclusión:** El PDF tiene dos problemas estructurales — (1) Amazon dice "current working" en vez de "Feb 2026" y (2) no tiene el rol de LinkedIn/Teleperformance. El patrón correcto es el mismo que ya se usa para LinkedIn: **hardcodear el rol de Amazon** para que fecha y estructura nunca dependan del PDF.

---

## Root Causes identificados

| # | Root Cause | Archivo | Línea | Síntoma |
|---|-----------|---------|-------|---------|
| RC-0 | Amazon rol viene del PDF con fecha `"current working"` — frágil, depende de regex | `agents/cv_rewriter.py` | ~209 | En producción: regex corrige "May 2025 – Present" → OK. En tests con CV sintético sin Amazon: LLM inventa fecha "2025 – Present". Fix definitivo: hardcodear Amazon igual que LinkedIn. |
| RC-1 | `_cv_to_plain_text()` pasa `exp["descripcion"]` verbatim al LLM | `agents/cv_rewriter.py` | ~229 | Con CV sintético incorrecto: Avanti muestra "Meta Ads, Google Ads, Amazon Ads USD 200K". Con PDF real: descripcion de Avanti es correcta pero igualmente prescindible — contenido debe venir de bullets_por_rol. |
| RC-2 | Prompt Rule 2 ambigua — LLM trata cifras/herramientas del JD como datos inyectables | `agents/cv_rewriter.py` | `_SYSTEM` | "Google Analytics" en rol LinkedIn (no en narrativas del rol); "USD 150K" atribuido a Amazon DSP sin evidencia |
| RC-3 | Regex de fecha Amazon demasiado estrecho: solo captura `"May 2025 – X"` | `agents/cv_rewriter.py` | ~154 | LLM escribe `"2025 – Present"` sin "May" → regex no aplica. Redundante si RC-0 se implementa, pero se conserva como defensa adicional. |
| RC-4 | Sin validador post-procesamiento para claims USD huérfanos | `agents/cv_rewriter.py` | — | No hay visibilidad de cuándo el LLM inyecta cifras sin evidencia en `bullets_por_rol` |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `agents/cv_rewriter.py` | RC-1: eliminar `exp["descripcion"]`; RC-2: agregar regla `6c`; RC-3: ampliar regex Amazon; RC-4: agregar `_warn_orphan_claims()` |
| `tests/test_cv_rewriter_unit.py` | Agregar 4 clases de tests (8 tests nuevos, sin colisión con las 6 clases existentes) |

---

## Task 0: RC-0 — Hardcodear rol Amazon en `_cv_to_plain_text()` (igual que LinkedIn)

**Problema:** El rol de Amazon viene del PDF con fecha `"May 2025 - current working"`. En producción la regex lo corrige, pero si el LLM reformatea la fecha (o si el PDF está ausente/sintético), la fecha queda incorrecta. El rol de LinkedIn ya está hardcodeado con estructura y datos exactos. Amazon debe seguir el mismo patrón.

**Fix:** Agregar bloque hardcodeado de Amazon en `_cv_to_plain_text()` con `_AMAZON_DATE` y estructura de empresa/mercado correctos, **antes** del loop `for exp in cv.get("experiencia", [])`. El loop sigue procesando los roles históricos (Avanti, Alcalisa, GRC) que SÍ están bien en el PDF. El Amazon hardcodeado reemplaza lo que el PDF dice.

> Nota: El PDF todavía incluirá Amazon en `cv["experiencia"]` — se evita duplicado filtrando por empresa en el loop.

**Files:**
- Modify: `agents/cv_rewriter.py:209-230` (bloque LinkedIn hardcodeado + loop experiencia)
- Test: `tests/test_cv_rewriter_unit.py`

- [ ] **Step 1: Escribir los tests que deben fallar**

```python
# ── RC-0: Amazon debe estar hardcodeado con fecha canónica ────────────────────

class TestCvToPlainTextAmazonHardcoded:

    def test_amazon_date_canonical_in_output(self):
        """_cv_to_plain_text() debe incluir _AMAZON_DATE sin importar lo que diga cv['experiencia']."""
        from agents.cv_rewriter import _cv_to_plain_text, _AMAZON_DATE
        # CV sin Amazon en experiencia (caso smoke test sintético)
        cv = {
            "nombre": "Test",
            "experiencia": [
                {
                    "cargo":   "Digital Channels Consultant",
                    "empresa": "Avanti IT SAS",
                    "fecha":   "August 2021 – April 2025",
                    "descripcion": "SENTINEL",
                }
            ],
            "educacion": [],
            "skills":    [],
            "idiomas":   [],
        }
        result = _cv_to_plain_text(cv, "C")
        assert _AMAZON_DATE in result, (
            f"_AMAZON_DATE '{_AMAZON_DATE}' debe aparecer siempre en el output, "
            f"incluso cuando Amazon no está en cv['experiencia']. "
            f"Obtenido (primeros 600 chars):\n{result[:600]}"
        )

    def test_amazon_not_duplicated_when_in_experiencia(self):
        """Si Amazon viene en cv['experiencia'], no debe aparecer dos veces."""
        from agents.cv_rewriter import _cv_to_plain_text, _AMAZON_DATE
        cv = {
            "nombre": "Test",
            "experiencia": [
                {
                    "cargo":   "Campaign Planner Contractor",
                    "empresa": "Amazon, Colombia",
                    "fecha":   "May 2025 - current working",
                    "descripcion": "Campaign Management across APAC.",
                }
            ],
            "educacion": [],
            "skills":    [],
            "idiomas":   [],
        }
        result = _cv_to_plain_text(cv, "C")
        count = result.count(_AMAZON_DATE)
        assert count == 1, (
            f"_AMAZON_DATE debe aparecer exactamente una vez. Aparece {count} veces."
        )
```

- [ ] **Step 2: Verificar que los tests FALLAN**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
pytest tests/test_cv_rewriter_unit.py::TestCvToPlainTextAmazonHardcoded -v
```

Expected: `test_amazon_date_canonical_in_output` FALLA (Amazon no aparece cuando no está en experiencia).

- [ ] **Step 3: Hardcodear bloque Amazon en `_cv_to_plain_text()`**

En `agents/cv_rewriter.py`, localizar el bloque LinkedIn hardcodeado (~línea 209). **Después** de ese bloque (después del cierre de las líneas de LinkedIn), agregar el bloque Amazon:

```python
    # ── Rol LinkedIn/Teleperformance (hardcodeado — no está en el PDF fuente) ──
    lines += [
        "",
        "Paid Media Specialist / Account Manager, LinkedIn Ads (via Teleperformance for LinkedIn Marketing Solutions)",
        "Teleperformance (contract for LinkedIn Marketing Solutions)",
        "February 2026 – Present  |  Bogotá, Hybrid",
        (
            "Manage and optimize LinkedIn Ads campaigns for 300+ B2B enterprise accounts across "
            "Latin America, executing Sponsored Content, Lead Gen Forms, and Website Conversion "
            "objectives. Monthly managed portfolio: USD 240,000. Market scope: Latin America only."
        ),
    ]

    # ── Rol Amazon (hardcodeado — PDF dice "current working"; fecha real es Feb 2026) ──
    # MARKET: APAC ONLY. Do NOT mention Latin America for this role.
    # Global Account Executives in Singapore, Sydney, Tokyo belong HERE ONLY.
    lines += [
        "",
        "Campaign Planner Contractor",
        "Amazon, Colombia",
        f"{_AMAZON_DATE}  |  Bogotá",
        (
            "Amazon DSP programmatic campaign planning for APAC premium brands. "
            f"Market scope: APAC only. "
            "Supports 4 Global Account Executives (Singapore, Sydney, Tokyo) managing "
            "premium brand accounts with annual sales targets of USD 3M per account."
        ),
    ]

    # ── Roles históricos del PDF (Avanti, Alcalisa, Nexura, GRC) ──
    # Filtrar Amazon para evitar duplicado (viene del PDF con fecha incorrecta).
    _AMAZON_EMPRESA_KEYS = {"amazon", "amazon, colombia"}
    for exp in cv.get("experiencia", []):
        empresa_lower = (exp.get("empresa") or "").lower().strip()
        if empresa_lower in _AMAZON_EMPRESA_KEYS:
            continue  # Ya hardcodeado arriba con fecha canónica
        lines.append("")
        lines.append(exp["cargo"])
        if exp.get("empresa"):
            lines.append(exp["empresa"])
        fecha = _normalize_fecha(exp.get("fecha", ""))
        lines.append(fecha)
        # exp["descripcion"] omitido — contenido viene de bullets_por_rol
```

- [ ] **Step 4: Verificar que los tests PASAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestCvToPlainTextAmazonHardcoded -v
```

Expected: `2 passed`

- [ ] **Step 5: Verificar con el CV real que Amazon no se duplica**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from agents.cv_parser import parse_cv
from agents.cv_rewriter import _cv_to_plain_text, _AMAZON_DATE
cv = parse_cv()
text = _cv_to_plain_text(cv, 'C')
count = text.count(_AMAZON_DATE)
print(f'_AMAZON_DATE aparece {count} veces (esperado: 1)')
print('--- Primeras 800 chars ---')
print(text[:800])
"
```

Expected: `_AMAZON_DATE aparece 1 veces`

- [ ] **Step 6: Correr suite completa — sin regresiones**

```bash
pytest tests/test_cv_rewriter_unit.py -v --tb=short
```

Expected: todos passing.

- [ ] **Step 7: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "fix(cv_rewriter): hardcodear rol Amazon con _AMAZON_DATE — elimina dependencia del PDF fuente"
```

---

## Task 1: RC-1 — Eliminar `exp["descripcion"]` de `_cv_to_plain_text()`

**Problema:** `_cv_to_plain_text()` (línea ~229) incluye `exp["descripcion"]` en el texto que se envía al LLM. El LLM lo trata como "fuente de verdad" y amplifica sus afirmaciones. En el smoke test, Avanti IT SAS (consultora de chatbots para sector público) mostró: *"Gestionó campañas en Meta Ads, Google Ads y Amazon Ads con presupuestos USD 200K optimizando ROAS y CPA"* — porque el campo `descripcion` del CV sintético lo afirmaba.

**Fix:** Eliminar las 2 líneas que agregan `exp["descripcion"]`. El contenido del rol viene exclusivamente de `bullets_por_rol` vía `_enrich_with_narratives()`.

**Files:**
- Modify: `agents/cv_rewriter.py:221-230`
- Test: `tests/test_cv_rewriter_unit.py`

- [ ] **Step 1: Escribir los tests que deben fallar**

Agregar al final de `tests/test_cv_rewriter_unit.py`:

```python
# ── RC-1: _cv_to_plain_text no debe incluir exp["descripcion"] ────────────────

class TestCvToPlainTextStripsDescripcion:

    def test_descripcion_not_in_plain_text(self):
        """exp['descripcion'] NO debe aparecer en _cv_to_plain_text().
        El contenido del rol viene de bullets_por_rol via _enrich_with_narratives()."""
        from agents.cv_rewriter import _cv_to_plain_text
        cv = {
            "nombre": "Test",
            "experiencia": [{
                "cargo":       "Digital Channels Consultant",
                "empresa":     "Avanti IT SAS",
                "fecha":       "August 2021 – April 2025",
                "descripcion": "SENTINEL_HALLUCINACION Meta Ads Google Ads USD 200K ROAS CPA",
            }],
            "educacion": [],
            "skills":    [],
            "idiomas":   [],
        }
        result = _cv_to_plain_text(cv, "C")
        assert "SENTINEL_HALLUCINACION" not in result, (
            "exp['descripcion'] no debe aparecer en _cv_to_plain_text(). "
            f"Fragmento obtenido: {result[:400]}"
        )

    def test_role_metadata_still_present_without_descripcion(self):
        """cargo, empresa y fecha deben seguir presentes aunque se elimine descripcion."""
        from agents.cv_rewriter import _cv_to_plain_text
        cv = {
            "nombre": "Test",
            "experiencia": [{
                "cargo":       "Digital Channels Consultant",
                "empresa":     "Avanti IT SAS",
                "fecha":       "August 2021 – April 2025",
                "descripcion": "SENTINEL",
            }],
            "educacion": [],
            "skills":    [],
            "idiomas":   [],
        }
        result = _cv_to_plain_text(cv, "C")
        assert "Digital Channels Consultant" in result
        assert "Avanti IT SAS" in result
        assert "August 2021" in result
```

- [ ] **Step 2: Verificar que los tests FALLAN**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
pytest tests/test_cv_rewriter_unit.py::TestCvToPlainTextStripsDescripcion -v
```

Expected: `FAILED` — `SENTINEL_HALLUCINACION` SÍ aparece en el output actual (comportamiento a corregir).

- [ ] **Step 3: Eliminar `exp["descripcion"]` de `_cv_to_plain_text()`**

En `agents/cv_rewriter.py`, localizar el loop `for exp in cv.get("experiencia", []):` (~línea 221). Cambiar:

```python
    for exp in cv.get("experiencia", []):
        lines.append("")
        lines.append(exp["cargo"])
        if exp.get("empresa"):
            lines.append(exp["empresa"])
        fecha = _normalize_fecha(exp.get("fecha", ""))
        lines.append(fecha)
        if exp.get("descripcion"):           # ← ELIMINAR ESTA LÍNEA
            lines.append(exp["descripcion"]) # ← ELIMINAR ESTA LÍNEA
```

Después del fix:

```python
    for exp in cv.get("experiencia", []):
        lines.append("")
        lines.append(exp["cargo"])
        if exp.get("empresa"):
            lines.append(exp["empresa"])
        fecha = _normalize_fecha(exp.get("fecha", ""))
        lines.append(fecha)
        # exp["descripcion"] omitido intencionalmente.
        # El contenido del rol viene de bullets_por_rol vía _enrich_with_narratives(),
        # lo que evita que el LLM amplifique afirmaciones no verificadas del CV fuente.
```

- [ ] **Step 4: Verificar que los tests PASAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestCvToPlainTextStripsDescripcion -v
```

Expected: `2 passed`

- [ ] **Step 5: Correr suite completa — sin regresiones**

```bash
pytest tests/test_cv_rewriter_unit.py tests/test_cv_rewriter.py -v --tb=short
```

Expected: todos los tests anteriores pasan + 2 nuevos.

- [ ] **Step 6: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "fix(cv_rewriter): strip exp[descripcion] from plain text — contenido viene de bullets_por_rol"
```

---

## Task 2: RC-2 — Agregar regla de aislamiento JD al `_SYSTEM` prompt

**Problema:** La regla 2 del prompt dice *"use only data already present in the source"* pero "source" es ambiguo — el LLM trata las cifras del JD (ej. `USD 150,000` pedido por OMD) y herramientas del JD (ej. `Google Analytics`) como datos inyectables en cualquier rol. Resultado: "Google Analytics" apareció en el rol de LinkedIn Ads (no documentado en narrativas de ese rol) y "USD 150K" se atribuyó a Amazon DSP sin evidencia.

**Fix:** Agregar regla `6c` explícita: los datos del JD son *targets de matching*, no fuentes de hechos. Una cifra o herramienta del JD solo puede aparecer en un rol si ya está en los bullets de ese rol en `KEY ACHIEVEMENTS`.

**Files:**
- Modify: `agents/cv_rewriter.py` — `_SYSTEM` string (después del bloque `6b.`, antes de `CONTENT AND STRUCTURE`)
- Test: `tests/test_cv_rewriter_unit.py`

- [ ] **Step 1: Escribir el test que debe fallar**

```python
# ── RC-2: _SYSTEM debe contener regla de aislamiento de datos del JD ──────────

class TestSystemPromptJdIsolation:

    def test_system_prompt_contains_jd_isolation_rule(self):
        """_SYSTEM debe prohibir explícitamente inyectar datos del JD sin evidencia en bullets."""
        from agents.cv_rewriter import _SYSTEM
        assert "JD DATA ISOLATION" in _SYSTEM, (
            "_SYSTEM no contiene la regla 'JD DATA ISOLATION'. "
            "Agrega la regla 6c después del bloque 6b en _SYSTEM."
        )
        # Verifica que la regla prohíbe explícitamente el uso de cifras del JD
        assert "NOT facts" in _SYSTEM or "not facts" in _SYSTEM.lower(), (
            "La regla 6c debe dejar claro que los datos del JD no son hechos inyectables."
        )
```

- [ ] **Step 2: Verificar que el test FALLA**

```bash
pytest tests/test_cv_rewriter_unit.py::TestSystemPromptJdIsolation -v
```

Expected: `FAILED` — `JD DATA ISOLATION` no existe en `_SYSTEM` actual.

- [ ] **Step 3: Agregar regla `6c` al `_SYSTEM`**

En `agents/cv_rewriter.py`, localizar este bloque en `_SYSTEM` (alrededor de la línea que dice `"If a bullet is not listed under an employer, omit it. Never fabricate or borrow from another section."`):

```python
   If a bullet is not listed under an employer, omit it. Never fabricate or borrow from another section.

CONTENT AND STRUCTURE
```

Reemplazar con:

```python
   If a bullet is not listed under an employer, omit it. Never fabricate or borrow from another section.

6c. JD DATA ISOLATION: Metrics, USD amounts, percentages, platform names, and tool names \
from the JOB DESCRIPTION are targets to match using existing evidence — they are NOT facts \
to inject. Never use a figure or tool name from the JD as a claim in a role's CV section \
unless it already appears verbatim or numerically in that role's section within KEY ACHIEVEMENTS. \
If the JD mentions a tool (e.g. Google Analytics) or a budget figure (e.g. USD 150,000) that \
has no matching bullet under that role in KEY ACHIEVEMENTS, omit it entirely. \
Do not fabricate evidence to satisfy JD requirements.

CONTENT AND STRUCTURE
```

- [ ] **Step 4: Verificar que el test PASA**

```bash
pytest tests/test_cv_rewriter_unit.py::TestSystemPromptJdIsolation -v
```

Expected: `1 passed`

- [ ] **Step 5: Correr suite completa — sin regresiones**

```bash
pytest tests/test_cv_rewriter_unit.py -v --tb=short
```

Expected: todos passing.

- [ ] **Step 6: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "fix(cv_rewriter): add JD data isolation rule 6c — cifras del JD son targets, no datos inyectables"
```

---

## Task 3: RC-3 — Ampliar regex de fecha Amazon en `_fix_static_fields()`

**Problema:** `_fix_static_fields()` corrige fechas de Amazon con `r"May\s+2025\s*[–\-]\s*[^\n]+"`. Si el LLM escribe `"2025 – Present"` o `"2025 – Feb 2026"` (sin "May"), la regex no matchea y la fecha incorrecta persiste. Observado en smoke test: Amazon mostró `"2025 – Present | Bogotá"` en vez de `"May 2025 – Feb 2026"`.

**Fix:** Agregar una regex fallback que captura los patrones sin "May".

**Files:**
- Modify: `agents/cv_rewriter.py:152-158` (función `_fix_static_fields()`)
- Test: `tests/test_cv_rewriter_unit.py`

- [ ] **Step 1: Escribir los tests que deben fallar**

```python
# ── RC-3: _fix_static_fields() debe corregir fecha Amazon sin "May" ───────────

class TestFixStaticFieldsAmazonDate:

    def test_amazon_date_fixed_when_may_dropped(self):
        """'2025 – Present' (LLM omitió 'May') debe corregirse a la fecha canónica."""
        from agents.cv_rewriter import _fix_static_fields, _AMAZON_DATE
        cv_text = (
            "Campaign Planner, Amazon Ads\n"
            "2025 – Present | Bogotá\n"
            "Amazon, Colombia\n"
            "- Managed campaigns.\n"
        )
        result = _fix_static_fields(cv_text)
        assert "2025 – Present" not in result, (
            f"'2025 – Present' debe reemplazarse por la fecha canónica. Obtenido:\n{result}"
        )
        assert _AMAZON_DATE in result, (
            f"La fecha canónica '{_AMAZON_DATE}' debe aparecer. Obtenido:\n{result}"
        )

    def test_amazon_date_fixed_when_february_2026_variant(self):
        """'2025 – February 2026' también debe corregirse."""
        from agents.cv_rewriter import _fix_static_fields, _AMAZON_DATE
        cv_text = "Campaign Planner, Amazon Ads\n2025 – February 2026 | Bogotá\n"
        result = _fix_static_fields(cv_text)
        assert "2025 – February 2026" not in result
        assert _AMAZON_DATE in result

    def test_canonical_amazon_date_unchanged(self):
        """La forma canónica 'May 2025 – Feb 2026' debe mantenerse correcta."""
        from agents.cv_rewriter import _fix_static_fields, _AMAZON_DATE
        cv_text = f"Campaign Planner\n{_AMAZON_DATE}\nAmazon, Colombia\n"
        result = _fix_static_fields(cv_text)
        assert _AMAZON_DATE in result
```

- [ ] **Step 2: Verificar que los tests FALLAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestFixStaticFieldsAmazonDate -v
```

Expected: `test_amazon_date_fixed_when_may_dropped` y `test_amazon_date_fixed_when_february_2026_variant` FALLAN. `test_canonical_amazon_date_unchanged` PASA (ya funciona).

- [ ] **Step 3: Agregar regex fallback en `_fix_static_fields()`**

En `agents/cv_rewriter.py`, localizar el bloque "# 2. Enforce Amazon role date" (~línea 152). Cambiar:

```python
    # 2. Enforce Amazon role date — always override whatever the LLM wrote.
    #    Matches any "May 2025 – <anything>" line (including "Present" if LLM hallucinates it).
    cv_text = re.sub(
        r"May\s+2025\s*[–\-]\s*[^\n]+",
        _AMAZON_DATE,
        cv_text,
    )
```

Por:

```python
    # 2. Enforce Amazon role date — always override whatever the LLM wrote.
    #    Primary:  "May 2025 – <anything>" — forma canónica y "May 2025 – Present".
    #    Fallback: "2025 – Present" o "2025 – Feb(ruary) 2026" — LLM omitió "May".
    cv_text = re.sub(
        r"May\s+2025\s*[–\-]\s*[^\n]+",
        _AMAZON_DATE,
        cv_text,
    )
    cv_text = re.sub(
        r"\b2025\s*[–\-]\s*(?:Present|Feb(?:ruary)?\s+2026)\b[^\n]*",
        _AMAZON_DATE,
        cv_text,
    )
```

- [ ] **Step 4: Verificar que los tests PASAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestFixStaticFieldsAmazonDate -v
```

Expected: `3 passed`

- [ ] **Step 5: Correr suite completa — sin regresiones**

```bash
pytest tests/test_cv_rewriter_unit.py -v --tb=short
```

Expected: todos passing.

- [ ] **Step 6: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "fix(cv_rewriter): ampliar regex fecha Amazon — captura '2025 – Present' sin 'May'"
```

---

## Task 4: RC-4 — Agregar `_warn_orphan_claims()` como logger diagnóstico

**Problema:** No hay visibilidad sobre cuándo el LLM pone montos USD en el CV que no están en ningún bullet de `bullets_por_rol`. Este diagnostic logger (no bloqueante) imprime warnings cada vez que detecta un monto USD en el CV generado que no aparece en los bullets.

**Fix:** Función `_warn_orphan_claims(cv_text, bullets_por_rol) -> list[str]` + llamada dentro de `rewrite()` después de cada `_rewrite_once()`.

**Files:**
- Modify: `agents/cv_rewriter.py` — agregar `_warn_orphan_claims()` después de `_load_bullets_por_rol()` (~línea 274); agregar llamada en `rewrite()` dentro del loop de intentos (~línea 595)
- Test: `tests/test_cv_rewriter_unit.py`

- [ ] **Step 1: Escribir los tests que deben fallar**

```python
# ── RC-4: _warn_orphan_claims() detecta montos USD huérfanos ──────────────────

class TestWarnOrphanClaims:

    def test_flags_usd_amount_not_in_any_bullet(self):
        """USD amount en CV ausente de todos los bullets → warning en lista."""
        from agents.cv_rewriter import _warn_orphan_claims
        bullets_por_rol = {
            "avanti": {
                "empresa": "Avanti IT SAS",
                "bullets": ["Managed Chatico: 575,134 conversations in 9 months."],
            }
        }
        cv_text = "- Managed campaigns with USD 999,999 monthly budget."
        warnings = _warn_orphan_claims(cv_text, bullets_por_rol)
        assert len(warnings) > 0, (
            "Debe haber al menos un warning para USD 999,999 no presente en bullets."
        )
        assert any("999" in w for w in warnings), (
            f"El warning debe mencionar la cifra huérfana. Warnings: {warnings}"
        )

    def test_no_warning_for_authorized_usd(self):
        """USD amount presente en bullets → no warning."""
        from agents.cv_rewriter import _warn_orphan_claims
        bullets_por_rol = {
            "linkedin": {
                "empresa": "Teleperformance",
                "bullets": ["Manages 300 accounts with monthly portfolio USD 240,000."],
            }
        }
        cv_text = "- Manages portfolio of USD 240,000 monthly."
        warnings = _warn_orphan_claims(cv_text, bullets_por_rol)
        assert not any("240" in w for w in warnings), (
            f"USD 240,000 está en bullets — no debe generar warning. Warnings: {warnings}"
        )

    def test_returns_empty_when_bullets_por_rol_is_none(self):
        """Con bullets_por_rol=None no debe lanzar excepción ni devolver warnings."""
        from agents.cv_rewriter import _warn_orphan_claims
        result = _warn_orphan_claims("- USD 999,999 budget.", None)
        assert result == [], f"Esperado [], obtenido {result}"

    def test_returns_empty_when_no_usd_in_cv(self):
        """Sin montos USD en el CV, retorna lista vacía."""
        from agents.cv_rewriter import _warn_orphan_claims
        bullets_por_rol = {"avanti": {"empresa": "Avanti IT SAS", "bullets": ["Led chatbot."]}}
        result = _warn_orphan_claims("- Led conversational flow optimization.", bullets_por_rol)
        assert result == []
```

- [ ] **Step 2: Verificar que los tests FALLAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestWarnOrphanClaims -v
```

Expected: `FAILED` — `_warn_orphan_claims` no existe todavía.

- [ ] **Step 3: Implementar `_warn_orphan_claims()`**

En `agents/cv_rewriter.py`, agregar después de `_load_bullets_por_rol()` (~línea 274), antes de `_enrich_with_narratives()`:

```python
_USD_RE = re.compile(r"\bUSD\s*[\d,]+(?:\.\d+)?(?:\s*[KkMm])?\b")


def _warn_orphan_claims(cv_text: str, bullets_por_rol: dict | None) -> list[str]:
    """
    Detecta montos USD en el CV generado que no aparecen en ningún bullet de bullets_por_rol.
    No-blocking: retorna lista de strings descriptivos para logging. No rechaza el CV.
    Retorna [] si bullets_por_rol es None o vacío.
    """
    if not bullets_por_rol:
        return []

    # Texto completo de todos los bullets (minúsculas para comparación)
    all_bullet_text = " ".join(
        b
        for rol in bullets_por_rol.values()
        if isinstance(rol, dict)
        for b in rol.get("bullets", [])
    ).lower()
    authorized = set(_USD_RE.findall(all_bullet_text))

    # Montos USD encontrados en el CV generado
    cv_usd = set(_USD_RE.findall(cv_text.lower()))
    orphan = cv_usd - authorized

    return [
        f"USD amount '{amt}' in CV has no matching bullet in bullets_por_rol"
        for amt in sorted(orphan)
    ]
```

- [ ] **Step 4: Agregar llamada en `rewrite()` dentro del loop de intentos**

En `agents/cv_rewriter.py`, dentro del loop `for attempt in range(1, max_attempts + 1):`, después de `print(f"[CVRewriter] Score ATS: {score}%")` (~línea 598):

```python
        print(f"[CVRewriter] Score ATS: {score}%")

        # Diagnóstico: montos USD sin evidencia en bullets_por_rol
        _bpr = _load_bullets_por_rol()
        for _w in _warn_orphan_claims(result["cv_text"], _bpr):
            print(f"[CVRewriter] ⚠️  ORPHAN CLAIM: {_w}")
```

- [ ] **Step 5: Verificar que los tests PASAN**

```bash
pytest tests/test_cv_rewriter_unit.py::TestWarnOrphanClaims -v
```

Expected: `4 passed`

- [ ] **Step 6: Correr suite completa — sin regresiones**

```bash
pytest tests/test_cv_rewriter_unit.py -v --tb=short
```

Expected: todos passing.

- [ ] **Step 7: Commit**

```bash
git add agents/cv_rewriter.py tests/test_cv_rewriter_unit.py
git commit -m "feat(cv_rewriter): add _warn_orphan_claims() — detecta montos USD huerfanos en CV generado"
```

---

## Task 5: Smoke test de regresión

Verificar que los 4 fixes funcionan juntos con el mismo smoke test que descubrió los bugs.

**Files:**
- Run: `_smoke_falabella.py` (ya existe en raíz del proyecto)

- [ ] **Step 1: Correr el smoke test completo**

```bash
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python _smoke_falabella.py 2>&1
```

- [ ] **Step 2: Verificar el output del Caso C (path del SÍ)**

Buscar en el output:

```
✅ [EvidenceMap] N skills — T1/T2/T3   (pipeline de evidencia funcionando)
✅ Status: enviado o pendiente_envio
✅ Sin línea "ORPHAN CLAIM: USD amount 'usd 150,000'"  (fix RC-2 + RC-4)
✅ Fecha Amazon en PDF: May 2025 – Feb 2026  (fix RC-3)
```

Si aparece algún `⚠️ ORPHAN CLAIM` residual, registrarlo como issue menor para el siguiente ciclo (no bloquea este plan).

- [ ] **Step 3: Correr suite de tests completa**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -25
```

Expected: `328 passed` (baseline) + 8 tests nuevos = ~336 passed. Todos en verde.

- [ ] **Step 4: Commit final si hay cambios en `_smoke_falabella.py`**

```bash
git add _smoke_falabella.py
git commit -m "test: smoke test regression — verifica fixes anti-alucinacion RC-1 a RC-4"
```

---

## Self-Review

### Spec coverage
| Root Cause | Task | Cubierto |
|---|---|---|
| RC-1: `exp["descripcion"]` inyectado | Task 1 | ✅ |
| RC-2: JD datos inyectables sin restricción | Task 2 | ✅ |
| RC-3: regex fecha Amazon estrecho | Task 3 | ✅ |
| RC-4: sin visibilidad de claims huérfanos | Task 4 | ✅ |
| Regresión smoke test | Task 5 | ✅ |

### Placeholder scan
- Sin TBD, TODO, ni frases vagas. Cada step tiene código exacto.

### Type consistency
- `_warn_orphan_claims(cv_text: str, bullets_por_rol: dict | None) -> list[str]` — firma consistente en implementación y tests.
- `_fix_static_fields(cv_text: str) -> str` — firma sin cambios, consistente.
- `_AMAZON_DATE: str` — importado correctamente en los tests de Task 3.
- `_USD_RE` — constante de módulo, accesible desde los tests vía import de `_warn_orphan_claims`.

### Notas para iteración futura (fuera de scope de este plan)
- `_PROFILE_BY_RAMA["C"]` menciona "Amazon Ads (Sponsored Products, Sponsored Brands)" pero las narrativas dicen "Amazon DSP programmatic — no Seller/Vendor Central". Ajustar el profile template en un plan separado.
- `_warn_orphan_claims()` solo detecta USD amounts. Una versión futura podría detectar plataformas específicas (Google Analytics, Tableau) sin evidencia en el rol correcto.
