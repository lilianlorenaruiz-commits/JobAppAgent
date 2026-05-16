# Evidence-Based CV Rewriter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar keyword injection con evidence mapping trazable a `narrativas_lorena.json` — cada claim del CV verificable con un bullet real.

**Architecture:** Nuevo módulo `evidence_mapper.py` construye un mapa de evidencia (Tier 1/2/3) antes de invocar Claude. `cv_rewriter.py` recibe ese mapa y redacta solo con él. `ats_auditor.py` agrega campo `tier3_skills_count` para que el retry loop detecte poor fit.

**Tech Stack:** Python 3.11+, Anthropic SDK (`claude-haiku-4-5-20251001` para mapper, `claude-sonnet-4-6` para rewriter), pytest, unittest.mock.

---

## Archivos

| Acción | Archivo | Responsabilidad |
|---|---|---|
| Crear | `agents/evidence_mapper.py` | Extraer skills del JD, buscar evidencia en narrativas, clasificar tiers |
| Crear | `tests/test_evidence_mapper.py` | Tests TDD para evidence_mapper |
| Modificar | `agents/cv_rewriter.py` | Importar mapper, pasar mapa a Claude, reemplazar reglas 7/10, retry nuevo |
| Modificar | `agents/ats_auditor.py` | Agregar `tier3_skills_count` y `claims_sin_evidencia` al output |
| Crear | `tests/test_evidence_rewriter.py` | Tests para las modificaciones del rewriter |

---

## Task 1: `agents/evidence_mapper.py` — TDD

**Files:**
- Create: `agents/evidence_mapper.py`
- Test: `tests/test_evidence_mapper.py`

### Step 1.1 — Escribir tests que fallan

- [ ] Crear `tests/test_evidence_mapper.py` con este contenido:

```python
"""
Tests TDD para evidence_mapper.py.
Todos los tests usan Claude mockeado — no llaman la API real.
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NARRATIVAS_MINI = {
    "roles": [
        {
            "empresa": "Alcalisa S.A.",
            "logros": [
                "Grew company revenue from USD 1.5M to USD 3.0M in 4 years (+100%), leading brand strategy and trade marketing.",
                "Grew market share from 12% to 18% in Ecuador spirits segment.",
                "Trained 150+ people per year: regional distributors, bartenders, and HORECA staff.",
            ],
        },
        {
            "empresa": "Avanti IT SAS",
            "logros": [
                "Increased client satisfaction by 20 percent through conversational flow optimization.",
                "Implemented chatbot for COMFENALCO EPS — reduced physical load by 80 percent.",
            ],
        },
        {
            "empresa": "Amazon, Colombia",
            "logros": [
                "Narwal: tROAS improved from 1.28x to 3.28x; USD 100,000 attributed sales in 30 days via DSP remarketing.",
                "Designed funnel-based reporting format adopted as internal standard by all Account Executives.",
            ],
        },
    ],
    "plataformas": {
        "meta_ads": {
            "empresas": ["Alcalisa S.A."],
            "logro_destacado": "USD 800 Facebook Ads → +18% ventas Bellows whisky Supermaxi diciembre.",
        }
    },
    "liderazgo": {
        "empresa_y_rol": "Alcalisa S.A. — National Marketing Manager (2013-2018)",
        "logro_coordinacion": "Lanzamiento Secreto Inti: estrategia HORECA → retail. 20+ puntos premium 2015. Codificado en Supermaxi 2016.",
        "capacitacion_anual": "150+ personas/año — distribuidores regionales, bartenders, HORECA hoteles 5 estrellas.",
    },
    "trade_retail": {
        "pl_ventas_anuales": "USD 1.5M (2013) → USD 3.0M (2017)",
        "market_share": "12% (2013) → 18% (2017) — +6 p.p.",
        "activaciones_anuales": "12-15 por año",
    },
    "brand_strategy": {
        "proyecto_mas_grande": "GRC S.A. — creación y posicionamiento de 3 marcas de vino para exportación China y Rusia.",
        "datos_awareness": "Alcalisa: awareness 18% → 34%; share of voice digital 0% → 45%.",
        "lanzamientos_liderados": "8 lanzamientos de productos + 6 campañas 360°.",
    },
}

_JD_RETAIL = (
    "Buscamos Category Manager con experiencia en gestión de categorías, "
    "trade marketing, liderazgo de equipos y planificación de surtido. "
    "Manejo de cadenas retail (Supermaxi, Éxito). "
    "Inglés B2 requerido. Bogotá, híbrido."
)

_JD_WMS = (
    "Se requiere Warehouse Manager con dominio de WMS, gestión de inventario, "
    "logística de última milla y picking. Excel avanzado."
)


def _mock_haiku(skills_text: str = "gestión de categorías\ntrade marketing\nliderazgo de equipos",
                match_indices: str = "0, 1"):
    """Mock del cliente Anthropic: primera llamada = extracción skills, segunda = matching."""
    responses = [
        MagicMock(content=[MagicMock(text=skills_text)]),
        MagicMock(content=[MagicMock(text=match_indices)]),
    ]
    client = MagicMock()
    client.messages.create.side_effect = responses
    return client


# ── Tests: _flatten_narrativas ────────────────────────────────────────────────

class TestFlattenNarrativas:
    def test_returns_list_of_dicts(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        assert isinstance(result, list)
        assert all("rol" in item and "bullet" in item for item in result)

    def test_includes_role_logros(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("tROAS" in b for b in bullets), "Bullets de Amazon no incluidos"
        assert any("chatbot" in b for b in bullets), "Bullets de Avanti IT no incluidos"

    def test_includes_platform_logros(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("Bellows" in b for b in bullets), "Logro de plataforma meta_ads no incluido"

    def test_includes_liderazgo_and_trade(self):
        from agents.evidence_mapper import _flatten_narrativas
        result = _flatten_narrativas(_NARRATIVAS_MINI)
        bullets = [item["bullet"] for item in result]
        assert any("Secreto Inti" in b for b in bullets), "Logro de liderazgo no incluido"
        assert any("1.5M" in b for b in bullets), "Dato de trade_retail no incluido"


# ── Tests: _c1_active_subject ─────────────────────────────────────────────────

class TestC1ActiveSubject:
    def test_active_verb_grows(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Grew revenue from 1.5M to 3.0M") is True

    def test_active_verb_managed(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Managed 300 B2B accounts across Latin America") is True

    def test_active_verb_implemented(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Implemented chatbot for COMFENALCO EPS") is True

    def test_support_verb_supported(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("Supported 4 Account Executives with campaign reporting") is False

    def test_empty_bullet(self):
        from agents.evidence_mapper import _c1_active_subject
        assert _c1_active_subject("") is False


# ── Tests: build_evidence_map ─────────────────────────────────────────────────

class TestBuildEvidenceMap:
    def test_returns_dict(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        assert isinstance(result, dict)

    def test_skills_have_tier_and_evidencia_keys(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        for skill, data in result.items():
            assert "tier" in data, f"Skill '{skill}' sin clave 'tier'"
            assert "evidencia" in data, f"Skill '{skill}' sin clave 'evidencia'"

    def test_tier_values_are_1_2_or_3(self):
        from agents.evidence_mapper import build_evidence_map
        client = _mock_haiku()
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_RETAIL, _NARRATIVAS_MINI)
        for skill, data in result.items():
            assert data["tier"] in (1, 2, 3), f"Tier inválido para '{skill}': {data['tier']}"

    def test_tier3_has_empty_evidencia(self):
        from agents.evidence_mapper import build_evidence_map
        # Mock que dice NONE para todos los matches → todos Tier 3
        responses = [
            MagicMock(content=[MagicMock(text="gestión de inventario WMS\nlogística de última milla")]),
            MagicMock(content=[MagicMock(text="NONE")]),
            MagicMock(content=[MagicMock(text="NONE")]),
        ]
        client = MagicMock()
        client.messages.create.side_effect = responses
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map(_JD_WMS, _NARRATIVAS_MINI)
        tier3 = {k: v for k, v in result.items() if v["tier"] == 3}
        assert len(tier3) > 0, "JD de WMS debería producir al menos un Tier 3"
        for skill, data in tier3.items():
            assert data["evidencia"] == [], f"Tier 3 '{skill}' debe tener evidencia=[]"

    def test_active_verb_bullet_yields_tier1(self):
        from agents.evidence_mapper import build_evidence_map
        # Mock: skill "trade marketing", match retorna índice 0 (bullet "Grew revenue...")
        responses = [
            MagicMock(content=[MagicMock(text="trade marketing")]),
            MagicMock(content=[MagicMock(text="0")]),  # matches "Grew revenue" (active verb)
        ]
        client = MagicMock()
        client.messages.create.side_effect = responses
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map("trade marketing experience required", _NARRATIVAS_MINI)
        assert result["trade marketing"]["tier"] == 1, (
            f"Bullet 'Grew revenue' (active verb) debe ser Tier 1, got {result['trade marketing']['tier']}"
        )

    def test_no_api_call_when_narrativas_empty(self):
        from agents.evidence_mapper import build_evidence_map
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text="algún skill")]),
            MagicMock(content=[MagicMock(text="NONE")]),
        ]
        with patch("agents.evidence_mapper._get_client", return_value=client):
            result = build_evidence_map("some JD", {})
        # Debe retornar sin romper
        assert isinstance(result, dict)


# ── Tests: verify_evidence ────────────────────────────────────────────────────

class TestVerifyEvidence:
    def test_returns_empty_list_when_tier1_present_in_cv(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "trade marketing": {
                "tier": 1,
                "evidencia": [{"rol": "Alcalisa", "bullet": "Grew revenue from USD 1.5M to USD 3.0M in 4 years"}],
            }
        }
        cv_text = "WORK EXPERIENCE\n- Grew revenue from USD 1.5M to USD 3.0M in 4 years leading trade marketing"
        result = verify_evidence(cv_text, evidence_map)
        assert result == [], f"No debería haber skills faltantes, got: {result}"

    def test_returns_skill_when_tier1_absent_from_cv(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "trade marketing": {
                "tier": 1,
                "evidencia": [{"rol": "Alcalisa", "bullet": "Grew market share from 12% to 18%"}],
            }
        }
        cv_text = "WORK EXPERIENCE\n- Managed social media campaigns"
        result = verify_evidence(cv_text, evidence_map)
        assert "trade marketing" in result, f"Skill faltante no detectado: {result}"

    def test_ignores_tier2_and_tier3(self):
        from agents.evidence_mapper import verify_evidence
        evidence_map = {
            "planificación de surtido": {"tier": 2, "evidencia": [{"rol": "Avanti", "bullet": "Supported retailers"}]},
            "gestión WMS": {"tier": 3, "evidencia": []},
        }
        cv_text = "No menciona ninguno de estos skills"
        result = verify_evidence(cv_text, evidence_map)
        assert result == [], f"verify_evidence no debe reportar Tier 2/3 como faltantes: {result}"
```

- [ ] Verificar que los tests fallan:

```
cd "C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent"
python -m pytest tests/test_evidence_mapper.py -v
```

Expected: `ImportError: No module named 'agents.evidence_mapper'` (el módulo no existe aún)

---

### Step 1.2 — Implementar `agents/evidence_mapper.py`

- [ ] Crear `agents/evidence_mapper.py`:

```python
"""
Evidence Mapper — pre-proceso para cv_rewriter.

Dado un JD y narrativas_lorena.json, produce un evidence_map:
  {skill: {"tier": 1|2|3, "evidencia": [{"rol": str, "bullet": str}]}}

Tier 1: evidencia directa — Lorena es sujeto activo (C1) + contexto específico (C2) + actividad transferible (C3)
Tier 2: exposición — C2+C3 sin C1 (consultora, soporte, adyacente)
Tier 3: sin match — evidencia=[] — aparece en mapa para que retry loop cuente poor fit

Constante de configuración:
  POOR_FIT_THRESHOLD = 5  — si hay más de 5 Tier 3, flag poor_fit en cv_rewriter
"""
import os
import sys

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

POOR_FIT_THRESHOLD = 5

_client: anthropic.Anthropic | None = None

# Verbos de acción que indican que Lorena es sujeto activo (C1 = True)
_ACTIVE_VERBS = {
    "managed", "led", "implemented", "grew", "achieved", "designed",
    "reduced", "increased", "exceeded", "secured", "trained", "built",
    "created", "developed", "delivered", "launched", "generated",
    "optimized", "transformed", "coordinated", "directed", "executed",
    "handled", "oversaw", "drove", "spearheaded", "established",
    "deployed", "negotiated", "closed", "grew", "produced",
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key or key.startswith("PEGA_AQUI"):
            raise RuntimeError("API key de Anthropic no configurada.")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _flatten_narrativas(narrativas: dict) -> list[dict]:
    """
    Extrae todos los bullets de narrativas_lorena.json en formato {rol, bullet}.
    Cubre: roles[].logros, plataformas[].logro_destacado, liderazgo, trade_retail, brand_strategy.
    """
    items = []

    # Roles principales
    for role in narrativas.get("roles", []):
        empresa = role.get("empresa", "")
        for bullet in role.get("logros", []):
            if bullet:
                items.append({"rol": empresa, "bullet": bullet})

    # Plataformas
    for plat_name, plat_data in narrativas.get("plataformas", {}).items():
        if not isinstance(plat_data, dict):
            continue
        logro = plat_data.get("logro_destacado", "")
        if logro:
            empresas = plat_data.get("empresas", [])
            rol = empresas[0] if empresas else plat_name
            items.append({"rol": rol, "bullet": logro})

    # Liderazgo
    liderazgo = narrativas.get("liderazgo", {})
    empresa_liderazgo = liderazgo.get("empresa_y_rol", "Alcalisa S.A.")
    for key in ("logro_coordinacion", "capacitacion_anual"):
        val = liderazgo.get(key, "")
        if val:
            items.append({"rol": empresa_liderazgo, "bullet": val})

    # Trade/retail
    trade = narrativas.get("trade_retail", {})
    for key in ("pl_ventas_anuales", "market_share", "activaciones_anuales", "shopper_insights"):
        val = trade.get(key, "")
        if val:
            items.append({"rol": "Alcalisa S.A.", "bullet": f"{key}: {val}"})

    # Brand strategy
    brand = narrativas.get("brand_strategy", {})
    for key in ("proyecto_mas_grande", "datos_awareness", "lanzamientos_liderados", "transformacion_digital"):
        val = brand.get(key, "")
        if val:
            items.append({"rol": "Alcalisa/GRC", "bullet": val})

    return items


def _c1_active_subject(bullet: str) -> bool:
    """
    C1: Lorena es sujeto activo.
    True si la primera palabra del bullet es un verbo de acción directa.
    False si el bullet empieza con verbo de soporte ("supported", "participated", etc.)
    """
    words = bullet.strip().split()
    if not words:
        return False
    first = words[0].lower().rstrip(".,;:")
    return first in _ACTIVE_VERBS


def _extract_jd_skills(job_description: str) -> list[str]:
    """
    Extrae lista de skills del JD usando Claude Haiku.
    Returns lista de strings, máx 20 items.
    """
    client = _get_client()
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Extract the key skills, competencies, and requirements from this job description. "
                "Output ONLY a plain list — one item per line, no numbering, no bullets, no explanation.\n\n"
                f"JOB DESCRIPTION:\n{job_description[:2000]}"
            ),
        }],
    )
    raw = response.content[0].text.strip()
    skills = [line.strip() for line in raw.splitlines() if line.strip()]
    return skills[:20]


def _find_matching_bullets(skill: str, all_bullets: list[dict]) -> list[dict]:
    """
    Encuentra bullets que cubren el skill dado.
    Paso 1: keyword match rápido (determinista).
    Paso 2: Claude Haiku semántico si keyword no encontró nada.
    """
    skill_words = {w for w in skill.lower().split() if len(w) > 3}
    keyword_matches = []
    remaining = []

    for item in all_bullets:
        bullet_lower = item["bullet"].lower()
        if any(w in bullet_lower for w in skill_words):
            keyword_matches.append(item)
        else:
            remaining.append(item)

    if keyword_matches:
        return keyword_matches

    # Semantic fallback via Claude Haiku
    if not remaining:
        return []

    client = _get_client()
    bullets_text = "\n".join(
        f"[{i}] ({item['rol']}) {item['bullet'][:120]}"
        for i, item in enumerate(remaining[:30])
    )
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Skill to match: \"{skill}\"\n\n"
                f"Bullets (numbered):\n{bullets_text}\n\n"
                "Which bullet numbers describe experience relevant to this skill? "
                "Output ONLY the numbers comma-separated. If none match, output: NONE"
            ),
        }],
    )
    raw = response.content[0].text.strip()
    if "NONE" in raw.upper() or not raw:
        return []
    try:
        indices = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        return [remaining[i] for i in indices if i < len(remaining)]
    except Exception:
        return []


def build_evidence_map(job_description: str, narrativas: dict) -> dict:
    """
    Construye el evidence_map para un JD dado.

    Returns:
        {
          skill: {
            "tier": 1 | 2 | 3,
            "evidencia": [{"rol": str, "bullet": str}]
          }
        }

    Tier 3 → evidencia=[] — skill sin match.
    Aparece en el mapa para que el retry loop cuente poor fit.
    """
    skills = _extract_jd_skills(job_description)
    all_bullets = _flatten_narrativas(narrativas)
    evidence_map = {}

    for skill in skills:
        matching = _find_matching_bullets(skill, all_bullets)

        if not matching:
            evidence_map[skill] = {"tier": 3, "evidencia": []}
            continue

        # Clasificar tier: el mejor tier entre todos los bullets matching gana
        best_tier = 3
        best_evidencia = []

        for item in matching:
            c1 = _c1_active_subject(item["bullet"])
            tier = 1 if c1 else 2
            if tier < best_tier:
                best_tier = tier
                best_evidencia = []
            if tier == best_tier:
                best_evidencia.append({
                    "rol": item["rol"],
                    "bullet": item["bullet"][:200],
                })

        evidence_map[skill] = {
            "tier": best_tier,
            "evidencia": best_evidencia[:3],  # máximo 3 bullets por skill
        }

    return evidence_map


def verify_evidence(cv_text: str, evidence_map: dict) -> list[str]:
    """
    Verifica que cada skill Tier 1 del evidence_map aparece en el CV.
    Returns lista de skills con evidencia Tier 1 ausente del cv_text.
    Solo verifica Tier 1 — Tier 2 y Tier 3 se ignoran.
    """
    missing = []
    cv_lower = cv_text.lower()

    for skill, data in evidence_map.items():
        if data["tier"] != 1:
            continue
        found = False
        for ev in data["evidencia"]:
            # Buscar las primeras 4 palabras del bullet en el CV
            key_words = ev["bullet"].lower().split()[:4]
            key_phrase = " ".join(key_words)
            if len(key_phrase) > 5 and key_phrase in cv_lower:
                found = True
                break
        if not found:
            missing.append(skill)

    return missing
```

### Step 1.3 — Correr tests y verificar que pasan

- [ ] Ejecutar:

```
python -m pytest tests/test_evidence_mapper.py -v
```

Expected output:
```
tests/test_evidence_mapper.py::TestFlattenNarrativas::test_returns_list_of_dicts PASSED
tests/test_evidence_mapper.py::TestFlattenNarrativas::test_includes_role_logros PASSED
tests/test_evidence_mapper.py::TestFlattenNarrativas::test_includes_platform_logros PASSED
tests/test_evidence_mapper.py::TestFlattenNarrativas::test_includes_liderazgo_and_trade PASSED
tests/test_evidence_mapper.py::TestC1ActiveSubject::test_active_verb_grows PASSED
tests/test_evidence_mapper.py::TestC1ActiveSubject::test_active_verb_managed PASSED
tests/test_evidence_mapper.py::TestC1ActiveSubject::test_active_verb_implemented PASSED
tests/test_evidence_mapper.py::TestC1ActiveSubject::test_support_verb_supported PASSED
tests/test_evidence_mapper.py::TestC1ActiveSubject::test_empty_bullet PASSED
... (todos PASSED)
```

### Step 1.4 — Commit

- [ ] Commitear:

```bash
git add agents/evidence_mapper.py tests/test_evidence_mapper.py
git commit -m "feat: evidence_mapper — build_evidence_map con tiers + verify_evidence"
```

---

## Task 2: Modificar `agents/cv_rewriter.py`

**Files:**
- Modify: `agents/cv_rewriter.py`
- Test: `tests/test_evidence_rewriter.py`

### Step 2.1 — Escribir tests que fallan

- [ ] Crear `tests/test_evidence_rewriter.py`:

```python
"""
Tests para las modificaciones del cv_rewriter:
- evidence_map se pasa a Claude en el prompt
- Reglas 7 y 10 eliminadas del _SYSTEM
- Retry note "Increase keyword density" eliminada
- poor_fit flag aparece cuando hay muchos Tier 3
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB = {
    "cargo": "Category Manager",
    "empresa": "Falabella",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "descripcion": (
        "Buscamos Category Manager con experiencia en gestión de categorías, "
        "trade marketing, liderazgo de equipos y planificación de surtido."
    ),
    "rama": "B",
}

_CV_DICT = {
    "nombre": "Lorena Ruiz",
    "experiencia": [
        {"cargo": "National Marketing Manager", "empresa": "Alcalisa S.A.",
         "fecha": "2013 – 2018", "descripcion": "Trade marketing."}
    ],
    "educacion": [],
    "skills": ["Trade Marketing", "Category Management"],
    "idiomas": ["Spanish (native)", "English (C2)"],
}

_GOOD_RESPONSE = """\
<CV>
LORENA RUIZ

Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884  |  www.linkedin.com/in/lilianlorenaruiz

PROFESSIONAL PROFILE
Trade Marketing and Category Management professional with 14 years of experience.

WORK EXPERIENCE

Alcalisa S.A.
National Marketing Manager
2013 – 2018
- Grew market share from 12% to 18% in Ecuador spirits segment through category management.
- Led trade marketing activations across Supermaxi, Coral, Tía, and Santa María.

EDUCATION

Diploma in AI and Community Management
Aug 2023 – Nov 2023
Universidad del Valle, Cali, Colombia

Advanced Certificate in Retail and Trade Marketing
2017 – 2017
EDES Business School, Retail Institute Spain and Latam, Quito, Ecuador

Master's in Marketing and Commercial Management
2011 – 2012
Real Centro Universitario Maria Cristina, Escuela Europea

Bachelor's in Social Communication and Journalism
2005 – 2011
Universidad del Valle, Cali, Colombia

SKILLS
- Trade Marketing, Category Management
- Power BI, Excel avanzado

LANGUAGES
Spanish (native)  |  English C2 Proficient (EF SET certified)
</CV>
<ATS_SCORE>96</ATS_SCORE>
<KEYWORDS>Category Manager, gestión de categorías, trade marketing, liderazgo</KEYWORDS>
"""

_EVIDENCE_MAP_WITH_TIER1 = {
    "gestión de categorías": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Grew market share from 12% to 18% in Ecuador spirits segment."}],
    },
    "trade marketing": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Led trade marketing activations across Supermaxi, Coral, Tía."}],
    },
    "liderazgo de equipos": {
        "tier": 1,
        "evidencia": [{"rol": "Alcalisa S.A.", "bullet": "Trained 150+ people per year: distributors and HORECA staff."}],
    },
    "gestión de inventario WMS": {"tier": 3, "evidencia": []},
}

_POOR_FIT_MAP = {f"skill_{i}": {"tier": 3, "evidencia": []} for i in range(6)}


def _mock_claude(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


# ── Tests: _SYSTEM no tiene reglas problemáticas ──────────────────────────────

class TestSystemPromptRules:
    def test_rule7_keyword_injection_removed(self):
        """Regla 7 original 'Inject keywords from the job description' debe estar eliminada."""
        from agents.cv_rewriter import _SYSTEM
        assert "Inject keywords from the job description" not in _SYSTEM, (
            "Regla 7 de keyword injection sigue en _SYSTEM — debe eliminarse."
        )

    def test_rule10_mirror_title_removed(self):
        """Regla 10 original 'Mirror the exact job-title language' debe estar eliminada."""
        from agents.cv_rewriter import _SYSTEM
        assert "Mirror the exact job-title language" not in _SYSTEM, (
            "Regla 10 de mirror title sigue en _SYSTEM — debe eliminarse."
        )

    def test_evidence_map_instruction_present(self):
        """_SYSTEM debe instruir a usar SOLO el EVIDENCE MAP."""
        from agents.cv_rewriter import _SYSTEM
        assert "EVIDENCE MAP" in _SYSTEM, (
            "_SYSTEM no menciona EVIDENCE MAP — la instrucción de evidencia falta."
        )

    def test_no_keyword_density_pressure(self):
        """La nota de retry 'Increase keyword density' debe estar eliminada."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        evidence_map = _EVIDENCE_MAP_WITH_TIER1
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=80,
                          evidence_map=evidence_map, auditor_feedback="")
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "Increase keyword density" not in user_content, (
            "El retry sigue usando 'Increase keyword density' — debe eliminarse."
        )


# ── Tests: evidence_map llega al prompt de Claude ─────────────────────────────

class TestEvidenceMapInPrompt:
    def test_evidence_map_tiers_in_prompt(self):
        """El prompt enviado a Claude debe incluir el EVIDENCE MAP con los tiers."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=None,
                          evidence_map=_EVIDENCE_MAP_WITH_TIER1, auditor_feedback="")
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "EVIDENCE MAP" in user_content, "EVIDENCE MAP no está en el prompt enviado a Claude"
        assert "gestión de categorías" in user_content, "Skills del mapa no llegan al prompt"
        assert "Tier 1" in user_content or "[1]" in user_content, "Tiers no están en el prompt"

    def test_tier3_labeled_as_omit_in_prompt(self):
        """Los skills Tier 3 deben aparecer marcados para omitir en el prompt."""
        from agents.cv_rewriter import _rewrite_once, _cv_to_plain_text
        client = _mock_claude(_GOOD_RESPONSE)
        cv_plain = _cv_to_plain_text(_CV_DICT, rama="B")
        with patch("agents.cv_rewriter._get_client", return_value=client):
            _rewrite_once(cv_plain, _JOB, previous_score=None,
                          evidence_map=_EVIDENCE_MAP_WITH_TIER1, auditor_feedback="")
        call_kwargs = client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "gestión de inventario WMS" in user_content, "Skill Tier 3 no llega al prompt"
        assert "omit" in user_content.lower() or "ausente" in user_content.lower() or "Tier 3" in user_content, (
            "Skill Tier 3 no está marcado como omitir en el prompt"
        )


# ── Tests: poor_fit flag ──────────────────────────────────────────────────────

class TestPoorFitFlag:
    def test_poor_fit_flagged_when_many_tier3(self):
        """rewrite() debe retornar poor_fit=True cuando hay más de 5 Tier 3."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_POOR_FIT_MAP),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert result.get("poor_fit") is True, (
            f"poor_fit debería ser True con 6 skills Tier 3, got: {result.get('poor_fit')}"
        )

    def test_poor_fit_false_when_few_tier3(self):
        """rewrite() no debe flagear poor_fit cuando hay pocos Tier 3."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_EVIDENCE_MAP_WITH_TIER1),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert result.get("poor_fit") is not True, (
            f"poor_fit no debería ser True con solo 1 Tier 3, got: {result.get('poor_fit')}"
        )

    def test_rewrite_result_has_poor_fit_key(self):
        """rewrite() siempre retorna la clave 'poor_fit' en el resultado."""
        from agents.cv_rewriter import rewrite
        client = _mock_claude(_GOOD_RESPONSE)
        with (
            patch("agents.cv_rewriter._get_client", return_value=client),
            patch("agents.cv_rewriter._enrich_with_narratives", side_effect=lambda t, r: t),
            patch("agents.cv_rewriter.build_evidence_map", return_value=_EVIDENCE_MAP_WITH_TIER1),
        ):
            result = rewrite(_CV_DICT, _JOB, rama="B")
        assert "poor_fit" in result, "La clave 'poor_fit' falta en el resultado de rewrite()"
```

- [ ] Verificar que los tests fallan:

```
python -m pytest tests/test_evidence_rewriter.py -v
```

Expected: varios FAILED (reglas aún existen en _SYSTEM, evidence_map no llega al prompt, poor_fit no existe)

---

### Step 2.2 — Modificar `agents/cv_rewriter.py`

- [ ] **Agregar import** al inicio de cv_rewriter.py (después de `from agents.narrative_builder import get_bullets_for_cv`):

```python
from agents.evidence_mapper import build_evidence_map, verify_evidence, POOR_FIT_THRESHOLD
```

- [ ] **Agregar función** `_format_evidence_map_for_prompt` antes de `_rewrite_once`:

```python
def _format_evidence_map_for_prompt(evidence_map: dict) -> str:
    """
    Convierte el evidence_map en texto para incluir en el prompt de Claude.
    Tier 1: narrativa completa. Tier 2: exposición. Tier 3: omitir del CV.
    """
    lines = ["EVIDENCE MAP (fuente de verdad — redactar SOLO con esto):"]
    for skill, data in evidence_map.items():
        tier = data["tier"]
        evidencia = data.get("evidencia", [])
        if tier == 1:
            ev_text = " | ".join(
                f"{e['rol']} → {e['bullet'][:100]}" for e in evidencia
            )
            lines.append(f"[Tier 1] {skill}: {ev_text}")
        elif tier == 2:
            ev_text = " | ".join(
                f"{e['rol']} → {e['bullet'][:100]}" for e in evidencia
            )
            lines.append(f"[Tier 2 — exposición] {skill}: {ev_text}")
        else:
            lines.append(f"[Tier 3 — omitir del CV] {skill}")
    return "\n".join(lines)
```

- [ ] **Reemplazar Regla 7** en `_SYSTEM` (línea ~358):

Texto actual:
```
7. Inject keywords from the job description naturally into bullet points and the profile section.
```

Reemplazar por:
```
7. Redacta cada skill usando exactamente los hechos listados en su fila del EVIDENCE MAP — ningún dato adicional. No busques ni inventes evidencia fuera del mapa. Tier 1: narrativa de transferencia completa con verbo activo, contexto y resultado. Tier 2: lenguaje de exposición ("en contexto de", "a través de", "con exposición a"). Skill con [Tier 3 — omitir del CV]: no lo menciones en el CV bajo ningún concepto.
```

- [ ] **Reemplazar Regla 10** en `_SYSTEM` (línea ~361):

Texto actual:
```
10. Mirror the exact job-title language from the job description in the profile headline.
```

Reemplazar por:
```
10. El headline del PROFESSIONAL PROFILE describe el perfil real de la candidata adaptado al área del cargo — no copia el título exacto del JD. Ejemplo correcto: si el JD es "Category Manager Vestuario", el headline puede ser "Trade Marketing and Category Management Professional | Retail | Ecuador & Colombia".
```

- [ ] **Modificar `_rewrite_once`** para aceptar `evidence_map` e incluirlo en el prompt:

Firma actual:
```python
def _rewrite_once(
    cv_plain: str,
    job: dict,
    previous_score: int | None,
    auditor_feedback: str = "",
) -> dict:
```

Nueva firma y bloque de retry_note (reemplazar el bloque completo del retry_note):
```python
def _rewrite_once(
    cv_plain: str,
    job: dict,
    previous_score: int | None,
    evidence_map: dict | None = None,
    auditor_feedback: str = "",
) -> dict:
    retry_note = ""
    if previous_score is not None:
        retry_note = (
            f"\n\nPREVIOUS ATTEMPT SCORED {previous_score}% — NOT ENOUGH. "
            "Reformulate the Tier 1 evidence descriptions with more keywords from the JD. "
            "Do NOT add any claim not present in the EVIDENCE MAP."
        )

    evidence_section = ""
    if evidence_map:
        evidence_section = "\n\n" + _format_evidence_map_for_prompt(evidence_map)

    audit_note = ""
    if auditor_feedback:
        audit_note = f"\n\nINDEPENDENT AUDITOR FEEDBACK (address ALL points):\n{auditor_feedback}"

    user = (
        f"JOB TITLE: {job.get('cargo', '')}\n"
        f"COMPANY: {job.get('empresa', '')}\n"
        f"MODALITY: {job.get('modalidad', '')} | LOCATION: {job.get('ubicacion', '')}\n\n"
        f"JOB DESCRIPTION:\n{job.get('descripcion', '')[:3000]}\n\n"
        f"ORIGINAL CV:\n{cv_plain}"
        f"{evidence_section}"
        f"{retry_note}"
        f"{audit_note}"
    )
    # ... resto del método sin cambios
```

- [ ] **Modificar `rewrite()`** — agregar llamada al mapper y nuevo retry logic:

Reemplazar el cuerpo de la función `rewrite()` completo:

```python
def rewrite(
    cv: dict,
    job: dict,
    rama: str,
    auditor_feedback: str = "",
    previous_cv_text: str = "",
) -> dict:
    """
    Reescribe el CV optimizado para ATS usando evidence mapping.
    Hasta MAX_ATTEMPTS si score < 95 y no es poor fit.

    Returns:
        {
            "cv_text":        str,
            "ats_score":      int,
            "keywords_added": list,
            "attempts":       int,
            "passed_ats":     bool,
            "poor_fit":       bool,   # True si JD tiene > POOR_FIT_THRESHOLD skills Tier 3
            "poor_fit_reason": str,   # descripción del gap (solo si poor_fit=True)
        }
    """
    import json

    # Cargar narrativas
    narrativas_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "narrativas", "narrativas_lorena.json",
    )
    narrativas = {}
    try:
        with open(narrativas_path, encoding="utf-8") as f:
            narrativas = json.load(f)
    except Exception as e:
        print(f"[CVRewriter] narrativas no disponibles: {e}")

    # Construir evidence map
    evidence_map = {}
    if job.get("descripcion") and narrativas:
        try:
            evidence_map = build_evidence_map(job["descripcion"], narrativas)
            tier3_count = sum(1 for v in evidence_map.values() if v["tier"] == 3)
            print(f"[CVRewriter] Evidence map: {len(evidence_map)} skills — "
                  f"{sum(1 for v in evidence_map.values() if v['tier']==1)} T1, "
                  f"{sum(1 for v in evidence_map.values() if v['tier']==2)} T2, "
                  f"{tier3_count} T3")
            # Poor fit check
            if tier3_count > POOR_FIT_THRESHOLD:
                print(f"[CVRewriter] POOR FIT: {tier3_count} skills sin evidencia — aplicando sin retry")
                # Hacer un intento único y retornar con flag
                is_carry = bool(previous_cv_text)
                cv_plain = previous_cv_text if is_carry else _cv_to_plain_text(cv, rama)
                cv_enriched = cv_plain if is_carry else _enrich_with_narratives(cv_plain, rama)
                result = _rewrite_once(cv_enriched, job, None, evidence_map=evidence_map,
                                       auditor_feedback=auditor_feedback)
                result["attempts"] = 1
                result["passed_ats"] = result["ats_score"] >= config.THRESHOLD_ATS
                result["poor_fit"] = True
                result["poor_fit_reason"] = f"{tier3_count} skills del JD sin evidencia en narrativas"
                return result
        except Exception as e:
            print(f"[CVRewriter] evidence_mapper error: {e} — continuando sin mapa")

    is_carry_forward = bool(previous_cv_text)
    cv_plain    = previous_cv_text if is_carry_forward else _cv_to_plain_text(cv, rama)
    cv_enriched = cv_plain if is_carry_forward else _enrich_with_narratives(cv_plain, rama)
    result      = None
    prev        = None
    max_attempts = 1 if is_carry_forward else MAX_ATTEMPTS

    for attempt in range(1, max_attempts + 1):
        print(f"[CVRewriter] Intento {attempt}/{max_attempts} — {job['cargo']} @ {job['empresa']}")
        source = cv_enriched if attempt == 1 else cv_plain
        fb     = auditor_feedback if attempt == 1 else ""
        result = _rewrite_once(source, job, prev, evidence_map=evidence_map, auditor_feedback=fb)
        score  = result["ats_score"]
        print(f"[CVRewriter] Score ATS: {score}%")

        if score >= config.THRESHOLD_ATS:
            # Check for missing Tier 1 evidence
            if evidence_map:
                missing = verify_evidence(result["cv_text"], evidence_map)
                if missing and attempt < max_attempts:
                    print(f"[CVRewriter] Tier 1 faltante: {missing} — reintentando")
                    fb = ("EVIDENCE GAP: The following Tier 1 evidence is missing from the CV — "
                          "include it explicitly: " + "; ".join(missing))
                    result = _rewrite_once(cv_enriched, job, prev,
                                           evidence_map=evidence_map, auditor_feedback=fb)
            break

        prev     = score
        cv_plain = result["cv_text"]

    result["attempts"]    = attempt
    result["passed_ats"]  = result["ats_score"] >= config.THRESHOLD_ATS
    result["poor_fit"]    = False
    result["poor_fit_reason"] = ""
    return result
```

### Step 2.3 — Correr tests

- [ ] Ejecutar:

```
python -m pytest tests/test_evidence_rewriter.py -v
```

Expected: todos PASSED

- [ ] Verificar que los tests anteriores siguen pasando:

```
python -m pytest tests/test_cv_rewriter.py tests/test_cv_rewriter_unit.py -v
```

Expected: todos PASSED (no hay regresiones)

### Step 2.4 — Commit

- [ ] Commitear:

```bash
git add agents/cv_rewriter.py tests/test_evidence_rewriter.py
git commit -m "feat: cv_rewriter usa evidence_map — elimina keyword injection, agrega poor_fit flag"
```

---

## Task 3: Modificar `agents/ats_auditor.py`

**Files:**
- Modify: `agents/ats_auditor.py`

El único cambio en el auditor es agregar `tier3_skills_count` y `claims_sin_evidencia` al output de `audit()`. Estos campos son opcionales — el auditor los computa si recibe `evidence_map`, de lo contrario retorna 0 y [].

### Step 3.1 — Modificar firma de `audit()` y su output

- [ ] Modificar `ats_auditor.py` — nueva firma:

```python
def audit(job: dict, cv_text: str, evidence_map: dict | None = None) -> dict:
    """
    Audita el CV reescrito contra la oferta específica.

    Args:
        job:          dict con cargo, empresa, descripcion, modalidad, ubicacion
        cv_text:      texto plano del CV ya reescrito
        evidence_map: (opcional) evidence_map de evidence_mapper — si se provee,
                      agrega tier3_skills_count y claims_sin_evidencia al output

    Returns:
        dict con audit_score, verdict, keywords_missing, weak_points,
             feedback_to_rewriter, passed_audit,
             tier3_skills_count (int), claims_sin_evidencia (list)
    """
```

- [ ] Al final de `audit()`, reemplazar el `return` final:

```python
    # Evidence fields — populated if evidence_map provided
    tier3_count = 0
    claims_sin_evidencia = []
    if evidence_map:
        from agents.evidence_mapper import verify_evidence
        tier3_count = sum(1 for v in evidence_map.values() if v["tier"] == 3)
        claims_sin_evidencia = verify_evidence(cv_text, evidence_map)

    return {
        "audit_score":           audit_score,
        "verdict":               verdict,
        "keywords_missing":      keywords_missing,
        "weak_points":           weak_points,
        "feedback_to_rewriter":  feedback_to_rewriter,
        "passed_audit":          verdict in ("PASS", "CONDITIONAL"),
        "tier3_skills_count":    tier3_count,
        "claims_sin_evidencia":  claims_sin_evidencia,
    }
```

### Step 3.2 — Verificar que los tests del auditor siguen pasando

- [ ] Ejecutar:

```
python -m pytest tests/test_ats_auditor.py -v
```

Expected: todos PASSED (los campos nuevos son opcionales, backward compatible)

### Step 3.3 — Commit

- [ ] Commitear:

```bash
git add agents/ats_auditor.py
git commit -m "feat: ats_auditor agrega tier3_skills_count y claims_sin_evidencia al output"
```

---

## Task 4: Auditoría de las 25 reglas de `_SYSTEM`

Revisar cada regla del `_SYSTEM` contra el principio de evidencia. Las reglas 7 y 10 ya se cambiaron en Task 2. Auditar el resto.

### Step 4.1 — Revisar reglas restantes

- [ ] Leer `_SYSTEM` en `agents/cv_rewriter.py` y verificar regla por regla:

| Regla | ¿Empuja hacia elaboración fuera de evidencia? | Acción |
|---|---|---|
| 1–6 (accuracy, market) | No — son restricciones de veracidad | Sin cambios |
| 7 (nuevo) | No — ya apunta al EVIDENCE MAP | Sin cambios |
| 8 (reorder bullets by relevance) | No | Sin cambios |
| 9 (keep role order) | No | Sin cambios |
| 10 (nuevo) | No — ya apunta a perfil real | Sin cambios |
| 11 (idioma del JD) | No | Sin cambios |
| 12–18 (formato) | No | Sin cambios |
| 19 (tono activo) | No | Sin cambios |
| 20–23 (longitud) | No | Sin cambios |
| 24 (section headers) | No | Sin cambios |
| 25 (formato educación) | No | Sin cambios |

- [ ] Si alguna regla empuja hacia elaboración, agregarla aquí y modificarla. Si ninguna, documentar que la auditoría no encontró issues adicionales.

### Step 4.2 — Commit si hubo cambios

- [ ] Si hubo cambios en reglas adicionales:

```bash
git add agents/cv_rewriter.py
git commit -m "fix: cv_rewriter _SYSTEM audit — eliminar reglas que empujan fuera de evidence"
```

---

## Task 5: Suite de tests completa

### Step 5.1 — Correr los 267 tests + nuevos

- [ ] Ejecutar suite completa:

```
python -m pytest -q
```

Expected:
```
... passed in Xs
```

El número total debe ser ≥ 267 + tests nuevos de evidence_mapper y evidence_rewriter.

Si algún test falla, corregir antes de continuar.

### Step 5.2 — Commit final

- [ ] Commitear si hubo ajustes:

```bash
git add -A
git commit -m "test: suite completa pasa con evidence mapper integrado"
```

---

## Verificación final

Antes de dar por completado el plan, verificar manualmente:

- [ ] `python -c "from agents.evidence_mapper import build_evidence_map; print('OK')"` — sin error
- [ ] `python -c "from agents.cv_rewriter import rewrite; print('OK')"` — sin error
- [ ] `python -c "from agents.ats_auditor import audit; print('OK')"` — sin error
- [ ] `python -m pytest -q` → todos los tests pasan

---

## Notas para el próximo plan (Plan 2 — Skill Matcher)

El campo `poor_fit=True` que produce `rewrite()` es el input que necesita `skill_matcher.py` para calibrar su threshold. Si consistentemente los cargos con X características producen `poor_fit`, el matcher debe filtrarlos antes de llegar al rewriter.

Ese scope es un plan separado — no parte de este.
