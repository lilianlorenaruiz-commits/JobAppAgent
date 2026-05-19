"""
Evidence Mapper — pre-proceso para cv_rewriter.

Dado un JD y narrativas_lorena.json, produce un evidence_map:
  {skill: {"tier": 1|2|3, "evidencia": [{"rol": str, "bullet": str}]}}

Tier 1: Lorena es sujeto activo (C1) + contexto específico (C2) + actividad transferible (C3)
Tier 2: C2+C3 sin C1 — exposición periférica (consultora, soporte, adyacente)
Tier 3: sin match — evidencia=[] — aparece en mapa para que retry loop cuente poor fit

Constante de configuración:
  POOR_FIT_THRESHOLD = 5  — si hay más de 5 Tier 3, flag poor_fit en cv_rewriter
"""
import os
import sys
import json

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

POOR_FIT_THRESHOLD = 5

_DEFAULT_NARRATIVAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "narrativas", "narrativas_lorena.json",
)


def load_narrativas(path: str | None = None) -> dict:
    """
    Carga narrativas_lorena.json. Retorna {} si el archivo no existe o hay error.

    Args:
        path: Ruta al archivo JSON. Si None, usa _DEFAULT_NARRATIVAS_PATH.
    """
    target = path or _DEFAULT_NARRATIVAS_PATH
    try:
        with open(target, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[EvidenceMapper] narrativas no disponibles ({target}): {e}")
        return {}


_client: anthropic.Anthropic | None = None

# Verbos de acción propios que indican que Lorena es sujeto activo (C1 = True)
_ACTIVE_VERBS = {
    "managed", "led", "implemented", "grew", "achieved", "designed",
    "reduced", "increased", "exceeded", "secured", "trained", "built",
    "created", "developed", "delivered", "launched", "generated",
    "optimized", "transformed", "coordinated", "directed", "executed",
    "handled", "oversaw", "drove", "spearheaded", "established",
    "deployed", "negotiated", "closed", "produced", "conducted",
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
    Cubre: roles[].logros, plataformas[].logro_destacado,
           liderazgo, trade_retail, brand_strategy.
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
    False si empieza con verbo de soporte ("supported", "participated", etc.)
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

    Tier 3 → evidencia=[] — skill sin match en narrativas.
    Aparece en el mapa para que el retry loop cuente poor fit.
    """
    all_bullets = _flatten_narrativas(narrativas)

    if not all_bullets:
        # Sin narrativas, no hay evidencia posible — extraer skills y marcar todo Tier 3
        skills = _extract_jd_skills(job_description) if job_description.strip() else []
        return {skill: {"tier": 3, "evidencia": []} for skill in skills}

    skills = _extract_jd_skills(job_description)
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
