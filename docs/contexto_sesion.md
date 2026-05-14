 contexto_sesion.md

  # Contexto de Sesión — Job Application Agent

  **Fecha:** 2026-05-13
  **Proyecto:** Sistema multi-agente para búsqueda y aplicación automatizada
  de empleo

  ---

  ## Resumen de lo que estábamos construyendo

  Un flujo agentico automatizado que:
  1. Lee el CV de Lorena Ruiz (ubicado en
  `C:\Users\lilia\CV\Lorena_Ruiz_CV.pdf`)
  2. Identifica 3 perfiles profesionales
  3. Hace scraping de LinkedIn Jobs para cada perfil
  4. Analiza match de skills entre CV y cargos
  5. Reescribe CV optimizado para ATS por cada cargo
  6. Aplica automáticamente (LinkedIn / web empresa / email)
  7. Registra todo en BD y reporta por Telegram

  ---

  ## Decisiones tomadas

  | Decisión | Opción elegida |
  |----------|---------------|
  | **Fuente principal de scraping** | LinkedIn (vía Apify LinkedIn Jobs
  Scraper) |
  | **Ubicación geográfica** | Bogotá, Colombia + remoto Colombia |
  | **Modalidades** | Presencial, Híbrido, Remoto |
  | **Nivel de inglés** | C1 como requisito |
  | **Rango de publicación** | 8 a 16 días |
  | **Score mínimo para aplicar** | 85% match (Skill Matcher) |
  | **Score para CV final** | 95-100% (Agente Reclutador) |
  | **Base de datos** | SQLite local |
  | **Reporte diario** | Telegram (@LorenaRuiz bot) |
  | **Token Telegram** | `8615990917:AAEfCOQVc_rER0EKOkMKcTCT_-ZSLspvZgA` |
  | **Lenguaje** | Python 3.11+ |
  | **Automatización navegador** | Playwright |
  | **IA para rewriting** | Claude API (Anthropic) |
  | **Generación PDF** | ReportLab o FPDF2 |

  ---

  ## Los 3 Perfiles Investigados

  ### Perfil A — Consultoría / Transformación Digital
  - **Cargos target:** Brand Strategist, Marketing Consultant, Digital
  Transformation, Brand Consultant
  - **Skills clave:** Brand Strategy, Digital Transformation, Market
  Research, Data Analysis, C1 English
  - **Match alto:** Essity Brand Strategist (95%), Publicis Digital
  Consultant (91%)

  ### Perfil B — Marketing Retail
  - **Cargos target:** Marketing Manager Retail, Trade Marketing, Category
  Manager, Shopper Marketing
  - **Skills clave:** Trade Marketing, Category Management, Shopper Insights,
   P&L Management
  - **Match alto:** Éxito Marketing Manager (82%), Falabella Retail
  Specialist (85%)

  ### Perfil C — Paid Media Ads
  - **Cargos target:** Paid Media Specialist, Amazon Ads Manager, Performance
   Marketing, PPC Specialist
  - **Skills clave:** Google Ads, Meta Ads, Amazon Ads, LinkedIn Ads,
  Programmatic
  - **Match alto:** Havas Paid Media (90%), GroupM Amazon Ads (92%)

  ---

  ## Arquitectura: 6 Agentes

  1. **Orquestador** — Loop diario, coordinación
  2. **Scraper** — LinkedIn Jobs vía Apify
  3. **Skill Matcher** — CV vs cargo (threshold 85%)
  4. **CV Rewriter** — ATS optimization (threshold 95%)
  5. **Applicator** — LinkedIn / Web / Email
  6. **Reporter** — SQLite + Telegram

  ### 3 Ramas de Búsqueda
  - Rama A: Consultoría
  - Rama B: Retail Marketing
  - Rama C: Paid Media

  ---

  ## Archivos Creados

  | Archivo | Ruta |
  |---------|------|
  | Arquitectura completa |
  `C:\Users\lilia\JobAppAgent\docs\arquitectura_flujo_agentico.md` |
  | Contexto de sesión | `C:\Users\lilia\JobAppAgent\docs\contexto_sesion.md`
   |

  ---

  ## Archivos Planeados para Crear (Pendientes)

  - [ ] `C:\Users\lilia\JobAppAgent\main.py`
  - [ ] `C:\Users\lilia\JobAppAgent\config.py`
  - [ ] `C:\Users\lilia\JobAppAgent\requirements.txt`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\__init__.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\orquestador.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\scraper.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\skill_matcher.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\cv_rewriter.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\applicator.py`
  - [ ] `C:\Users\lilia\JobAppAgent\agents\reporter.py`
  - [ ] `C:\Users\lilia\JobAppAgent\profiles\perfil_a_consultoria.json`
  - [ ] `C:\Users\lilia\JobAppAgent\profiles\perfil_b_retail.json`
  - [ ] `C:\Users\lilia\JobAppAgent\profiles\perfil_c_paidmedia.json`
  - [ ] `C:\Users\lilia\JobAppAgent\database\schema.sql`
  - [ ] `C:\Users\lilia\JobAppAgent\config\telegram_token.txt`

  ---

  ## Lo que alcanzamos a hacer en esta sesión

  - [x] Leer y parsear el CV de Lorena Ruiz
  - [x] Identificar los 3 perfiles profesionales
  - [x] Investigar cargos reales en LinkedIn para cada perfil
  - [x] Analizar patrones de skills por perfil
  - [x] Calcular match scores contra el CV
  - [x] Obtener el token de Telegram
  - [x] Diseñar la arquitectura completa del flujo agentico (6 agentes)
  - [x] Definir el esquema de base de datos SQLite
  - [x] Definir la estructura de carpetas del proyecto
  - [x] Documentar todo en `arquitectura_flujo_agentico.md`
  - [x] Escribir este contexto de sesión

  ## Pendiente principal para la siguiente sesión

  **Implementar la Fase 1:** Crear estructura del proyecto, schema SQLite,
  parser de CV, y empezar con el scraper de LinkedIn conectado a Apify.

  ---

  ## Notas importantes

  - El CV está en `C:\Users\lilia\CV\Lorena_Ruiz_CV.pdf`
  - El proyecto arranca desde la creacion de la carpeta`C:\Users\lilia\JobAppAgent\`
  - El stop hook de esta sesión se activó por el comando `/goal` — no es
  necesario para sesiones nuevas
  - El bot de Telegram ya está creado: @JobAppAgent_lorenaRuiz_bot