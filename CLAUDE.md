# JobAppAgent — Contexto para Claude

## Qué es este proyecto
Sistema multi-agente en Python que automatiza búsqueda y aplicación a empleos para **Lorena Ruiz** en 3 perfiles simultáneos.

## Rutas críticas
- **Proyecto:** `C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent\`
- **CV fuente:** `C:\Users\lilia\CV\Lorena_Ruiz_CV.pdf`
- **Arquitectura:** `docs\arquitectura_flujo_agentico.md` — leer antes de codificar
- **Contexto sesión:** `docs\contexto_sesion.md`

## Los 3 perfiles
| Rama | Cargos target | Threshold |
|------|--------------|-----------|
| A — Consultoría | Brand Strategist, Digital Transformation, Marketing Consultant | 85% match |
| B — Retail Marketing | Trade Marketing, Category Manager, Shopper Marketing | 85% match |
| C — Paid Media | Paid Media Specialist, Amazon Ads, PPC Specialist | 85% match |

## Stack técnico (decisiones cerradas)
- Python 3.11+ / SQLite / Playwright / ReportLab / python-telegram-bot v20+
- Scraping: Apify LinkedIn Jobs Scraper (vía MCP)
- CV rewriting: Claude API (Anthropic)
- Scheduler: `schedule` (Python puro — sin LangGraph, sin frameworks de agentes)

## 6 Agentes
1. Orquestador — loop diario
2. Scraper — LinkedIn Jobs vía Apify
3. Skill Matcher — CV vs cargo, threshold 85%
4. CV Rewriter — ATS optimization, threshold 95%
5. Applicator — LinkedIn Easy Apply / Web empresa / Email
6. Reporter — SQLite + Telegram diario

## Estado actual
- Estructura de carpetas: ✅ creada
- Schema SQLite: ⬜ pendiente (Fase 1)
- Parser CV: ⬜ pendiente (Fase 1)
- Perfiles JSON: ⬜ pendiente (Fase 1)
- Agentes: ⬜ pendiente (Fase 2+)

## Telegram
- Bot: @JobAppAgent_lorenaRuiz_bot
- Token: en `config\telegram_token.txt`

## Skills a invocar
- Fase 1 (actual): ninguna — implementación directa
- Al llegar al Orquestador: `/auto-project-orchestrator` y `/tdd`
- NO usar: `langgraph-agents-skill`, `subagent-teams-skill` (no aplican)

## Reglas de trabajo
- NUNCA modificar archivos en `docs\` sin confirmar
- NUNCA instalar dependencias sin mostrarlas primero
- SIEMPRE confirmar ✅ después de cada entregable completado
- Scope: solo dentro de esta carpeta
