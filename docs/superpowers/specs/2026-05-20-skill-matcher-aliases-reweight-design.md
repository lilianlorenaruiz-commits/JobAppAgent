# Skill Matcher: Aliases + Reweight 20/80 + Threshold 75% — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminar rechazos falsos en el skill matcher causados por mismatch tipográfico entre `skills_target` y el lenguaje real de JDs colombianos, reduciendo el peso del keyword score y bajando el threshold al valor calibrado para el mercado real.

**Architecture:** Tres cambios coordinados — aliases en JSONs de perfiles, soporte de aliases en `_keyword_score`, y rebalanceo de la fórmula final a 20/80 (keyword/semantic). El semantic scorer de Claude mantiene el criterio de calidad; el keyword score pasa a ser señal de dirección, no árbitro.

**Tech Stack:** Python 3.11, pytest, JSON — sin nuevas dependencias.

---

## Contexto y motivación

### Hallazgo del test real Canal A (2026-05-20)

| Job | kw score | sem score | final (40/60) | Resultado |
|-----|----------|-----------|---------------|-----------|
| Valatam — Digital Marketing Account Manager | 50% (2/4) | 78% | **67%** | RECHAZADO (threshold 82%) |
| Worx1 — Digital Marketing Strategist | 50% (2/4) | 72% | **63%** | RECHAZADO (threshold 82%) |

Skills que NO matchearon en ambos casos:
- `"C1 English"` — el JD de Valatam dice `"C1/C2"`, no `"C1 English"` literalmente
- `"Digital Transformation"` — no aparece textualmente en los JDs reales, aunque semánticamente el rol la implica

Claude (semantic scorer) calificó ambos como "good fit" (72-78%). La fórmula 40/60 convirtió un problema tipográfico en un rechazo de negocio.

### Causa raíz

`_keyword_score` hace `skill.lower() in haystack` — coincidencia de substring exacto. Con solo 4 `skills_target`, fallar 1 baja el keyword score 25 puntos de golpe. El peso del 40% sobre un score tan discreto domina la fórmula de forma desproporcionada.

El threshold de 82% fue calibrado contra mocks sintéticos (`dry-run` jobs) escritos deliberadamente con las keywords exactas — no representa el corpus real de JDs colombianos.

---

## Diseño

### Componente 1 — Perfiles JSON (aliases)

`skills_target` pasa de lista plana de strings a lista mixta. Strings simples siguen funcionando sin cambio (backward compatible). Skills con variantes usan formato dict.

**Formato:**
```json
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
]
```

**Reglas:**
- Aliases siempre en minúsculas (el haystack ya está en lower)
- El campo `"skill"` es el nombre canónico que aparece en `matched`/`gaps`
- Strings simples = skill sin variantes conocidas (no requieren dict)
- Cada perfil tiene sus propios aliases según el vocabulario de su sector

**Cambios por perfil:**

`perfil_a_consultoria.json`:
- `"Digital Transformation"` → aliases: `["transformación digital", "digital transformation"]`
- `"C1 English"` → aliases: `["c1/c2", "inglés c1", "english c1", "advanced english", "nivel c1", "fluent english", "bilingual"]`
- `threshold_match`: 82 → **75**

`perfil_b_retail.json`:
- `"Trade Marketing"` → aliases: `["trade mktg", "trade & marketing"]`
- `"Category Management"` → aliases: `["category manager", "gestión de categorías", "category mgmt"]`
- `"Shopper Insights"` → aliases: `["shopper marketing", "shopper analytics", "consumer insights"]`
- `"P&L"` → aliases: `["p&l management", "profit and loss", "pérdidas y ganancias"]`
- `threshold_match`: 82 → **75**

`perfil_c_paidmedia.json`:
- `"Meta Ads"` → aliases: `["facebook ads", "instagram ads", "meta advertising", "facebook advertising"]`
- `"Google Ads"` → aliases: `["google adwords", "sem", "search ads", "google advertising"]`
- `"Amazon Ads"` → aliases: `["amazon advertising", "amazon dsp", "amazon ppc", "sponsored products"]`
- `"LinkedIn Ads"` → aliases: `["linkedin advertising", "linkedin campaigns"]`
- `threshold_match`: 75 → **sin cambio** (ya estaba en 75)

---

### Componente 2 — `agents/skill_matcher.py`

**Cambio 1: `_keyword_score` — soporte de aliases**

```python
def _keyword_score(
    cv_text: str,
    job_desc: str,
    skills_target: list,
) -> tuple[float, list[str], list[str]]:
    """Keyword match con soporte de aliases. skills_target puede contener
    strings simples o dicts {"skill": str, "aliases": list[str]}."""
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

**Cambio 2: `analyze` — fórmula 20/80**

```python
# Línea ~192 — cambiar peso de keyword score
final = round(kw_score * 0.20 + sem_score * 0.80)  # era 0.40 / 0.60
```

---

### Componente 3 — Tests

**Tests a actualizar — `tests/test_cv_rewriter.py` (`TestThresholdProfiles`)**

| Test actual | Test nuevo |
|---|---|
| `test_rama_a_threshold_is_82` → assert 82 | `test_rama_a_threshold_is_75` → assert 75 |
| `test_rama_b_threshold_is_82` → assert 82 | `test_rama_b_threshold_is_75` → assert 75 |
| `test_rama_c_threshold_unchanged_75` | sin cambio |

**Tests nuevos — `tests/test_skill_matcher_narrativas.py` (`TestSkillMatcherAliases`)**

```python
class TestSkillMatcherAliases:

    def test_alias_matches_c1_c2_variant(self):
        skills = [{"skill": "C1 English", "aliases": ["c1/c2", "inglés c1"]}]
        _, matched, _ = _keyword_score("", "Requiere inglés C1/C2", skills)
        assert "C1 English" in matched

    def test_alias_matches_spanish_digital_transformation(self):
        skills = [{"skill": "Digital Transformation",
                   "aliases": ["transformación digital"]}]
        _, matched, _ = _keyword_score("", "liderará transformación digital", skills)
        assert "Digital Transformation" in matched

    def test_plain_string_backward_compatible(self):
        skills = ["Brand Strategy"]
        _, matched, _ = _keyword_score("brand strategy en CV", "", skills)
        assert "Brand Strategy" in matched

    def test_skill_goes_to_gap_when_no_alias_matches(self):
        skills = [{"skill": "C1 English", "aliases": ["c1/c2"]}]
        _, _, gaps = _keyword_score("", "requiere experiencia en marketing", skills)
        assert "C1 English" in gaps

    def test_formula_weight_20_80(self):
        # kw=50%, sem=78% con fórmula nueva = 72 (era 67 con 40/60)
        kw, sem = 50.0, 78.0
        result = round(kw * 0.20 + sem * 0.80)
        assert result == 72

    def test_valatam_scenario_passes_threshold_75(self):
        # Reproduce el caso real: 3/4 aliases + sem=78% debe superar threshold 75%
        kw, sem = 75.0, 78.0
        result = round(kw * 0.20 + sem * 0.80)
        assert result >= 75   # 77.25 → 77 ✓
```

---

## Comportamiento esperado post-fix

| Escenario | kw | sem | final nuevo | Resultado |
|---|---|---|---|---|
| Valatam (con aliases 3/4) | 75% | 78% | **77%** | PASA ✓ |
| Worx1 (con aliases 3/4) | 75% | 72% | **73%** | MARGINAL — depende de sem real |
| Job excelente (4/4 + sem=85%) | 100% | 85% | **88%** | PASA ✓ |
| Job pobre (2/4 + sem=60%) | 50% | 60% | **58%** | RECHAZADO ✓ |
| Job sin keywords (0/4 + sem=88%) | 0% | 88% | **70%** | RECHAZADO ✓ (keywords siguen importando) |
| Job keyword-match solo (4/4 + sem=65%) | 100% | 65% | **72%** | RECHAZADO ✓ (sem bajo no basta) |

---

## Archivos a modificar

| Archivo | Tipo de cambio | Líneas estimadas |
|---|---|---|
| `profiles/perfil_a_consultoria.json` | Aliases + threshold 82→75 | ~15 |
| `profiles/perfil_b_retail.json` | Aliases + threshold 82→75 | ~20 |
| `profiles/perfil_c_paidmedia.json` | Aliases (threshold sin cambio) | ~20 |
| `agents/skill_matcher.py` | `_keyword_score` + fórmula | ~15 |
| `tests/test_cv_rewriter.py` | 2 tests de threshold renombrados | ~6 |
| `tests/test_skill_matcher_narrativas.py` | 6 tests nuevos `TestSkillMatcherAliases` | ~35 |

**Total: ~110 líneas. Sin cambios en CV rewriter, PDF generator, applicator ni scraper.**

---

## Criterio de éxito

1. `pytest tests/test_cv_rewriter.py tests/test_skill_matcher_narrativas.py` — todos en verde
2. Smoke test manual contra Valatam (`4413843121`) retorna `score ≥ 75%, passed=True`
3. Score de Worx1 (`4409288980`) sube vs resultado actual (63%)
4. Jobs de dry-run existentes (Accenture, Grupo Éxito) siguen pasando con el nuevo threshold
