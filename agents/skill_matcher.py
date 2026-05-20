"""
Skill Matcher — Agente 3
Compara el CV de Lorena vs la descripción de un cargo y calcula un score 0-100.

Lógica:
  - 20 % keyword match (skills_target del perfil vs texto del CV + descripción del cargo)
  - 80 % scoring semántico vía Claude (prompt caching: el CV se cachea entre llamadas)

Input:
    cv   : dict de cv_parser.parse_cv()
    job  : {"cargo", "empresa", "descripcion", "url", "modalidad", "ubicacion"}
    rama : "A" | "B" | "C"

Output:
    {"score": int, "skills_match": list, "skills_gap": list, "passed": bool, "reason": str}
"""
import json
import os
import sys
import re

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from agents.cv_parser import parse_cv
from agents.evidence_mapper import load_narrativas

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key or key.startswith("PEGA_AQUI"):
            raise RuntimeError(
                "API key de Anthropic no configurada. "
                "Edita config/anthropic_key.txt o setea ANTHROPIC_API_KEY."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_profile(rama: str) -> dict:
    names = {
        "A": "perfil_a_consultoria.json",
        "B": "perfil_b_retail.json",
        "C": "perfil_c_paidmedia.json",
    }
    path = os.path.join(config.PROFILES_DIR, names[rama.upper()])
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cv_to_text(cv: dict, narrativas: dict | None = None) -> str:
    """Aplana el dict del CV a texto plano para matching.

    Si se proveen narrativas, suplementa con bullets verificados de
    bullets_por_rol para capturar contexto sectorial que el PDF genérico
    omite (ej: licores/spirits/HORECA en Alcalisa, artesanal en Enzalsarte).
    """
    parts = [f"Name: {cv['nombre']}"]
    for exp in cv.get("experiencia", []):
        parts.append(f"Role: {exp['cargo']} at {exp['empresa']} ({exp['fecha']})")
        if exp.get("descripcion"):
            parts.append(exp["descripcion"])
    for edu in cv.get("educacion", []):
        parts.append(f"Education: {edu['titulo']} — {edu['institucion']}")
    parts.append("Skills: " + ", ".join(cv.get("skills", [])))
    parts.append("Languages: " + ", ".join(cv.get("idiomas", [])))

    # Suplementar con bullets verificados de narrativas
    bullets_por_rol = (narrativas or {}).get("bullets_por_rol", {})
    if bullets_por_rol:
        parts.append("\n--- VERIFIED CAREER NARRATIVE ---")
        for rol_data in bullets_por_rol.values():
            if not isinstance(rol_data, dict):
                continue
            bullets = rol_data.get("bullets", [])
            if not bullets:
                continue
            empresa = rol_data.get("empresa", "")
            periodo = rol_data.get("periodo", "")
            header = f"\n[{empresa}]" + (f" — {periodo}" if periodo else "")
            parts.append(header)
            for b in bullets:
                parts.append(f"• {b}")

    return "\n".join(parts)


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


def _semantic_score(cv_text: str, job: dict) -> tuple[int, str]:
    """
    Pide a Claude un score semántico 0-100 con prompt caching en el bloque del CV.
    Retorna (score, reason).
    """
    client = _get_client()

    system_block = (
        "You are a senior recruiter with 20+ years of experience in Latin America. "
        "Your task: evaluate a candidate's suitability for a job opening and return "
        "ONLY a JSON object with keys 'score' (integer 0-100) and 'reason' (one sentence in Spanish).\n\n"
        "Score guide:\n"
        "  0-50  → poor fit, missing key requirements\n"
        "  51-70 → partial fit, transferable skills\n"
        "  71-85 → good fit, meets most requirements\n"
        "  86-100→ excellent fit, strong match\n\n"
        f"CANDIDATE CV:\n{cv_text}"
    )

    user_msg = (
        f"JOB TITLE: {job.get('cargo', '')}\n"
        f"COMPANY: {job.get('empresa', '')}\n"
        f"LOCATION: {job.get('ubicacion', '')} | MODALIDAD: {job.get('modalidad', '')}\n\n"
        f"JOB DESCRIPTION:\n{job.get('descripcion', '')[:2000]}\n\n"
        "Respond with ONLY the JSON object."
    )

    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": system_block,
                "cache_control": {"type": "ephemeral"},  # CV cached across calls
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Extract score with regex as fallback
        m = re.search(r'"score"\s*:\s*(\d+)', raw)
        score = int(m.group(1)) if m else 50
        r = re.search(r'"reason"\s*:\s*"([^"]*)', raw)
        reason = r.group(1) if r else "Score estimado por fallback."
        return score, reason
    return int(data["score"]), data.get("reason", "")


# ── API pública ────────────────────────────────────────────────────────────────

def analyze(cv: dict, job: dict, rama: str) -> dict:
    """
    Calcula el score de idoneidad entre el CV y un cargo.

    Returns:
        {
            "score":        int,    # 0-100
            "skills_match": list,   # skills_target que matchean
            "skills_gap":   list,   # skills_target que faltan
            "passed":       bool,   # score >= threshold del perfil
            "threshold":    int,
            "reason":       str,    # breve justificación del score semántico
        }
    """
    perfil = _load_profile(rama)
    narrativas = load_narrativas()
    cv_text = _cv_to_text(cv, narrativas)

    kw_score, matched, gaps = _keyword_score(
        cv_text, job.get("descripcion", ""), perfil["skills_target"]
    )
    sem_score, reason = _semantic_score(cv_text, job)

    final = round(kw_score * 0.20 + sem_score * 0.80)

    return {
        "score":        final,
        "skills_match": matched,
        "skills_gap":   gaps,
        "passed":       final >= perfil["threshold_match"],
        "threshold":    perfil["threshold_match"],
        "reason":       reason,
    }


if __name__ == "__main__":
    cv = parse_cv()
    test_job = {
        "cargo":       "Brand Strategist Sr.",
        "empresa":     "Empresa Demo S.A.S",
        "descripcion": (
            "Buscamos Brand Strategist con experiencia en transformación digital, "
            "brand strategy, data analysis y manejo de presupuestos B2B/B2C. "
            "Indispensable inglés C1, conocimiento de herramientas digitales y liderazgo. "
            "Sector consumo masivo. Modalidad híbrida en Bogotá."
        ),
        "url":       "https://linkedin.com/jobs/demo",
        "modalidad": "Híbrido",
        "ubicacion": "Bogotá",
    }
    resultado = analyze(cv, test_job, "A")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
