# Contexto de Sesión — Job Application Agent

**Última actualización:** 2026-05-15 (smoke ronda 3 — 267 tests — Canal A aprobado)
**Proyecto:** Sistema multi-agente para búsqueda y aplicación automatizada de empleo para Lorena Ruiz

---

## Estado actual del proyecto

**CANAL A APROBADO SMOKE TEST RONDA 3 — 267/267 tests GREEN**
**GitHub:** `https://github.com/lilianlorenaruiz-commits/JobAppAgent` — commit `db30d13` (HEAD)

| Canal | Estado | Smoke test | Resultado |
|---|---|---|---|
| A — LinkedIn Easy Apply | ✅ APROBADO | Falabella PM Vestuario `4412781665` — 2026-05-15 | JD 1403 chars, ATS 96%, enviado True |
| B — Portal empresa | ✅ APROBADO | Manpower Group computrabajo — 2026-05-14 | OK |
| C — Email draft | ✅ APROBADO | Gmail Compose + Telegram — anterior | OK |

---

## Arquitectura: 6 Agentes

1. **Orquestador** `main.py` — loop diario 08:00 con `schedule`
2. **Scraper** `agents/scraper.py` — LinkedIn Jobs vía Apify + deduplicación + filtro seniority
3. **Skill Matcher** `agents/skill_matcher.py` — 40% keyword + 60% Claude semántico, threshold 85%
4. **CV Rewriter** `agents/cv_rewriter.py` — 25 reglas, anti-invención, educación hardcoded, detección idioma JD
5. **Applicator** `agents/applicator.py` — 3 canales (A/B/C) con HITL Telegram
6. **Reporter** `agents/reporter.py` — SQLite + Telegram diario

---

## Archivos clave del proyecto

| Archivo | Propósito |
|---|---|
| `config.py` | Config global: rutas, API keys, flags HITL |
| `agents/applicator.py` | Agente principal — Canal A/B/C |
| `agents/telegram_hitl.py` | Notificaciones + HITL (urllib puro, sin asyncio) |
| `agents/cv_rewriter.py` | Reescritura CV con Claude — detección idioma JD |
| `_smoke_canal_a.py` | Smoke test Canal A (pipeline completo: scrape→rewrite→PDF→apply) |
| `_smoke_canal_b.py` | Smoke test Canal B |
| `_setup_browser.py` | Inicializa sesión LinkedIn en `browser_profile/` |
| `_preflight.py` | Preflight check de APIs y configuración |
| `_schedule_task.py` | Registra tarea Windows diaria 08:00 |
| `narrativas/narrativas_lorena.json` | Bullets validados por Lorena (fuente de verdad) |
| `profiles/perfil_*.json` | Perfiles A/B/C con skills target |
| `config/candidate_profile.json` | Respuestas estables de Lorena para formularios |
| `browser_profile/` | Perfil persistente Chromium con sesión LinkedIn |

---

## Test Suite — 267 tests

```bash
python -m pytest -q    # → 267 passed (2026-05-15)
```

| Archivo | Tests | Cubre |
|---|---|---|
| `test_applicator_canal_a.py` | 79 | Canal A completo: smart fill, HITL SI/NO, JD extraction 3 estrategias, BUG-001/C/D |
| `test_applicator_canal_b.py` | 11 | Canal B |
| `test_applicator_controlled.py` | 29 | Pre-producción checklist |
| `test_applicator_v2.py` | 12 | Canal C email body |
| `test_applicator.py` | 17 | Canal detection |
| `test_telegram_hitl.py` | 19 | HITL wait_for_approval + send_message_sync |
| `test_cv_rewriter.py` | 37 | CV rewriting 25 reglas |
| `test_cv_rewriter_unit.py` | 17 | CV rewriting unidad + detección idioma JD |
| `test_narrative_builder.py` | 13 | Bullets validados |
| `test_pdf_generator.py` | 10 | PDF 2 páginas, nombre correcto |
| `test_ats_auditor.py` | 8 | ATS score |
| `test_pipeline.py` | 7 | End-to-end dry-run |
| `test_config_hitl.py` | 2 | HITL timeout config |

---

## Canal A — Lecciones aprendidas (2026-05-15)

### BUG-001 root cause definitivo
El perfil de LinkedIn de Lorena está en **español Colombia**. El marcador de sección de descripción es **"Acerca del empleo"** — no "About the job" ni "Acerca del puesto". Una sola variante faltante causaba 0 chars de extracción y ATS 70%.

### JD Extraction — estrategia multicapa
```python
_JD_START_MARKERS = [
    "About the job", "About this job", "Job description",
    "Acerca del empleo",   # ← confirmado 2026-05-15 en perfil ES-CO de Lorena
    "Acerca del puesto",
]
_JD_END_MARKERS = [
    "Show more jobs", "More jobs", "Más empleos",
    "Mostrar más empleos", "Mostrar más",
    "People also viewed", "Personas que también",
    "LinkedIn members give", "You applied",
    "Solicitud enviada", "Similar jobs", "Empleos similares",
]
```
- **4a XPath:** busca elemento por texto con marcadores
- **4b body.innerText:** parsea entre START y END markers
- **4c JSON-LD:** fallback con application/ld+json

### Scroll para lazy-load
Playwright necesita ~4s después de cargar para que React renderice la descripción:
```python
page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")  # 1.5s
page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2 / 3)")  # 1.5s
page.evaluate("window.scrollTo(0, 0)")  # 1s
```

### Shadow DOM de LinkedIn
`document.querySelectorAll('button')` NO encuentra "Solicitud sencilla".
**Fix:** `page.get_by_role("button")` penetra shadow DOM.

### Badge misclick
`page.locator("text=Solicitud sencilla")` encuentra badges de "Similar Jobs" y navega al trabajo equivocado.
**Fix:** `get_by_role("button", name=regex)` primero — solo botones reales.

### Botones bilingües
LinkedIn español: "Siguiente", "Revisar tu solicitud", "Enviar solicitud"
LinkedIn inglés: "Next", "Review your application", "Submit application"
`_find_next_button()` y `_find_submit_button()` cubren ambos idiomas.

### Fix asyncio Canal A y B
`asyncio.run()` NO puede correr dentro del event loop de Playwright sync API.
- **Canal A:** `_linkedin_playwright_loop()` retorna `None` → `_apply_linkedin()` llama `_apply_web()` DESPUÉS del `with sync_playwright()`.
- **Canal B:** `send_cv_ready_browser()` se llama ANTES del `with sync_playwright()`.
- **send_message_sync / send_screenshot_for_approval_sync:** usan `urllib` puro — seguros dentro del context manager.

### _maybe_upload_cv
File inputs en LinkedIn son siempre `visibility:hidden`. `is_visible()` siempre False.
**Fix:** llamar `set_input_files()` directamente sin check de visibilidad.

### Emoji en Windows console
`print()` con emojis (❌, ✅) falla en consola Windows cp1252.
**Fix en send_message_sync:**
```python
enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
safe = text[:60].encode(enc, errors="replace").decode(enc)
```

### HITL — rutas verificadas
- **SI (primera vez real 2026-05-15):** screenshot Telegram → Lorena aprueba → submit enviado ✅
- **NO (verificado 2026-05-15):** Escape + ctx.close() inmediato + notificación cancelación ✅

---

## candidate_profile.json

`config/candidate_profile.json`:
```json
{
  "salary_cop_monthly":        "6500000",
  "city":                      "Bogotá D.C., Colombia",
  "willing_to_travel":         "Sí",
  "willing_to_relocate":       "No",
  "availability":              "Inmediata",
  "english_level":             "C2 - Proficiencia completa",
  "requires_visa_sponsorship": "No",
  "work_authorization":        "Sí",
  "years_experience":          "14"
}
```

`_match_profile_question(question, profile)` → respuesta directa sin LLM. Si no match → Claude Haiku fallback.

---

## Bugs históricos resueltos

| Bug | Sesión | Fix |
|---|---|---|
| Salary field texto vs decimal | 2026-05-14 | `salary_cop_monthly` = "6500000" |
| HITL timeout 5 min insuficiente | 2026-05-14 | HITL_TIMEOUT_S: 300 → 600 |
| No extraía cargo/empresa/JD | 2026-05-14 | `_extract_linkedin_job_info(page)` |
| Smoke test usaba PDF estático | 2026-05-14 | pipeline completo en _smoke_canal_a.py |
| BUG-A: selectores DOM LinkedIn muertos | 2026-05-14 | page.title() → _parse_title_for_job_info() |
| BUG-D: HITL en Review no en Submit | 2026-05-14 | _find_submit_button() separado |
| BUG-C: _maybe_upload_cv is_visible() | 2026-05-14 | remover is_visible(), directo set_input_files() |
| BUG-B: cv_rewriter siempre en inglés | 2026-05-14 | detectar idioma JD → escribir en ese idioma |
| BUG-001: JD 0 chars / ATS 70% | 2026-05-15 | XPath+body.innerText+"Acerca del empleo" |
| HITL NO esperaba 10 min | 2026-05-15 | Escape+ctx.close() inmediato |
| Emoji ❌ UnicodeEncodeError Windows | 2026-05-15 | encode+errors=replace en print |

---

## APIs y configuración

| Servicio | Archivo | Estado |
|---|---|---|
| Anthropic API | `config/anthropic_key.txt` | ACTIVA |
| Telegram Bot | `config/telegram_token.txt` | Activo — @LilianAgent_lorenaRuiz_bot |
| Apify | `config/apify_key.txt` | Configurada |
| LinkedIn Session | `browser_profile/` | Guardada (perfil ES-CO de Lorena) |
| Windows Task | `JobAppAgent_LorenaRuiz` 08:00 | Registrada |

---

## Roles y fechas canónicas de Lorena

| Rol | Empresa | Fecha | Mercado |
|---|---|---|---|
| Paid Media Specialist / AM LinkedIn Ads | Teleperformance (LinkedIn) | Feb 2026 – Present | Latin America ONLY |
| Campaign Planner Contractor | Amazon, Colombia | May 2025 – Feb 2026 | APAC ONLY |
| Digital Channels Consultant | Avanti IT SAS | Aug 2021 – Apr 2025 | Colombia |
| Marketing Manager | Alcalisa S.A. | 2013 – 2018 | Ecuador |
| Commercial Director | GRC S.A. | 2012 – 2013 | Ecuador / China / Russia |

**NUNCA mezclar mercados APAC/LATAM.**

---

## Comandos de producción

```bash
# Setup inicial (una vez)
python _setup_browser.py      # inicializar sesión LinkedIn
python _schedule_task.py      # registrar tarea Windows 08:00

# Verificación
python _preflight.py          # check APIs y configuración
python -m pytest -q           # → 267 passed

# Smoke tests manuales
python _smoke_canal_a.py https://www.linkedin.com/jobs/view/XXXXXXX
python _smoke_canal_b.py

# Producción
python main.py --once --dry-run --rama C    # dry-run una vez
python main.py --once --rama C              # real una vez
python main.py                              # loop diario 08:00
```
