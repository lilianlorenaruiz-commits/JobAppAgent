# Evidence-Based CV Rewriter — Design Spec

**Fecha:** 2026-05-15  
**Proyecto:** JobAppAgent — Lorena Ruiz  
**Estado:** APROBADO — listo para plan de implementación  
**Objetivo:** Reescribir CVs que maximicen match real sin alucinar — cada claim trazable a `narrativas_lorena.json`

---

## Problema actual

El `cv_rewriter.py` tiene dos reglas que causan alucinación sistemática:

- **Regla 7:** "Inject keywords from the JD naturally into bullet points" → Claude copia keywords del JD sin verificar si Lorena tiene evidencia real
- **Regla 10:** "Mirror the exact job-title language" → el headline refleja el título del JD, no el perfil real de Lorena
- **Retry loop:** "Increase keyword density to reach 95%+" → presión hacia invención bajo repetición

El resultado: CVs con keywords correctos pero claims no defendibles en entrevista. El objetivo (conseguir trabajo) requiere callbacks reales, no solo ATS alto.

---

## Principio de diseño

El rewriter no es un keyword injector — es un **evidence mapper**. Su trabajo es:

1. Encontrar dónde Lorena hizo cada skill requerido por el JD — aunque sea en otro contexto, cargo o mercado
2. Construir la narrativa que conecta esa evidencia real con el requisito del JD
3. Si no existe evidencia, aplicar tier conservador o omitir

Cada claim del CV debe ser trazable a un bullet de `narrativas_lorena.json`.

---

## Arquitectura — 4 componentes

```
JD + narrativas_lorena.json
        ↓
[1] evidence_mapper.py        ← NUEVO
    → evidence_map dict (Tier 1 / 2 / 3)
        ↓
[2] cv_rewriter.py            ← MODIFICADO (quirúrgico)
    → Claude redacta SOLO con el mapa
        ↓
[3] ats_auditor.py            ← REDISEÑADO
    → Evidence check + ATS score
        ↓
[4] Retry loop                ← NUEVO DENTRO DE cv_rewriter.py
    → 3 caminos: poor fit / evidence faltante / redacción débil
```

---

## Componente 1 — `agents/evidence_mapper.py` (NUEVO)

### Función pública

```python
def build_evidence_map(job_description: str, narrativas: dict) -> dict:
    """
    Dado un JD y narrativas_lorena.json, retorna un evidence_map completo:
    {skill_name: {"tier": int, "evidencia": [{"rol": str, "bullet": str}]}}
    
    Tier 1 y 2: evidencia presente. Tier 3: evidencia = [] (skill sin match).
    El cv_rewriter filtra Tier 3 al construir el prompt — no los envía a Claude.
    El retry loop los cuenta para detectar poor fit.
    """
```

### Flujo interno

1. **Extracción de skills del JD** — Claude Haiku:
   ```
   "Lista los skills, competencias y requisitos clave de este JD. 
   Output: lista de strings, uno por línea, sin numeración."
   ```

2. **Búsqueda en narrativas** — para cada skill, tres pasos en cascada:
   - Paso 1: keyword match exacto (case-insensitive, strip accents)
   - Paso 2: keyword fuzzy match (variantes, plural/singular, ES/EN)
   - Paso 3: Claude Haiku semántico: "¿Este bullet cubre este skill? Responde SOLO sí/no + razón en una línea"

3. **Clasificación con rubrica determinista** — para cada bullet encontrado:

   | Criterio | Descripción |
   |---|---|
   | C1 — Sujeto activo | Lorena es quien ejecuta (verbo propio, no "apoyé", "participé en", "colaboré") |
   | C2 — Contexto específico | Empresa, mercado, o resultado concreto presente en el bullet |
   | C3 — Actividad transferible | La actividad es reconociblemente la misma que pide el JD, aunque el nombre o sector difiera |

   - **Tier 1:** cumple C1 + C2 + C3
   - **Tier 2:** cumple C2 + C3 pero NO C1 (exposición, consultoría, soporte)
   - **Tier 3:** no cumple C3 → skill ausente del evidence_map

4. **Output estructurado:**

```python
{
  "gestión de categorías": {
    "tier": 1,
    "evidencia": [
      {"rol": "Alcalisa", "bullet": "P&L categoría spirits, pricing y mix de portafolio"},
      {"rol": "Amazon", "bullet": "cada cliente = vertical independiente con análisis competitivo"}
    ]
  },
  "planificación de surtido": {
    "tier": 2,
    "evidencia": [
      {"rol": "Avanti IT", "bullet": "análisis de portafolio con retailers en sector gobierno"}
    ]
  },
  "gestión de inventario WMS": {
    "tier": 3,
    "evidencia": []   # sin match → cv_rewriter no lo envía a Claude, retry lo cuenta
  }
}
```

### Constante de configuración

```python
POOR_FIT_THRESHOLD = 5  # si el JD tiene más de N skills sin evidencia (Tier 3), flag poor_fit
```

---

## Componente 2 — `cv_rewriter.py` (MODIFICADO)

### Cambios en el flujo principal

```python
def rewrite(cv, job, rama):
    narrativas = _load_narrativas()
    evidence_map = build_evidence_map(job["descripcion"], narrativas)  # NUEVO
    cv_text = _enrich_with_narratives(cv, narrativas, rama)
    result = _call_claude(cv_text, job, rama, evidence_map)            # evidence_map agregado
    return _retry_with_evidence_logic(result, evidence_map)            # retry nuevo
```

### Cambios en `_SYSTEM` prompt

**Eliminar:**
- Regla 7: "Inject keywords from the job description naturally into bullet points and the profile section"
- Regla 10: "Mirror the exact job-title language from the job description in the profile headline"
- Nota de retry: "Increase keyword density and tighten alignment to reach 95%+"

**Reemplazar Regla 7 con:**
> "Redacta cada skill o requisito del JD usando exactamente los hechos listados en su fila del EVIDENCE MAP — ningún dato adicional. No busques evidencia fuera del mapa."

**Reemplazar Regla 10 con:**
> "El headline describe el perfil real de Lorena adaptado al área del cargo — no copia el título exacto del JD. Ejemplo: si el JD es 'Product Manager Vestuario', el headline puede ser 'Marketing & Category Manager | E-commerce | Retail'."

**Nueva regla — tiers de evidencia:**
> "Para cada skill en el EVIDENCE MAP: Tier 1 = narrativa de transferencia completa con verbo activo, contexto y resultado. Tier 2 = lenguaje de exposición ('en contexto de', 'a través de', 'con exposición a'). Skill ausente del mapa = ausente del CV sin excepción."

**Tarea en implementación:** Auditar las 25 reglas restantes del `_SYSTEM` actual y eliminar cualquier instrucción que empuje hacia elaboración fuera de evidencia.

### El prompt incluye el mapa explícitamente

```
EVIDENCE MAP (fuente de verdad — redactar SOLO con esto):
gestión de categorías [Tier 1]: Alcalisa → P&L spirits | Amazon → vertical independiente
liderazgo de equipos [Tier 1]: Alcalisa → 12 reportes directos marketing/trade/comercial
planificación de surtido [Tier 2]: Avanti IT → análisis portafolio con retailers
gestión inventario WMS → AUSENTE (no incluir en CV)
```

---

## Componente 3 — `ats_auditor.py` (REDISEÑADO)

### Dos checks secuenciales

**Check 1 — Evidence verification (NUEVO):**
Para cada claim sustantivo del CV, verificar que existe una fila correspondiente en `evidence_map`.

```python
def verify_evidence(cv_text: str, evidence_map: dict) -> list[str]:
    """
    Retorna lista de claims en el CV sin correspondencia en evidence_map.
    Claims sin evidencia = candidatos a eliminar o degradar.
    """
```

**Check 2 — ATS score (EXISTENTE, sin cambios):**
% de keywords del JD presentes en el CV. Se mantiene como métrica secundaria.

### Output del auditor

```python
{
  "ats_score": 94,
  "passed_ats": False,
  "claims_sin_evidencia": ["gestión de inventario WMS avanzado"],  # nuevo campo
  "tier3_skills_count": 3  # nuevo campo — input para retry logic
}
```

---

## Componente 4 — Retry loop (NUEVO en `cv_rewriter.py`)

```python
POOR_FIT_THRESHOLD = 5  # desde evidence_mapper

def _retry_with_evidence_logic(result, evidence_map):
    tier3_count = result.get("tier3_skills_count", 0)

    # Camino 1: demasiados gaps reales → job fit insuficiente
    if tier3_count > POOR_FIT_THRESHOLD:
        result["poor_fit"] = True
        result["poor_fit_reason"] = f"{tier3_count} skills sin evidencia en narrativas"
        return result  # no retry — HITL decide si Lorena quiere aplicar igual

    # Camino 2: hay Tier 1 que no apareció en el CV → solo puede subir
    if result.get("claims_sin_evidencia"):
        return _retry_with_instruction(
            "Faltan estas evidencias Tier 1 en el CV — inclúyelas: "
            + str(result["claims_sin_evidencia"])
        )

    # Camino 3: evidencia completa pero redacción débil
    if result["ats_score"] < ATS_THRESHOLD:
        return _retry_with_instruction(
            "Reformula los Tier 1 con más keywords del JD "
            "sin agregar datos fuera del EVIDENCE MAP"
        )

    return result
```

### Invariante del retry loop

El loop nunca puede bajar el ATS score al reintentar:
- Camino 1: no retry
- Camino 2: agrega evidencia faltante (ATS solo sube)
- Camino 3: reformula evidencia existente con más keywords (ATS estable o sube)

---

## Lo que NO cambia

| Componente | Estado |
|---|---|
| `_fix_static_fields()` — educación hardcoded | Sin cambios |
| Flujo HITL Telegram | Sin cambios |
| PDF generator | Sin cambios |
| `skill_matcher.py` | Sin cambios (plan 2 separado) |
| 267 tests existentes | Se mantienen — se agregan tests nuevos |
| `narrativas_lorena.json` | Fuente de verdad — sin cambios estructurales |

---

## Tests nuevos requeridos

| Archivo | Qué cubre |
|---|---|
| `tests/test_evidence_mapper.py` | build_evidence_map: extracción skills, rubrica tiers, output dict |
| `tests/test_cv_rewriter_evidence.py` | rewrite() con evidence_map: Tier 1 aparece, Tier 3 ausente, retry logic |
| `tests/test_ats_auditor_v2.py` | verify_evidence(): claims sin evidencia detectados correctamente |

---

## Impacto sobre el objetivo

| Escenario | Antes | Después |
|---|---|---|
| JD con match real (pocos Tier 3) | Alucina keywords → ATS alto → entrevista expone → no job | Tier 1 honesto → ATS 95%+ → entrevista defendible → callback real |
| JD con match parcial (varios Tier 3) | Inventa skills → CV no representa a Lorena | ATS honesto + flag poor_fit → Lorena decide en HITL con información real |
| JD sin match (muchos Tier 3) | Fabrica CV falso | Flag poor_fit → no aplica → matcher (plan 2) lo filtra desde el inicio |

---

## Plan 2 — Skill Matcher (separado, siguiente sesión)

El flag `poor_fit` que produce el rewriter es el input que el matcher necesita para calibrar su threshold. Si consistentemente los cargos con X características producen poor_fit, el matcher debe filtrarlos antes de llegar al rewriter.

Scope del plan 2: fuera de este spec — sesión separada.
