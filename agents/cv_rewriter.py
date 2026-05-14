"""
CV Rewriter — Agente 4
Reescribe el CV de Lorena optimizado para ATS del cargo específico.
Usa Claude Sonnet con hasta MAX_ATTEMPTS intentos hasta alcanzar ATS >= 95%.

Técnicas aplicadas:
  - Keyword injection desde la descripción del cargo
  - Reordenamiento de bullets por relevancia
  - Formato ATS-friendly (sin tablas, sin columnas, sin gráficos)
  - Logros cuantificados adaptados al rol

Input:  cv (dict de cv_parser), job (dict), rama (str)
Output: {"cv_text", "ats_score", "keywords_added", "attempts", "passed_ats"}
"""
import os
import re
import sys
from datetime import date

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from agents.cv_parser import parse_cv
from agents.narrative_builder import get_bullets_for_cv

MAX_ATTEMPTS = 3
_client: anthropic.Anthropic | None = None


# ── Cliente ────────────────────────────────────────────────────────────────────

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key or key.startswith("PEGA_AQUI"):
            raise RuntimeError("API key de Anthropic no configurada.")
        _client = anthropic.Anthropic(api_key=key)
    return _client


# ── Convertir dict CV → texto plano ───────────────────────────────────────────

def _years_of_experience(cv: dict) -> int:
    """Compute years of experience from the earliest role in cv['experiencia']."""
    earliest = date.today().year
    for exp in cv.get("experiencia", []):
        fecha = exp.get("fecha", "")
        m = re.search(r"\b(19|20)(\d{2})\b", fecha)
        if m:
            yr = int(m.group(0))
            if yr < earliest:
                earliest = yr
    return date.today().year - earliest


_PROFILE_BY_RAMA = {
    "A": (
        "Senior Marketing and Brand Strategy Consultant with {yoe}+ years of experience in "
        "brand strategy, commercial management, 360° campaigns, and B2B/B2C market positioning. "
        "Track record of P&L ownership, C-suite presentations, and digital transformation "
        "initiatives across consumer goods, spirits, and technology sectors. "
        "Fully bilingual Spanish/English (C2 Proficient, EF SET certified)."
    ),
    "B": (
        "Trade Marketing and Retail Activation professional with {yoe}+ years of experience in "
        "category management, shopper marketing, distributor management, and retail sell-out "
        "strategy across FMCG and spirits verticals. "
        "Proven record of market share growth, point-of-sale activation ROI, and category P&L. "
        "Fully bilingual Spanish/English (C2 Proficient, EF SET certified)."
    ),
    "C": (
        "Performance Marketing professional with {yoe}+ years in marketing and digital strategy, "
        "including hands-on paid media campaign management across Google Ads, Meta Ads "
        "(Facebook and Instagram), Amazon Ads (Sponsored Products, Sponsored Brands, DSP), "
        "and LinkedIn Ads since 2025. "
        "Expertise in ROAS and ACOS optimization, programmatic advertising, and data analysis "
        "of CTR, CPC, DPV, NTB Sales metrics. "
        "Experience coordinating with global and APAC teams in English. "
        "Amazon Seller Central, Vendor Central, and AMC practitioner. "
        "Fully bilingual Spanish/English (C2 Proficient, EF SET certified)."
    ),
}


def _normalize_fecha(fecha: str) -> str:
    """Normaliza variantes de 'en curso' a 'Present' para consistencia."""
    return re.sub(
        r"\b(current\s*working|current|actual|presente|en\s+curso|a\s+la\s+fecha)\b",
        "Present",
        fecha,
        flags=re.IGNORECASE,
    ).strip()


def _cv_to_plain_text(cv: dict, rama: str = "A") -> str:
    yoe = _years_of_experience(cv)
    profile_template = _PROFILE_BY_RAMA.get(rama.upper(), _PROFILE_BY_RAMA["A"])
    profile = profile_template.format(yoe=yoe)
    lines = [
        "LORENA RUIZ",
        "",
        "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884",
        "",
        "PROFESSIONAL PROFILE",
        profile,
        "",
        "WORK EXPERIENCE",
    ]

    # Most recent role (not yet in PDF source — added Feb 2026)
    # MARKET BOUNDARY: this role covers Latin America ONLY.
    # APAC market coverage belongs exclusively to the Amazon Campaign Planner role.
    lines += [
        "",
        "Paid Media Specialist / Account Manager — LinkedIn Ads (via Teleperformance for LinkedIn Marketing Solutions)",
        "Teleperformance (contract for LinkedIn Marketing Solutions)",
        "February 2026 – Present  |  Bogotá, Hybrid",
        (
            "Manage and optimize LinkedIn Ads campaigns for 300+ B2B enterprise accounts across "
            "Latin America, executing Sponsored Content, Lead Gen Forms, and Website Conversion "
            "objectives. Monthly managed portfolio: USD 240,000. Conduct weekly performance reviews "
            "and deliver optimization recommendations in English to Global Account Executives "
            "based in Singapore, Sydney, and Tokyo. Market scope: Latin America only."
        ),
    ]

    for exp in cv.get("experiencia", []):
        lines.append("")
        lines.append(exp["cargo"])
        if exp.get("empresa"):
            lines.append(exp["empresa"])
        fecha = _normalize_fecha(exp.get("fecha", ""))
        lines.append(fecha)
        if exp.get("descripcion"):
            lines.append(exp["descripcion"])

    lines += ["", "EDUCATION"]
    for edu in cv.get("educacion", []):
        lines.append("")
        lines.append(edu["titulo"])
        inst = edu.get("institucion", "")
        lugar = edu.get("lugar", "")
        lines.append(f"{inst} — {lugar}".strip(" —"))

    lines += ["", "SKILLS", ", ".join(cv.get("skills", []))]
    lines += ["", "LANGUAGES", "  |  ".join(cv.get("idiomas", []))]
    return "\n".join(lines)


def _enrich_with_narratives(cv_plain: str, rama: str) -> str:
    """Añade bullets ATS reales del narrative_builder como insumo para el rewriter."""
    try:
        bullets = get_bullets_for_cv(rama)
        if bullets:
            return (
                cv_plain
                + "\n\nKEY ACHIEVEMENTS & METRICS "
                "(use these EXACT numbers and data points in the rewrite — do not modify them):\n"
                + bullets
            )
    except Exception as e:
        print(f"[CVRewriter] narrative_builder no disponible: {e} — usando CV base")
    return cv_plain


# ── Una iteración de reescritura ───────────────────────────────────────────────

_SYSTEM = """\
You are a Senior Recruiter and ATS optimization expert with 20+ years of experience \
in Latin America. Rewrite the candidate's CV to maximize ATS score for the target job.

RULES:
1. Keep ALL real facts — do NOT invent experience, companies, or degrees
2. Inject job-description keywords naturally into bullet points and profile
3. Plain text only — no tables, no columns, no special characters or bullets symbols
4. Quantify achievements where the original text allows (%, numbers, revenue)
5. Reorder bullet points so the most relevant appear first
6. Mirror the exact job-title language in the profile headline
7. Write in the same language style as the original CV (bilingual Spanish/English mix)
8. NEVER attribute total company revenue or total brand sales as the candidate's personal paid media result — only attribute metrics directly tied to campaigns she managed (e.g. attributed sales from a specific DSP flight, not a company's annual revenue line)
9. Use ONE consistent English proficiency level: "C2 Proficient (EF SET certified)" — do NOT write C1, C1/C2, or any variation
10. MARKET ATTRIBUTION — each role has a fixed geographic scope; never cross-assign:
    - LinkedIn/Teleperformance role: Latin America ONLY — do NOT write "APAC" for this role
    - Amazon Campaign Planner role: APAC markets ONLY — do NOT write "Latin America" for this role
    The LinkedIn AEs based in Singapore/Sydney/Tokyo are who she reports TO, not the market she manages
11. NEVER modify employment dates — copy them exactly as provided. If a role shows "Present" keep "Present"; never infer an end date from another role's start date. Do NOT translate month names to Spanish.
12. Keep work experience roles in the EXACT order provided (most recent first). Do NOT reorder roles based on relevance — only reorder bullet points within each role.

OUTPUT FORMAT — use these exact delimiters, nothing else:
<CV>
[full rewritten CV, plain text]
</CV>
<ATS_SCORE>[integer 0-100]</ATS_SCORE>
<KEYWORDS>[comma-separated list of keywords you added]</KEYWORDS>\
"""


def _rewrite_once(
    cv_plain: str,
    job: dict,
    previous_score: int | None,
    auditor_feedback: str = "",
) -> dict:
    retry_note = ""
    if previous_score is not None:
        retry_note = (
            f"\n\nPREVIOUS ATTEMPT SCORED {previous_score}% — NOT ENOUGH. "
            "Increase keyword density and tighten alignment to reach 95%+."
        )

    audit_note = ""
    if auditor_feedback:
        audit_note = f"\n\nINDEPENDENT AUDITOR FEEDBACK (address ALL points):\n{auditor_feedback}"

    user = (
        f"JOB TITLE: {job.get('cargo', '')}\n"
        f"COMPANY: {job.get('empresa', '')}\n"
        f"MODALITY: {job.get('modalidad', '')} | LOCATION: {job.get('ubicacion', '')}\n\n"
        f"JOB DESCRIPTION:\n{job.get('descripcion', '')[:3000]}\n\n"
        f"ORIGINAL CV:\n{cv_plain}"
        f"{retry_note}"
        f"{audit_note}"
    )

    response = _get_client().messages.create(
        model=config.MODEL_MAIN,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
    )

    raw = response.content[0].text

    # Parse XML delimiters
    cv_match    = re.search(r"<CV>\s*(.*?)\s*</CV>",             raw, re.DOTALL)
    score_match = re.search(r"<ATS_SCORE>\s*(\d+)\s*</ATS_SCORE>", raw)
    kw_match    = re.search(r"<KEYWORDS>\s*(.*?)\s*</KEYWORDS>", raw, re.DOTALL)

    cv_text   = cv_match.group(1).strip()    if cv_match    else cv_plain
    ats_score = int(score_match.group(1))    if score_match else 70
    keywords  = [k.strip() for k in kw_match.group(1).split(",")] if kw_match else []

    return {"cv_text": cv_text, "ats_score": ats_score, "keywords_added": keywords}


# ── API pública ────────────────────────────────────────────────────────────────

def rewrite(
    cv: dict,
    job: dict,
    rama: str,
    auditor_feedback: str = "",
    previous_cv_text: str = "",
) -> dict:
    """
    Reescribe el CV optimizado para ATS. Hasta MAX_ATTEMPTS si score < 95.
    Si auditor_feedback no está vacío, se inyecta en el primer intento de este ciclo.
    Si previous_cv_text está presente, se usa como base en vez del CV original
    (permite construir sobre mejoras del ciclo anterior del auditor).

    Returns:
        {
            "cv_text":        str,   # CV reescrito listo para generar PDF
            "ats_score":      int,   # 0-100
            "keywords_added": list,
            "attempts":       int,
            "passed_ats":     bool,
        }
    """
    is_carry_forward = bool(previous_cv_text)
    cv_plain    = previous_cv_text if is_carry_forward else _cv_to_plain_text(cv, rama)
    cv_enriched = cv_plain if is_carry_forward else _enrich_with_narratives(cv_plain, rama)
    result      = None
    prev        = None

    # When carrying forward an already-optimized CV, one focused attempt is enough.
    # The retry loop risks degrading a CV that's already well-structured.
    max_attempts = 1 if is_carry_forward else MAX_ATTEMPTS

    for attempt in range(1, max_attempts + 1):
        print(f"[CVRewriter] Intento {attempt}/{max_attempts} — {job['cargo']} @ {job['empresa']}")
        source = cv_enriched if attempt == 1 else cv_plain
        fb     = auditor_feedback if attempt == 1 else ""
        result = _rewrite_once(source, job, prev, auditor_feedback=fb)
        score  = result["ats_score"]
        print(f"[CVRewriter] Score ATS: {score}%")

        if score >= config.THRESHOLD_ATS:
            break

        prev     = score
        cv_plain = result["cv_text"]

    result["attempts"]   = attempt
    result["passed_ats"] = result["ats_score"] >= config.THRESHOLD_ATS
    return result


if __name__ == "__main__":
    cv = parse_cv()
    test_job = {
        "cargo":       "Brand Strategist Sr.",
        "empresa":     "Grupo Exito",
        "descripcion": (
            "Buscamos Brand Strategist con experiencia en brand strategy, "
            "digital transformation y data analysis. Ingles C1 requerido. "
            "Liderazgo de equipos multidisciplinarios, gestion de presupuesto B2B/B2C. "
            "Sector consumo masivo. 5+ anos de experiencia."
        ),
        "url":       "https://linkedin.com/jobs/dry-A-001",
        "modalidad": "Hibrido",
        "ubicacion": "Bogota",
    }
    r = rewrite(cv, test_job, "A")
    print(f"\nScore: {r['ats_score']}% | Intentos: {r['attempts']} | Pasa: {r['passed_ats']}")
    print(f"Keywords: {r['keywords_added']}")
    print(f"\n--- PRIMERAS 800 CHARS DEL CV REESCRITO ---")
    print(r["cv_text"][:800])
