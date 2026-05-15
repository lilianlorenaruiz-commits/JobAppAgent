# Contexto de Sesión — Job Application Agent

**Última actualización:** 2026-05-14
**Proyecto:** Sistema multi-agente para búsqueda y aplicación automatizada de empleo para Lorena Ruiz

---

## Estado actual del proyecto

**TODOS LOS CANALES APROBADOS EN SMOKE TEST REAL — 186/186 tests GREEN**

| Canal | Estado | Smoke test |
|---|---|---|
| A — LinkedIn Easy Apply | ✅ APROBADO | OMD Colombia `4405866108` — 2026-05-14 |
| B — Portal empresa | ✅ APROBADO | Manpower Group computrabajo |
| C — Email draft | ✅ APROBADO | Gmail Compose + Telegram |

---

## Arquitectura: 6 Agentes

1. **Orquestador** `main.py` — loop diario 08:00 con `schedule`
2. **Scraper** `agents/scraper.py` — LinkedIn Jobs vía Apify + deduplicación + filtro seniority
3. **Skill Matcher** `agents/skill_matcher.py` — 40% keyword + 60% Claude semántico, threshold 85%
4. **CV Rewriter** `agents/cv_rewriter.py` — 25 reglas, anti-invención, educación hardcoded, `_fix_static_fields()`
5. **Applicator** `agents/applicator.py` — 3 canales (A/B/C) con HITL Telegram
6. **Reporter** `agents/reporter.py` — SQLite + Telegram diario

---

## Archivos clave del proyecto

| Archivo | Propósito |
|---|---|
| `config.py` | Config global: rutas, API keys, flags HITL |
| `agents/applicator.py` | Agente principal — Canal A/B/C |
| `agents/telegram_hitl.py` | Notificaciones + HITL (urllib, sin asyncio) |
| `_smoke_canal_a.py` | Smoke test Canal A (URL OMD Colombia) |
| `_smoke_canal_b.py` | Smoke test Canal B |
| `_setup_browser.py` | Inicializa sesión LinkedIn en `browser_profile/` |
| `_preflight.py` | Preflight check de APIs y configuración |
| `_schedule_task.py` | Registra tarea Windows diaria 08:00 |
| `narrativas/narrativas_lorena.json` | Bullets validados por Lorena (fuente de verdad) |
| `profiles/perfil_*.json` | Perfiles A/B/C con skills target |
| `browser_profile/` | Perfil persistente Chromium con sesión LinkedIn |

---

## Canal A — LinkedIn Easy Apply — Lecciones aprendidas

### Shadow DOM de LinkedIn
`document.querySelectorAll('button')` NO encuentra "Solicitud sencilla" — está en shadow DOM.
**Fix:** `page.get_by_role("button")` y `page.locator("text=X")` penetran shadow DOM.
**Fix:** Esperar 3-4s después de cargar la página antes de buscar el botón.

### Badge misclick
`page.locator("text=Solicitud sencilla")` encuentra badges de "Similar Jobs" y navega al trabajo equivocado.
**Fix:** `get_by_role("button", name=regex)` primero — solo botones reales, no badges `<a>/<span>`.

### Botones bilingües
LinkedIn español: "Siguiente", "Revisar tu solicitud", "Enviar solicitud", "Review"
LinkedIn inglés: "Next", "Review your application", "Submit application"
`_find_next_button()` y detección de submit cubren ambos idiomas.

### Campos numéricos
`_fill_free_text_fields` excluye `input[type=number]` y `inputmode=numeric/decimal`.
Claude no puede inventar salarios. Próxima mejora: `candidate_profile.json`.

### Fix asyncio Canal A y B
`asyncio.run()` no puede correr dentro del event loop de Playwright sync API.
**Fix Canal A:** `_linkedin_playwright_loop()` retorna `None` → `_apply_linkedin()` llama `_apply_web()` DESPUÉS de que cierra el `with sync_playwright()`.
**Fix Canal B:** `send_cv_ready_browser()` se llama ANTES del `with sync_playwright()`.

### Ya aplicado
`_linkedin_playwright_loop()` verifica `text=Solicitud enviada` antes de buscar el botón.
Si ya fue aplicado → retorna `enviado=True` sin reenviar.

---

## Test Suite — 186 tests

```bash
python -m pytest -q    # → 186 passed
```

| Archivo | Tests | Cubre |
|---|---|---|
| `test_applicator_canal_a.py` | 28 | Canal A completo + edge cases + asyncio |
| `test_applicator_canal_b.py` | 11 | Canal B |
| `test_applicator_controlled.py` | 29 | Pre-producción checklist |
| `test_applicator_v2.py` | 12 | Canal C email body |
| `test_applicator.py` | 17 | Canal detection |
| `test_telegram_hitl.py` | 16 | HITL wait_for_approval |
| `test_cv_rewriter.py` | 37 | CV rewriting reglas |
| `test_narrative_builder.py` | 13 | Bullets validados |
| `test_pdf_generator.py` | 10 | PDF 2 páginas |
| `test_ats_auditor.py` | 8 | ATS score |
| `test_pipeline.py` | 7 | End-to-end dry-run |

---

## APIs y configuración

| Servicio | Archivo | Estado |
|---|---|---|
| Anthropic API | `config/anthropic_key.txt` | ACTIVA |
| Telegram Bot | `config/telegram_token.txt` | Activo — @LilianAgent_lorenaRuiz_bot |
| Apify | `config/apify_key.txt` | Configurada |
| LinkedIn Session | `browser_profile/` | Guardada |
| Windows Task | `JobAppAgent_LorenaRuiz` 08:00 | Registrada |

---

## Próxima mejora planeada: candidate_profile.json

Repositorio de respuestas estructuradas de Lorena para preguntas recurrentes en formularios Easy Apply:

```json
{
  "salary_expectation":  "8000000",
  "currency":            "COP",
  "city":                "Bogotá D.C.",
  "lives_in_bogota":     "Sí",
  "willing_to_relocate": "No",
  "willing_to_travel":   "Sí",
  "years_experience":    "14",
  "work_authorization":  "Sí",
  "english_level":       "C2",
  "availability":        "Inmediata"
}
```

Flujo: `_match_profile_question(question)` por keywords → perfil → si no match → Claude Haiku.
Esto resuelve: campos numéricos (salario), dropdowns sí/no, y preguntas repetidas entre postulaciones.

---

## Comandos de producción

```bash
# Setup inicial (una vez)
python _setup_browser.py      # inicializar sesión LinkedIn
python _schedule_task.py      # registrar tarea Windows 08:00

# Verificación
python _preflight.py          # check APIs y configuración
python -m pytest -q           # 186 tests

# Smoke tests manuales
python _smoke_canal_a.py      # Canal A con URL real Easy Apply
python _smoke_canal_b.py      # Canal B con URL real portal

# Producción
python main.py --once --dry-run --rama C    # dry-run una vez
python main.py --once --rama C              # real una vez
python main.py                              # loop diario 08:00
```

---

## Roles y fechas canónicas de Lorena

| Rol | Empresa | Fecha | Mercado |
|---|---|---|---|
| Paid Media Specialist / AM LinkedIn Ads | Teleperformance (LinkedIn) | Feb 2026 – Present | Latin America ONLY |
| Campaign Planner Contractor | Amazon, Colombia | May 2025 – Feb 2026 | APAC ONLY |
| Digital Channels Consultant | Avanti IT SAS | Aug 2021 – Apr 2025 | Colombia |
| Marketing Manager | Alcalisa S.A. | 2013 – 2018 | Ecuador |
| Commercial Director | GRC S.A. | 2012 – 2013 | Ecuador / China / Russia |

**IMPORTANTE:** Amazon terminó Feb 2026. LinkedIn empezó Feb 2026. Nunca mezclar mercados APAC/LATAM.
