# Skill Matcher: Aliases + Reweight 20/80 + Threshold 75% — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar rechazos falsos en el skill matcher causados por mismatch tipográfico, reduciendo el peso del keyword score (40→20) y bajando el threshold al valor calibrado para el mercado colombiano real (82→75 para Ramas A y B).

**Architecture:** Tres cambios coordinados — aliases en los JSONs de perfiles, soporte de aliases en `_keyword_score`, y rebalanceo de la fórmula final a 20/80 (keyword/semantic). TDD estricto: cada cambio de producción está precedido por su test en rojo.

**Tech Stack:** Python 3.11, pytest, JSON — sin nuevas dependencias.

---

## File Map

| Archivo | Cambio |
|---------|--------|
| `tests/test_cv_rewriter.py` | Renombrar 2 tests de threshold 82→75 |
| `profiles/perfil_a_consultoria.json` | aliases en skills_target + threshold 82→75 |
| `profiles/perfil_b_retail.json` | aliases en skills_target + threshold 82→75 |
| `profiles/perfil_c_paidmedia.json` | aliases en skills_target (threshold sin cambio) |
| `tests/test_skill_matcher_narrativas.py` | Agregar clase `TestSkillMatcherAliases` (6 tests) |
| `agents/skill_matcher.py` | `_keyword_score` con aliases + fórmula 20/80 |

---

## Task 1: Threshold 82→75 — RED tests primero, luego JSONs

**Files:**
- Modify: `tests/test_cv_rewriter.py:467-502`
- Modify: `profiles/perfil_a_consultoria.json`
- Modify: `profiles/perfil_b_retail.json`

- [ ] **Step 1: Renombrar los 2 tests en rojo (cambiar assert de 82 a 75)**

En `tests/test_cv_rewriter.py`, reemplazar los tests `test_rama_a_threshold_is_82` y `test_rama_b_threshold_is_82`:

```python
    def test_rama_a_threshold_is_75(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_a_consultoria.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_match"] == 75, (
            f"Rama A threshold esperado 75, encontrado {perfil['threshold_match']}"
        )

    def test_rama_b_threshold_is_75(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "perfil_b_retail.json"
        )
        with open(path, encoding="utf-8") as f:
            perfil = json.load(f)
        assert perfil["threshold_match"] == 75, (
            f"Rama B threshold esperado 75, encontrado {perfil['threshold_match']}"
        )
```

- [ ] **Step 2: Verificar que los 2 tests fallan (y el de Rama C sigue verde)**

```
cd C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent
pytest tests/test_cv_rewriter.py::TestThresholdProfiles -v
```

Esperado: `FAILED test_rama_a_threshold_is_75`, `FAILED test_rama_b_threshold_is_75`, `PASSED test_rama_c_threshold_unchanged_75`

- [ ] **Step 3: Actualizar `perfil_a_consultoria.json` — aliases + threshold 75**

Reemplazar contenido completo:

```json
{
  "rama": "A",
  "nombre": "Consultoría de Marca y Marketing",
  "terminos_busqueda": [
    "Brand Strategist",
    "Marketing Consultant",
    "Digital Transformation",
    "Brand Consultant",
    "Marketing Strategy"
  ],
  "ubicacion": ["Bogotá", "Colombia"],
  "modalidades": ["Presencial", "Híbrido", "Remoto"],
  "dias_publicacion_max": 16,
  "idioma_requerido": "Inglés C1",
  "skills_target": [
    "Brand Strategy",
    {
      "skill": "Digital Transformation",
      "aliases": ["transformación digital", "digital transformation"]
    },
    "Data Analysis",
    {
      "skill": "C1 English",
      "aliases": ["c1/c2", "inglés c1", "english c1", "advanced english",
                  "nivel c1", "fluent english", "bilingual"]
    }
  ],
  "threshold_match": 75,
  "threshold_ats": 92
}
```

- [ ] **Step 4: Actualizar `perfil_b_retail.json` — aliases + threshold 75**

Reemplazar contenido completo:

```json
{
  "rama": "B",
  "nombre": "Retail y Trade Marketing",
  "terminos_busqueda": [
    "Marketing Manager Retail",
    "Trade Marketing",
    "Category Manager",
    "Shopper Marketing",
    "Retail Marketing"
  ],
  "ubicacion": ["Bogotá", "Colombia"],
  "modalidades": ["Presencial", "Híbrido", "Remoto"],
  "dias_publicacion_max": 16,
  "idioma_requerido": "Inglés C1",
  "skills_target": [
    {
      "skill": "Trade Marketing",
      "aliases": ["trade mktg", "trade & marketing"]
    },
    {
      "skill": "Category Management",
      "aliases": ["category manager", "gestión de categorías", "category mgmt"]
    },
    {
      "skill": "Shopper Insights",
      "aliases": ["shopper marketing", "shopper analytics", "consumer insights"]
    },
    {
      "skill": "P&L",
      "aliases": ["p&l management", "profit and loss", "pérdidas y ganancias"]
    }
  ],
  "threshold_match": 75,
  "threshold_ats": 92
}
```

- [ ] **Step 5: Verificar que los 2 tests ahora pasan**

```
pytest tests/test_cv_rewriter.py::TestThresholdProfiles -v
```

Esperado: los 3 tests en verde (`PASSED test_rama_a_threshold_is_75`, `PASSED test_rama_b_threshold_is_75`, `PASSED test_rama_c_threshold_unchanged_75`)

- [ ] **Step 6: Verificar que el resto del suite no se rompió**

```
pytest tests/test_cv_rewriter.py -v --tb=short 2>&1 | tail -20
```

Esperado: todos los tests existentes pasan (el cambio de JSON es backward compat para el resto de tests).

- [ ] **Step 7: Commit**

```
git add profiles/perfil_a_consultoria.json profiles/perfil_b_retail.json tests/test_cv_rewriter.py
git commit -m "feat: threshold 82->75 Ramas A y B, calibrado mercado colombiano real"
```

---

## Task 2: Aliases en `perfil_c_paidmedia.json`

**Files:**
- Modify: `profiles/perfil_c_paidmedia.json`

*(Rama C no cambia threshold — ya estaba en 75. Solo agregamos aliases.)*

- [ ] **Step 1: Actualizar `perfil_c_paidmedia.json` — aliases (threshold sin cambio)**

Reemplazar contenido completo:

```json
{
  "rama": "C",
  "nombre": "Paid Media y Performance",
  "terminos_busqueda": [
    "Paid Media",
    "Amazon Ads",
    "Performance Marketing",
    "PPC Specialist",
    "LinkedIn Ads"
  ],
  "ubicacion": ["Bogotá", "Colombia"],
  "modalidades": ["Presencial", "Híbrido", "Remoto"],
  "dias_publicacion_max": 16,
  "idioma_requerido": "Inglés C1",
  "skills_target": [
    {
      "skill": "Google Ads",
      "aliases": ["google adwords", "sem", "search ads", "google advertising"]
    },
    {
      "skill": "Meta Ads",
      "aliases": ["facebook ads", "instagram ads", "meta advertising", "facebook advertising"]
    },
    {
      "skill": "Amazon Ads",
      "aliases": ["amazon advertising", "amazon dsp", "amazon ppc", "sponsored products"]
    },
    {
      "skill": "LinkedIn Ads",
      "aliases": ["linkedin advertising", "linkedin campaigns"]
    },
    "Programmatic"
  ],
  "threshold_match": 75,
  "threshold_ats": 95
}
```

- [ ] **Step 2: Verificar test de Rama C sigue en verde**

```
pytest tests/test_cv_rewriter.py::TestThresholdProfiles::test_rama_c_threshold_unchanged_75 -v
```

Esperado: `PASSED`

- [ ] **Step 3: Commit**

```
git add profiles/perfil_c_paidmedia.json
git commit -m "feat: aliases en perfil_c_paidmedia — backward compat, threshold sin cambio"
```

---

## Task 3: Alias support en `_keyword_score` — RED tests primero

**Files:**
- Modify: `tests/test_skill_matcher_narrativas.py` (agregar clase al final)
- Modify: `agents/skill_matcher.py:95-109`

- [ ] **Step 1: Agregar clase `TestSkillMatcherAliases` al final de `tests/test_skill_matcher_narrativas.py`**

Agregar inmediatamente después del último test del archivo (línea 267), sin modificar nada existente:

```python


# ── Tests: aliases en _keyword_score ──────────────────────────────────────────

class TestSkillMatcherAliases:
    """
    Verifica que _keyword_score acepta skills_target mixto:
    strings simples (backward compat) y dicts {"skill", "aliases"}.
    """

    def test_alias_matches_c1_c2_variant(self):
        """'C1/C2' en JD debe matchear skill 'C1 English' via alias."""
        from agents.skill_matcher import _keyword_score
        skills = [{"skill": "C1 English", "aliases": ["c1/c2", "inglés c1"]}]
        _, matched, _ = _keyword_score("", "Requiere inglés C1/C2", skills)
        assert "C1 English" in matched

    def test_alias_matches_spanish_digital_transformation(self):
        """'transformación digital' en JD debe matchear 'Digital Transformation' via alias."""
        from agents.skill_matcher import _keyword_score
        skills = [{"skill": "Digital Transformation",
                   "aliases": ["transformación digital"]}]
        _, matched, _ = _keyword_score("", "liderará transformación digital", skills)
        assert "Digital Transformation" in matched

    def test_plain_string_backward_compatible(self):
        """Strings simples siguen funcionando igual que antes."""
        from agents.skill_matcher import _keyword_score
        skills = ["Brand Strategy"]
        _, matched, _ = _keyword_score("brand strategy en CV", "", skills)
        assert "Brand Strategy" in matched

    def test_skill_goes_to_gap_when_no_alias_matches(self):
        """Si ni el skill ni sus aliases aparecen, va a gaps."""
        from agents.skill_matcher import _keyword_score
        skills = [{"skill": "C1 English", "aliases": ["c1/c2"]}]
        _, _, gaps = _keyword_score("", "requiere experiencia en marketing", skills)
        assert "C1 English" in gaps

    def test_skill_name_is_canonical_in_matched(self):
        """El nombre en 'matched' es el campo 'skill', no el alias."""
        from agents.skill_matcher import _keyword_score
        skills = [{"skill": "Meta Ads", "aliases": ["facebook ads"]}]
        _, matched, _ = _keyword_score("", "experiencia en Facebook Ads requerida", skills)
        assert "Meta Ads" in matched
        assert "facebook ads" not in matched

    def test_mixed_list_plain_and_dict(self):
        """Lista mixta: string + dict coexisten sin error."""
        from agents.skill_matcher import _keyword_score
        skills = [
            "Brand Strategy",
            {"skill": "C1 English", "aliases": ["c1/c2"]},
            "Data Analysis",
        ]
        score, matched, gaps = _keyword_score(
            "brand strategy analysis", "requiere c1/c2", skills
        )
        assert "Brand Strategy" in matched
        assert "C1 English" in matched
        assert "Data Analysis" in gaps
        assert score == pytest.approx(66.67, abs=0.5)
```

- [ ] **Step 2: Verificar que los 6 tests fallan (función actual no soporta dicts)**

```
pytest tests/test_skill_matcher_narrativas.py::TestSkillMatcherAliases -v
```

Esperado: los 6 tests `FAILED` con `TypeError` o `AttributeError` (skill.lower() falla en dict).

- [ ] **Step 3: Implementar soporte de aliases en `_keyword_score`**

En `agents/skill_matcher.py`, reemplazar la función `_keyword_score` completa (líneas 95-109):

```python
def _keyword_score(
    cv_text: str,
    job_desc: str,
    skills_target: list,
) -> tuple[float, list[str], list[str]]:
    """Keyword match con soporte de aliases.

    skills_target puede contener:
    - strings simples: "Brand Strategy"  (backward compatible)
    - dicts: {"skill": "C1 English", "aliases": ["c1/c2", "inglés c1"]}

    El campo "skill" es el nombre canónico que aparece en matched/gaps.
    Los aliases siempre se buscan en minúsculas (haystack ya está en lower).
    """
    haystack = (cv_text + " " + job_desc).lower()
    matched, gaps = [], []
    for entry in skills_target:
        if isinstance(entry, dict):
            skill_name = entry["skill"]
            terms = [skill_name.lower()] + [a.lower() for a in entry.get("aliases", [])]
        else:
            skill_name = entry
            terms = [entry.lower()]
        if any(t in haystack for t in terms):
            matched.append(skill_name)
        else:
            gaps.append(skill_name)
    score = (len(matched) / len(skills_target) * 100) if skills_target else 0.0
    return score, matched, gaps
```

También actualizar la type hint en la firma (línea 98 — `list[str]` → `list`):

La firma nueva ya está arriba: `skills_target: list,` (sin `[str]`).

- [ ] **Step 4: Verificar que los 6 tests nuevos pasan**

```
pytest tests/test_skill_matcher_narrativas.py::TestSkillMatcherAliases -v
```

Esperado: los 6 tests `PASSED`

- [ ] **Step 5: Verificar que los tests existentes de narrativas siguen en verde**

```
pytest tests/test_skill_matcher_narrativas.py -v
```

Esperado: todos los tests pasan (backward compat total — strings siguen funcionando).

- [ ] **Step 6: Commit**

```
git add tests/test_skill_matcher_narrativas.py agents/skill_matcher.py
git commit -m "feat: _keyword_score soporta aliases en skills_target (backward compat)"
```

---

## Task 4: Fórmula 20/80 — RED test primero

**Files:**
- Modify: `tests/test_skill_matcher_narrativas.py` (agregar 2 tests de fórmula a `TestSkillMatcherAliases`)
- Modify: `agents/skill_matcher.py:192`

- [ ] **Step 1: Agregar los 2 tests de fórmula al final de `TestSkillMatcherAliases`**

Dentro de la clase `TestSkillMatcherAliases` (al final, después del test `test_mixed_list_plain_and_dict`), agregar:

```python
    def test_formula_weight_20_80(self):
        """kw=50%, sem=78% con fórmula 20/80 = 72 (no 67 que daba la fórmula 40/60)."""
        kw, sem = 50.0, 78.0
        result = round(kw * 0.20 + sem * 0.80)
        assert result == 72

    def test_valatam_scenario_passes_threshold_75(self):
        """Reproduce el caso real Valatam: 3/4 aliases match + sem=78% debe superar threshold 75."""
        kw, sem = 75.0, 78.0
        result = round(kw * 0.20 + sem * 0.80)
        assert result >= 75   # 15 + 62.4 = 77.4 → 77 ✓
```

Estos tests son de aritmética pura — no dependen de `analyze()`, por eso son GREEN inmediatamente. No necesitan RED. Verificar que pasan:

```
pytest tests/test_skill_matcher_narrativas.py::TestSkillMatcherAliases::test_formula_weight_20_80 tests/test_skill_matcher_narrativas.py::TestSkillMatcherAliases::test_valatam_scenario_passes_threshold_75 -v
```

Esperado: ambos `PASSED` (son cálculos numéricos sin código de producción)

- [ ] **Step 2: Actualizar la fórmula en `analyze()`**

En `agents/skill_matcher.py` línea ~192, reemplazar:

```python
    final = round(kw_score * 0.40 + sem_score * 0.60)
```

por:

```python
    final = round(kw_score * 0.20 + sem_score * 0.80)
```

- [ ] **Step 3: Actualizar el docstring del módulo (línea 9)**

Reemplazar:

```python
  - 40 % keyword match (skills_target del perfil vs texto del CV + descripción del cargo)
  - 60 % scoring semántico vía Claude (prompt caching: el CV se cachea entre llamadas)
```

por:

```python
  - 20 % keyword match (skills_target del perfil vs texto del CV + descripción del cargo)
  - 80 % scoring semántico vía Claude (prompt caching: el CV se cachea entre llamadas)
```

- [ ] **Step 4: Correr el suite completo de skill_matcher y cv_rewriter**

```
pytest tests/test_skill_matcher_narrativas.py tests/test_cv_rewriter.py -v --tb=short
```

Esperado: todos los tests pasan. Verificar en particular:
- `TestSkillMatcherAliases` — 8 tests verdes
- `TestThresholdProfiles` — 3 tests verdes (rama A=75, B=75, C=75)
- `TestThresholdAtsProfiles` — 3 tests verdes (sin cambio)
- `TestKeywordScoreImprovement` — verde (backward compat string lists)

- [ ] **Step 5: Commit**

```
git add agents/skill_matcher.py tests/test_skill_matcher_narrativas.py
git commit -m "feat: formula skill_matcher 40/60 -> 20/80 (semantic-primary)"
```

---

## Task 5: Validación final

**Files:** ninguno (solo correr tests y smoke manual)

- [ ] **Step 1: Correr el suite completo del proyecto**

```
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Esperado: todos los tests pasan. Cualquier falla es un bloqueante — no avanzar.

- [ ] **Step 2: Smoke test rápido con Valatam (sin browser)**

Ejecutar el módulo directamente para verificar que `analyze()` retorna score ≥ 75 y `passed=True` con el JD real de Valatam (usar fragmento inline — no requiere Playwright):

```python
# Ejecutar desde el directorio raíz del proyecto:
python -c "
import sys, os
sys.path.insert(0, '.')
from agents.cv_parser import parse_cv
from agents.skill_matcher import analyze

cv = parse_cv()

# Fragmento real del JD de Valatam extraído el 2026-05-20
job = {
    'cargo': 'Digital Marketing Account Manager',
    'empresa': 'Valatam',
    'descripcion': (
        'We are seeking a Digital Marketing Account Manager. '
        'Requirements: C1/C2 English proficiency, brand strategy experience, '
        'data analysis, digital transformation leadership, Google Ads, Meta Ads. '
        'Fully remote position. Strong analytical skills required.'
    ),
    'modalidad': 'Remoto',
    'ubicacion': 'Colombia',
}

r = analyze(cv, job, 'A')
print(f'Score: {r[\"score\"]}% | Threshold: {r[\"threshold\"]}% | Passed: {r[\"passed\"]}')
print(f'Match: {r[\"skills_match\"]}')
print(f'Gaps:  {r[\"skills_gap\"]}')
"
```

Esperado:
- `Score: 75%+`
- `Passed: True`
- `C1 English` en `skills_match` (alias `c1/c2` matchea)
- `Digital Transformation` en `skills_match` (nombre canónico matchea directo)

- [ ] **Step 3: Verificar que los dry-run jobs históricos siguen pasando**

```python
python -c "
import sys
sys.path.insert(0, '.')
from agents.cv_parser import parse_cv
from agents.skill_matcher import analyze

cv = parse_cv()

# Job sólido de Rama A (simulado) — debe seguir pasando con threshold 75
job_accenture = {
    'cargo': 'Marketing Strategy Manager',
    'empresa': 'Accenture',
    'descripcion': (
        'Brand strategy and digital transformation leadership. '
        'Data analysis, C1 English required. '
        'Consulting experience in brand positioning and market strategy. '
        'Advanced English fluency essential.'
    ),
    'modalidad': 'Híbrido',
    'ubicacion': 'Bogotá',
}
r = analyze(cv, job_accenture, 'A')
print(f'Accenture → Score: {r[\"score\"]}% | Passed: {r[\"passed\"]} (esperado: True)')

# Job pobre — debe seguir siendo rechazado
job_pobre = {
    'cargo': 'Data Entry Clerk',
    'empresa': 'BPO Random',
    'descripcion': 'Ingreso de datos, manejo de Excel básico, no se requiere experiencia.',
    'modalidad': 'Presencial',
    'ubicacion': 'Bogotá',
}
r2 = analyze(cv, job_pobre, 'A')
print(f'BPO Pobre → Score: {r2[\"score\"]}% | Passed: {r2[\"passed\"]} (esperado: False)')
"
```

Esperado:
- Accenture: `Passed: True` (score ≥ 75)
- BPO Pobre: `Passed: False` (score < 75 — semántico bajo garantiza rechazo)

- [ ] **Step 4: Commit final si hay cambios pendientes**

```
git status
# Si hay algo sin commitear:
git add -A
git commit -m "chore: validacion final skill-matcher aliases + reweight completa"
```

---

## Criterio de éxito

1. `pytest tests/test_cv_rewriter.py tests/test_skill_matcher_narrativas.py` — todos en verde
2. `analyze(cv, valatam_job, 'A')` retorna `score ≥ 75, passed=True`
3. Jobs pobres (BPO, Data Entry) siguen siendo rechazados con el nuevo threshold
4. Accenture/Grupo Éxito dry-run siguen pasando

---

## Comportamiento esperado post-fix (referencia)

| Escenario | kw | sem | final nuevo | Resultado |
|---|---|---|---|---|
| Valatam (con aliases 3/4) | 75% | 78% | **77%** | PASA ✓ |
| Worx1 (con aliases 3/4) | 75% | 72% | **73%** | MARGINAL — depende de sem real |
| Job excelente (4/4 + sem=85%) | 100% | 85% | **88%** | PASA ✓ |
| Job pobre (2/4 + sem=60%) | 50% | 60% | **58%** | RECHAZADO ✓ |
| Job sin keywords (0/4 + sem=88%) | 0% | 88% | **70%** | RECHAZADO ✓ |
| Job keyword-only (4/4 + sem=65%) | 100% | 65% | **72%** | RECHAZADO ✓ |
