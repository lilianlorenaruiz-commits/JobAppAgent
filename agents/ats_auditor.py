"""
ATS Auditor — Agente 4b  (devil's advocate)
Evaluador independiente que actúa como reclutador hostil.
Cross-referencia la oferta EXACTA contra el CV reescrito PARA esa oferta.
No sabe el score que el rewriter se dio a sí mismo → elimina sesgo de auto-evaluación.

Flujo:
  cv_rewriter → ats_auditor → [PASS → pdf_generator]
                             → [FAIL/CONDITIONAL → feedback al rewriter → siguiente intento]

Input:
  job      (dict) — oferta original del scraper (cargo, empresa, descripcion, …)
  cv_text  (str)  — CV reescrito por cv_rewriter para ESA oferta específica

Output:
  {
    "audit_score":         int,          # 0-100
    "verdict":             str,          # "PASS" | "CONDITIONAL" | "FAIL"
    "keywords_missing":    list[str],    # keywords exactas de la oferta ausentes en el CV
    "weak_points":         list[str],    # afirmaciones sin evidencia concreta
    "feedback_to_rewriter": str,         # instrucciones concretas para la próxima iteración
    "passed_audit":        bool,
  }
"""
import os
import re
import sys

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

MAX_AUDIT_CYCLES = 4   # tras este límite se escala por Telegram

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key or key.startswith("PEGA_AQUI"):
            raise RuntimeError("API key de Anthropic no configurada.")
        _client = anthropic.Anthropic(api_key=key)
    return _client


_SYSTEM = """\
You are a hostile senior recruiter with 25 years of experience. You have seen thousands \
of inflated, keyword-stuffed CVs. Your job is to find every reason to reject this CV \
before it reaches the hiring manager. You are ruthless, sceptical, and unconvinced by \
generic language.

CRITICAL RULE — CROSS-REFERENCE:
You receive two paired inputs:
  1. JOB_OFFER — the EXACT job posting this CV was written for
  2. CV_TEXT   — the CV rewritten SPECIFICALLY for that job posting

You evaluate CV_TEXT ONLY against JOB_OFFER. You never mix offers or CVs from other roles.

EVALUATE in this exact order:
1. Exact keyword match — are the LITERAL words from the job title and description present \
in the CV? Synonyms do NOT count unless the offer itself uses them.
2. Quantified evidence — does every achievement claim include a real number (%, revenue, \
team size, timeframe)? Vague superlatives are automatic red flags.
3. Chronological coherence — are there unexplained gaps, overlaps, or suspiciously brief tenures?
4. Profile relevance — does the headline MIRROR the exact job title language from this offer?
5. Filler language — flag phrases that contain zero verifiable information \
("dynamic professional", "results-oriented", "passionate about…").

SCORING:
  PASS         → AUDIT_SCORE >= 90
  CONDITIONAL  → AUDIT_SCORE 80–89
  FAIL         → AUDIT_SCORE < 80

OUTPUT — use ONLY these delimiters, nothing else:
<AUDIT_SCORE>[integer 0-100]</AUDIT_SCORE>
<VERDICT>PASS|CONDITIONAL|FAIL</VERDICT>
<KEYWORDS_MISSING>[exact keywords from JOB_OFFER absent in CV, comma-separated]</KEYWORDS_MISSING>
<WEAK_POINTS>[list of specific claims the recruiter would challenge, one per line]</WEAK_POINTS>
<FEEDBACK_TO_REWRITER>[concrete paragraph-level instructions referencing exact CV text \
and exact offer terms — what to fix, where, and how]</FEEDBACK_TO_REWRITER>\
"""


def audit(job: dict, cv_text: str, evidence_map: dict | None = None) -> dict:
    """
    Audita el CV reescrito contra la oferta específica.

    Args:
        job:          dict con cargo, empresa, descripcion, modalidad, ubicacion
        cv_text:      texto plano del CV ya reescrito por cv_rewriter para este job
        evidence_map: (opcional) evidence_map de evidence_mapper — si se provee,
                      agrega tier3_skills_count y claims_sin_evidencia al output

    Returns:
        dict con audit_score, verdict, keywords_missing, weak_points,
             feedback_to_rewriter, passed_audit,
             tier3_skills_count (int), claims_sin_evidencia (list)
    """
    from datetime import date as _date
    today = _date.today().strftime("%B %d, %Y")
    user = (
        f"TODAY'S DATE: {today} — use this to evaluate whether employment dates are past, present, or future.\n\n"
        f"JOB_OFFER\n"
        f"Title: {job.get('cargo', '')}\n"
        f"Company: {job.get('empresa', '')}\n"
        f"Modality: {job.get('modalidad', '')} | Location: {job.get('ubicacion', '')}\n"
        f"Description:\n{job.get('descripcion', '')[:3000]}\n\n"
        f"CV_TEXT\n{cv_text}"
    )

    response = _get_client().messages.create(
        model=config.MODEL_MAIN,   # Sonnet — necesita razonamiento consistente para auditar
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

    score_m   = re.search(r"<AUDIT_SCORE>\s*(\d+)\s*</AUDIT_SCORE>",          raw)
    verdict_m = re.search(r"<VERDICT>\s*(PASS|CONDITIONAL|FAIL)\s*</VERDICT>", raw)
    kw_m      = re.search(r"<KEYWORDS_MISSING>\s*(.*?)\s*</KEYWORDS_MISSING>", raw, re.DOTALL)
    wp_m      = re.search(r"<WEAK_POINTS>\s*(.*?)\s*</WEAK_POINTS>",           raw, re.DOTALL)
    fb_m      = re.search(r"<FEEDBACK_TO_REWRITER>\s*(.*?)\s*</FEEDBACK_TO_REWRITER>", raw, re.DOTALL)

    audit_score = int(score_m.group(1)) if score_m else 0
    verdict     = verdict_m.group(1)    if verdict_m else ("PASS" if audit_score >= 90 else
                                                            "CONDITIONAL" if audit_score >= 80 else "FAIL")

    keywords_missing    = [k.strip() for k in kw_m.group(1).split(",") if k.strip()] if kw_m else []
    weak_points         = [l.strip() for l in wp_m.group(1).splitlines() if l.strip()] if wp_m else []
    feedback_to_rewriter = fb_m.group(1).strip() if fb_m else ""

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


# ── Test directo ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from agents.cv_parser   import parse_cv
    from agents.cv_rewriter import rewrite

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

    rw = rewrite(cv, test_job, "A")
    print(f"\n[Rewriter] Score auto: {rw['ats_score']}% | Intentos: {rw['attempts']}")

    result = audit(test_job, rw["cv_text"])
    print(f"\n[Auditor] Score: {result['audit_score']}% | Verdict: {result['verdict']}")
    print(f"Keywords missing: {result['keywords_missing']}")
    print(f"Weak points:\n  " + "\n  ".join(result["weak_points"]))
    print(f"\nFeedback to rewriter:\n{result['feedback_to_rewriter']}")
