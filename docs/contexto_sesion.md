# Contexto de Sesión — Job Application Agent

**Última actualización:** 2026-05-14
**Proyecto:** Sistema multi-agente para búsqueda y aplicación automatizada de empleo para Lorena Ruiz

---

## Estado actual del proyecto

**TODOS LOS CANALES APROBADOS EN SMOKE TEST REAL — 226/226 tests GREEN**

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

## Test Suite — 226 tests

```bash
python -m pytest -q    # → 226 passed
```

| Archivo | Tests | Cubre |
|---|---|---|
| `test_applicator_canal_a.py` | 53 | Canal A + smart fill + candidate_profile + _extract_linkedin_job_info |
| `test_applicator_canal_b.py` | 11 | Canal B |
| `test_applicator_controlled.py` | 29 | Pre-producción checklist |
| `test_applicator_v2.py` | 12 | Canal C email body |
| `test_applicator.py` | 17 | Canal detection |
| `test_telegram_hitl.py` | 16 | HITL wait_for_approval |
| `test_cv_rewriter.py` | 37 | CV rewriting reglas |
| `test_cv_rewriter_unit.py` | 15 | CV rewriting unidad (ciclo 28) |
| `test_narrative_builder.py` | 13 | Bullets validados |
| `test_pdf_generator.py` | 10 | PDF 2 páginas |
| `test_ats_auditor.py` | 8 | ATS score |
| `test_pipeline.py` | 7 | End-to-end dry-run |
| `test_config_hitl.py` | 2 | HITL timeout config |

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

## Bugs post-smoke-test 2026-05-14 — CORREGIDOS

| Bug | Severidad | Fix | Commit |
|---|---|---|---|
| BUG-001: Salary field recibía texto, LinkedIn esperaba decimal | CRÍTICO | `_PROFILE_KEYWORD_RULES` → `salary_cop_monthly` ("6500000") | `784d982` |
| BUG-003: HITL timeout 5 min insuficiente (~3 min formulario + 2 min revisión) | MEDIO | `HITL_TIMEOUT_S`: 300 → 600 | `51e58c0` |
| BUG-004: No extraía cargo/empresa/JD de la URL antes de aplicar | MEDIO | `_extract_linkedin_job_info(page)` nueva función con 7 tests | `29fdec3` |
| BUG-002: Smoke test usaba PDF estático (Rappi) sin adaptar al cargo | CRÍTICO | `_smoke_canal_a.py` pipeline completo: scrape → rewrite → generate → apply | `d5a0da9` |

---

## candidate_profile.json — IMPLEMENTADO (Ciclo 27)

Repositorio de respuestas estables de Lorena en `config/candidate_profile.json`:

```json
{
  "salary_text":               "6.500.000 COP / 2.300 USD mensuales",  // SOLO para referencia — NO usar en formularios
  "salary_cop_monthly":        "6500000",  // campo numérico LinkedIn — BUG-001
  "city":                      "Bogotá D.C., Colombia",
  "willing_to_travel":         "Sí",
  "willing_to_relocate":       "No",
  "availability":              "Inmediata",
  "has_vehicle":               "Sí",
  "background_check":          "Sí",
  "english_level":             "C2 - Proficiencia completa",
  "requires_visa_sponsorship": "No",
  "work_authorization":        "Sí",
  "night_shifts":              "No, disponible lunes a viernes en horario regular",
  "hybrid_available":          "Sí",
  "years_experience":          "14"
}
```

Flujo implementado: `_match_profile_question(question, profile)` por keywords → si match → retorna respuesta del perfil (sin llamar a Claude). Si no match → Claude como fallback.

Funciones añadidas a `agents/applicator.py`:
- `_load_candidate_profile() -> dict` — carga el JSON desde config/
- `_PROFILE_KEYWORD_RULES` — 14 reglas keyword → clave de perfil
- `_match_profile_question(question, profile) -> str` — match case-insensitive

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
