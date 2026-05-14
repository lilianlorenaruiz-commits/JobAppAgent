  ---
  arquitectura_flujo_agentico.md

  # Arquitectura del Flujo Agentico — Job Application Agent

  ## Visión General

  Sistema multi-agente que automatiza la búsqueda, análisis y aplicación a
  cargos laborales en LinkedIn para 3 perfiles profesionales basados en el CV
   de Lorena Ruiz. Corre en loop diario con memoria para evitar aplicaciones
  duplicadas.

  ---

  ## Diagrama de Flujo General

                      ┌──────────────────────┐
                      │   ORQUESTADOR PRAL    │
                      │   (Loop diario cron)  │
                      └──────┬───────────────┘
                             │
                  ┌──────────┴──────────┐
                  │   MEMORIA (SQLite)   │
                  │  - Aplicaciones prev │
                  │  - Cargos ya vistos  │
                  └──────────┬──────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
  │  RAMA A       │ │  RAMA B       │ │  RAMA C       │
  │  CONSULTORÍA  │ │  RETAIL MKTG  │ │  PAID MEDIA   │
  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  SCRAPER LINKEDIN    │
                  │ (Apify Actor)        │
                  │  - Bogotá            │
                  │  - Presencial/Híbrido│
                  │  - Remoto Colombia   │
                  │  - Inglés C1         │
                  │  - Pub: 8-16 días    │
                  └──────────┬───────────┘
                             │
                  ┌──────────┴───────────┐
                  │  ANALIZADOR SKILLS   │
                  │  - Match CV vs cargo │
                  │  - Score 0-100%      │
                  │  - Threshold >= 85%  │
                  └──────────┬───────────┘
                             │
                  ┌──────────┴───────────┐
                  │  AGENTE RECLUTADOR   │
                  │  (Senior Recruiter)  │
                  │  - Rewrite CV para   │
                  │    filtros ATS       │
                  │  - Score 95-100%     │
                  └──────────┬───────────┘
                             │
                  ┌──────────┴───────────┐
                  │  GENERADOR PDF       │
                  │  Lorena Ruiz -       │
                  │  [cargo] - [empresa] │
                  └──────────┬───────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
  │  LINKEDIN     │ │  WEB EMPRESA  │ │  EMAIL        │
  │  Easy Apply   │ │  Formulario   │ │  Borrador     │
  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  REGISTRO BD         │
                  │  - Cargo, empresa    │
                  │  - Status A/B/C      │
                  │  - Fecha, resultado  │
                  └──────────┬───────────┘
                             │
                  ┌──────────┴───────────┐
                  │  REPORTE TELEGRAM    │
                  │  @LorenaRuiz bot     │
                  │  Resumen diario      │
                  └──────────────────────┘

  ---

  ## Los 6 Agentes del Sistema

  ### 1. Agente Orquestador (Orquestador Principal)
  - **Rol:** Coordina todos los agentes, maneja el loop diario, consulta
  memoria
  - **Trigger:** Cron diario o ejecución manual
  - **Input:** Fecha actual, última ejecución
  - **Output:** Reporte de ejecución diaria
  - **Tecnología:** Python script principal con scheduler

  ### 2. Agente Scraper (LinkedIn Jobs)
  - **Rol:** Busca cargos en LinkedIn para cada rama
  - **Input:** Términos de búsqueda por perfil, ubicación, días
  - **Output:** JSON con cargos encontrados
  - **Fuente:** Apify LinkedIn Jobs Scraper
  - **Filtros:** Bogotá, presencial/híbrido/remoto, C1 inglés, 8-16 días
  publicación

  | Rama | Términos de búsqueda |
  |------|---------------------|
  | A Consultoría | "Brand Strategist", "Marketing Consultant", "Digital
  Transformation", "Brand Consultant", "Marketing Strategy" |
  | B Retail | "Marketing Manager Retail", "Trade Marketing", "Category
  Manager", "Shopper Marketing", "Retail Marketing" |
  | C Paid Media | "Paid Media", "Amazon Ads", "Performance Marketing", "PPC
  Specialist", "LinkedIn Ads" |

  ### 3. Agente Analizador de Skills (Skill Matcher)
  - **Rol:** Compara CV de Lorena vs requisitos del cargo, calcula match
  score
  - **Input:** CV parseado, descripción del cargo
  - **Output:** Score de idoneidad (%), skills que matchean, gaps
  - **Threshold:** >= 85% para pasar al reclutador
  - **Skills target por perfil:**
    - Consultoría: Brand Strategy, Digital Transformation, Data Analysis, C1
  English
    - Retail: Trade Marketing, Category Management, Shopper Insights, P&L
    - Paid Media: Google Ads, Meta Ads, Amazon Ads, LinkedIn Ads,
  Programmatic

  ### 4. Agente Reclutador Senior (CV Rewriter)
  - **Rol:** Reescribe el CV optimizado para ATS del cargo específico
  - **Input:** CV original, cargo objetivo, descripción, skills requeridas
  - **Output:** CV optimizado en texto (luego va a PDF)
  - **Score target:** 95-100% de idoneidad contra filtros ATS
  - **Técnicas:**
    - Keyword optimization de la descripción del cargo
    - Reordenamiento de experiencia según relevancia
    - Formato ATS-friendly (sin tablas, sin columnas, sin gráficos)
    - Logros cuantificados adaptados al rol

  ### 5. Agente Aplicador (Application Sender)
  - **Rol:** Toma el PDF generado y lo envía por el canal correspondiente
  - **Input:** PDF, URL de aplicación, tipo de canal
  - **Output:** Confirmación de envío (A, B, o C)
  - **3 canales:**
    - **A - LinkedIn Easy Apply:** Abre LinkedIn, completa aplicación
    - **B - Web Empresa:** Navega al portal de carreras, llena formulario
    - **C - Email:** Genera borrador en cliente de correo

  ### 6. Agente Reportero (Telegram + BD)
  - **Rol:** Registra todas las aplicaciones y envía reporte diario
  - **Input:** Resultados del día de todos los agentes
  - **Output:**
    - BD actualizada (SQLite)
    - Mensaje Telegram a @LorenaRuiz
  - **Estructura del reporte:**
    📋 RESUMEN DIARIO - [Fecha]

    ✅ Aplicaciones exitosas: X
    ❌ Fallidas: Y
    🎯 Pendientes: Z

    ─────────────────────
    🔹 [Cargo] @ [Empresa] → ✅ Enviado (LinkedIn)
    🔹 [Cargo] @ [Empresa] → ❌ No cumplió threshold (72%)
    ...

    📊 Total acumulado: XX aplicaciones

  ---

  ## Base de Datos SQLite

  ### Tabla: `aplicaciones`

  | Columna | Tipo | Descripción |
  |---------|------|-------------|
  | id | INTEGER PK | Auto-incremental |
  | fecha | DATE | Fecha de aplicación |
  | rama | TEXT | A (Consultoría), B (Retail), C (Paid Media) |
  | cargo | TEXT | Nombre del cargo |
  | empresa | TEXT | Nombre de la empresa |
  | url | TEXT | URL de la oferta |
  | modalidad | TEXT | Presencial, Híbrido, Remoto |
  | ubicacion | TEXT | Bogotá u otra |
  | match_score | INTEGER | Score de idoneidad (0-100) |
  | status_aplicacion | TEXT | A (LinkedIn), B (Web), C (Email) |
  | resultado | TEXT | Enviado, Pendiente, Fallido |
  | cv_generado | TEXT | Ruta del PDF generado |
  | fecha_creacion | TIMESTAMP | Auto-generado |

  ### Tabla: `memoria_cargos`

  | Columna | Tipo | Descripción |
  |---------|------|-------------|
  | id_cargo_externo | TEXT | ID único del cargo en LinkedIn |
  | cargo | TEXT | Nombre |
  | empresa | TEXT | Empresa |
  | fecha_visto | DATE | Cuándo se procesó |
  | aplicado | BOOLEAN | Si ya se aplicó |

  ---

  ## Estructura de Carpetas del Proyecto

  C:\Users\lilia\JobAppAgent
  ├── main.py                    # Orquestador principal
  ├── config.py                  # Configuración global
  ├── requirements.txt           # Dependencias
  │
  ├── agents/
  │   ├── init.py
  │   ├── orquestador.py         # Agente 1: Loop y coordinación
  │   ├── scraper.py             # Agente 2: LinkedIn Jobs Scraper
  │   ├── skill_matcher.py       # Agente 3: Match CV vs cargo
  │   ├── cv_rewriter.py         # Agente 4: Reescritura CV para ATS
  │   ├── applicator.py          # Agente 5: Envío de aplicación
  │   └── reporter.py            # Agente 6: BD + Telegram
  │
  ├── profiles/
  │   ├── perfil_a_consultoria.json   # Términos y config Rama A
  │   ├── perfil_b_retail.json        # Términos y config Rama B
  │   └── perfil_c_paidmedia.json     # Términos y config Rama C
  │
  ├── database/
  │   ├── schema.sql              # Esquema SQLite
  │   └── job_app.db              # Base de datos (auto-generada)
  │
  ├── output/
  │   └── cv_optimizados/        # PDFs generados por cargo
  │       └── Lorena Ruiz - [cargo] - [empresa].pdf
  │
  ├── docs/
  │   ├── arquitectura_flujo_agentico.md
  │   └── contexto_sesion.md
  │
  └── config/
      └── telegram_token.txt      # Token del bot

  ---

  ## Stack Tecnológico

  | Componente | Tecnología |
  |------------|-----------|
  | Lenguaje | Python 3.11+ |
  | Scraping LinkedIn | Apify LinkedIn Jobs Scraper (MCP) |
  | Base de datos | SQLite (sqlite3) |
  | Generación PDF | ReportLab o FPDF2 |
  | Telegram Bot | python-telegram-bot v20+ |
  | CV Parsing | PyMuPDF (pdfplumber) |
  | IA / NLP | Claude API (Anthropic) para rewriting |
  | Scheduler | schedule (Python lib) |
  | Automatización navegador | Playwright (para web empresa) |
  | Control de versión | Git |

  ---

  ## Flujo de Decisión por Cargo

  Cargo encontrado por scraper
          │
          ▼
  ¿Ya está en memoria? ──SÍ──→ DESCARTAR (ya aplicado)
          │
          NO
          ▼
  Skill Matcher: ¿Score >= 85%? ──NO──→ DESCARTAR (bajo match)
          │
          SÍ
          ▼
  Agente Reclutador: Rewrite CV
          │
          ▼
  ¿Score ATS >= 95%? ──NO──→ Re-rewrite (máx 3 intentos)
          │
          SÍ
          ▼
  Generar PDF → Guardar en /output/cv_optimizados/
          │
          ▼
  Aplicar:
     ├── A: LinkedIn Easy Apply
     ├── B: Web empresa (Playwright)
     └── C: Email borrador
          │
          ▼
  Registrar en BD + memoria
          │
          ▼
  Reporte Telegram al final del día

  ---

  ## Telegram Integration

  - **Bot Token:** `8615990917:AAEfCOQVc_rER0EKOkMKcTCT_-ZSLspvZgA`
  - **Chat:** @LorenaRuiz
  - **Comandos del bot:**
    - `/start` — Inicia el bot
    - `/status` — Resumen de hoy
    - `/aplicaciones` — Lista de aplicaciones recientes
    - `/run` — Ejecutar loop manualmente

  ---

  ## Pendientes para Implementación

  - [ ] Crear estructura de carpetas
  - [ ] Implementar schema SQLite
  - [ ] Configurar Apify LinkedIn Jobs Scraper
  - [ ] Implementar parser de CV
  - [ ] Implementar Skill Matcher
  - [ ] Implementar CV Rewriter (con Claude API)
  - [ ] Implementar generador PDF
  - [ ] Implementar aplicador (LinkedIn + Web + Email)
  - [ ] Implementar reportero Telegram
  - [ ] Implementar orquestador + loop diario
  - [ ] Testing integral
  - [ ] Despliegue (cron)