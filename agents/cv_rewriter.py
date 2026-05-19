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
from agents.evidence_mapper import build_evidence_map, verify_evidence, POOR_FIT_THRESHOLD

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


_CONTACT_LINE = "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884  |  www.linkedin.com/in/lilianlorenaruiz"

# Maps degree-title keywords (uppercased) to known date strings.
_EDUCATION_DATES: dict[str, str] = {
    "DIPLOMA":      "Aug 2023 – Nov 2023",
    "CERTIFICATE":  "2017",
    "MASTER":       "2011 – 2012",
    "BACHELOR":     "2005 – 2011",
}

# Ground-truth date for the Amazon role (ended Feb 2026 when LinkedIn role started).
_AMAZON_DATE = "May 2025 – Feb 2026"

# Canonical education block — injected after LLM output so it cannot be modified.
# Format per entry: title / date / institution  (3 lines, no bullets — PDF generator
# renders the first line of each group as bold automatically).
_EDUCATION_BLOCK = """EDUCATION

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
"""


def _fix_static_fields(cv_text: str) -> str:
    """
    Post-processing determinístico para campos que el LLM no debe modificar.
    Runs after LLM output; overrides hallucinated values with ground truth.
    """
    # 1. Fix contact line — replace the first email-containing line in the header area.
    #    Only look in the first 600 chars (before PROFESSIONAL PROFILE) to avoid touching
    #    bullets that mention URLs.
    head = cv_text[:600]
    tail = cv_text[600:]
    head_fixed = re.sub(
        r"[^\n]*@[^\n]*",
        _CONTACT_LINE,
        head,
        count=1,
    )
    cv_text = head_fixed + tail

    # 2. Enforce Amazon role date — always override whatever the LLM wrote.
    #    Matches any "May 2025 – <anything>" line (including "Present" if LLM hallucinates it).
    cv_text = re.sub(
        r"May\s+2025\s*[–\-]\s*[^\n]+",
        _AMAZON_DATE,
        cv_text,
    )

    # 3. Replace the entire EDUCATION section with canonical ground-truth data.
    #    The LLM may drop titles, reorder lines, or invent dates — we override all of it.
    #    Strategy: find "EDUCATION" (case-insensitive, any variant header), find the next
    #    all-caps section header after it (SKILLS, LANGUAGES, CERTIFICATIONS…), and
    #    replace everything in between with _EDUCATION_BLOCK.
    edu_start = re.search(
        r"(?im)^(EDUCATION[\w\s&]*|ACADEMIC[\w\s]+|TRAINING\s*(?:&|AND)\s*EDUCATION"
        r"|DEGREES?[\w\s&]+|ESTUDIOS?|FORMACI[OÓ]N(?:\s+ACAD[EÉ]MICA)?)[ \t]*$",
        cv_text,
    )
    if edu_start:
        # Find the next recognisable all-caps section header after the education header
        next_sec = re.search(
            r"(?m)^(SKILLS|HABILIDADES|LANGUAGES?|IDIOMAS|CERTIFICATIONS?|"
            r"ADDITIONAL\s+INFORMATION|REFERENCES?)[ \t]*$",
            cv_text[edu_start.end():],
        )
        if next_sec:
            after_edu = cv_text[edu_start.end() + next_sec.start():]
        else:
            after_edu = ""
        cv_text = cv_text[: edu_start.start()] + _EDUCATION_BLOCK + "\n" + after_edu

    # 4. Fix GRC S.A. company name — LLM sometimes drops the leading 'G'.
    #    \bRC matches only when preceded by a non-word char (newline, space),
    #    not when 'RC' appears inside 'GRC' which is already correct.
    cv_text = re.sub(r"\bRC S\.A\.", "GRC S.A.", cv_text)

    return cv_text


def _cv_to_plain_text(cv: dict, rama: str = "A") -> str:
    yoe = _years_of_experience(cv)
    profile_template = _PROFILE_BY_RAMA.get(rama.upper(), _PROFILE_BY_RAMA["A"])
    profile = profile_template.format(yoe=yoe)
    lines = [
        "LORENA RUIZ",
        "",
        "Bogotá D.C.  |  lilian@lorena-ruiz.com  |  +57 315 256 1884  |  www.linkedin.com/in/lilianlorenaruiz",
        "",
        "PROFESSIONAL PROFILE",
        profile,
        "",
        "WORK EXPERIENCE",
    ]

    # Most recent role (not yet in PDF source — added Feb 2026)
    # MARKET BOUNDARY: Latin America ONLY.
    # Global Account Executives in Singapore/Sydney/Tokyo = Amazon role. Do NOT mention them here.
    lines += [
        "",
        "Paid Media Specialist / Account Manager, LinkedIn Ads (via Teleperformance for LinkedIn Marketing Solutions)",
        "Teleperformance (contract for LinkedIn Marketing Solutions)",
        "February 2026 – Present  |  Bogotá, Hybrid",
        (
            "Manage and optimize LinkedIn Ads campaigns for 300+ B2B enterprise accounts across "
            "Latin America, executing Sponsored Content, Lead Gen Forms, and Website Conversion "
            "objectives. Monthly managed portfolio: USD 240,000. Market scope: Latin America only."
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

    # EDUCATION — hardcoded ground truth.
    # The PDF text extraction mangles education data (merged fields, encoding errors,
    # wrong splits). We bypass cv["educacion"] entirely and inject verified entries.
    # Format: degree title / date / institution+location  (3 lines per entry).
    lines += [
        "",
        "EDUCATION",
        "",
        "Diploma in AI and Community Management",
        "Aug 2023 – Nov 2023",
        "Universidad del Valle, Cali, Colombia",
        "",
        "Advanced Certificate in Retail and Trade Marketing",
        "2017",
        "EDES Business School – Retail Institute Spain & Latam, Quito, Ecuador",
        "",
        "Master's in Marketing and Commercial Management",
        "2011 – 2012",
        "Real Centro Universitario María Cristina – Escuela Europea, El Escorial, Spain",
        "",
        "Bachelor's in Social Communication and Journalism",
        "2005 – 2011",
        "Universidad del Valle, Cali, Colombia",
    ]

    lines += ["", "SKILLS", ", ".join(cv.get("skills", []))]
    lines += ["", "LANGUAGES", "  |  ".join(cv.get("idiomas", []))]
    return "\n".join(lines)


def _load_bullets_por_rol() -> dict | None:
    """Lee bullets_por_rol de narrativas_lorena.json. Retorna None si no existe."""
    import json
    narrativas_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "narrativas", "narrativas_lorena.json",
    )
    try:
        with open(narrativas_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("bullets_por_rol")
    except Exception:
        return None


def _enrich_with_narratives(cv_plain: str, rama: str) -> str:
    """
    Añade bullets por empresa como insumo para el rewriter.
    Usa bullets_por_rol (agrupados por employer) cuando está disponible — previene cross-contaminación.
    Fallback: bullets_validados planos del narrative_builder.
    """
    bpr = _load_bullets_por_rol()
    if bpr:
        lines = [
            "",
            "KEY ACHIEVEMENTS — ROLE ATTRIBUTION IS MANDATORY",
            "Each section below is labeled with the employer name.",
            "Use each bullet ONLY under the section that matches that employer in the CV.",
            "It is a critical error to move a bullet from one employer to a different employer's section.",
            "If a bullet is not listed under an employer, do NOT create it or borrow it from another section.",
            "",
        ]
        for rol_data in bpr.values():
            if isinstance(rol_data, str):
                continue
            empresa  = rol_data.get("empresa", "")
            mercado  = rol_data.get("mercado", "")
            bullets  = rol_data.get("bullets", [])
            header   = f"[{empresa}]"
            if mercado:
                header += f"  — {mercado}"
            lines.append(header)
            for b in bullets:
                lines.append(f"- {b}")
            lines.append("")
        return cv_plain + "\n".join(lines)

    # Fallback: bullets planos sin agrupación por rol
    try:
        bullets = get_bullets_for_cv(rama)
        if bullets:
            return (
                cv_plain
                + "\n\nKEY ACHIEVEMENTS AND METRICS "
                "(these are verified facts. Use ONLY these numbers. Do not modify them. "
                "Do not invent any metric, percentage, or figure that does not appear here):\n"
                + bullets
            )
    except Exception as e:
        print(f"[CVRewriter] narrative_builder no disponible: {e} — usando CV base")
    return cv_plain


# ── Evidence map → texto para prompt ──────────────────────────────────────────

def _format_evidence_map_for_prompt(evidence_map: dict) -> str:
    """
    Convierte el evidence_map en texto para incluir en el prompt de Claude.
    Tier 1: narrativa completa con evidencia.
    Tier 2: exposición — lenguaje conservador.
    Tier 3: marcado explícitamente para omitir.
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


# ── Una iteración de reescritura ───────────────────────────────────────────────

_SYSTEM = """\
You are a Senior Recruiter and ATS optimization expert with 20 years of experience \
in Latin America. Rewrite the candidate's CV to maximize the ATS score for the target job.

ACCURACY
1. Keep ALL real facts. Do NOT invent experience, companies, or degrees.
2. Quantify achievements using only data already present in the source. Use percentages, \
numbers, or revenue figures from the original. Do not fabricate metrics.
3. NEVER attribute total company revenue or total brand sales as the candidate's personal \
paid media result. Only attribute metrics directly tied to campaigns she managed.
4. NEVER modify employment dates. Copy them exactly as provided. If a role shows "Present", \
keep "Present". Never infer an end date from another role's start date. \
Do NOT translate month names to Spanish.
5. Use ONE consistent English proficiency level throughout: "C2 Proficient (EF SET certified)". \
Never write C1, C1/C2, or any variation.

MARKET ATTRIBUTION
6. Each role has a fixed geographic scope. Never cross-assign markets.
   LinkedIn/Teleperformance role: Latin America ONLY. Do NOT write "APAC" for this role.
   Amazon Campaign Planner role: APAC markets ONLY. Do NOT write "Latin America" for this role.
   Global Account Executives in Singapore, Sydney, and Tokyo belong to the Amazon role ONLY. \
Never mention them in the LinkedIn/Teleperformance section.
6b. BULLET ATTRIBUTION IS ABSOLUTE. The KEY ACHIEVEMENTS section groups verified bullets by \
employer in brackets. Each bullet must appear ONLY under the section that matches its employer. \
Never move a bullet from one employer to a different employer's section. \
Specific prohibitions:
   Bullets from [Amazon, Colombia] (tROAS, Narwal, Modelones, TCL, DSP, AMC, CPC Team Colombia, \
funnel format, Global Account Executives APAC) must ONLY appear under the Amazon Campaign Planner role.
   Bullets from [Teleperformance / LinkedIn Marketing Solutions] (300 accounts, USD 240,000 portfolio, \
ThinkOnward, Latin America) must ONLY appear under the LinkedIn/Teleperformance role.
   If a bullet is not listed under an employer, omit it. Never fabricate or borrow from another section.

CONTENT AND STRUCTURE
7. Redacta cada skill usando exactamente los hechos listados en su fila del EVIDENCE MAP — ningún dato adicional. No busques ni inventes evidencia fuera del mapa. Tier 1: narrativa de transferencia completa con verbo activo, contexto y resultado. Tier 2: lenguaje de exposición ("en contexto de", "a través de", "con exposición a"). Skill con [Tier 3 — omitir del CV]: no lo menciones bajo ningún concepto.
8. Within each role, reorder bullet points so the most relevant appear first.
9. Keep work experience roles in the EXACT order provided, most recent first. \
Do NOT reorder roles based on relevance.
10. El headline del PROFESSIONAL PROFILE describe el perfil real de la candidata adaptado al área del cargo — no copia el título exacto del JD. Ejemplo correcto: si el JD es "Category Manager Vestuario", el headline puede ser "Trade Marketing and Category Management Professional | Retail | Ecuador y Colombia".
11. Detect the primary language of the job description (job posting). If the job description is primarily in Spanish, write all bullet points and the PROFESSIONAL PROFILE section in Spanish. If it is primarily in English, write them in English. Section headers (PROFESSIONAL PROFILE, WORK EXPERIENCE, EDUCATION, SKILLS, LANGUAGES) always remain in English regardless of the job description language.

FORMATTING
12. Plain text only. No tables, no columns, no special characters beyond standard punctuation.
13. No em-dashes. Use a period or colon to connect ideas.
14. No semicolons.
15. Do NOT use the plus sign as a modifier or connector. \
Write "more than 300" instead of "300+". Write "grew 100 percent" instead of "+100%".
16. For each individual achievement or responsibility, start the line with a hyphen and a space (- ). One achievement per line. No asterisks, no special characters, no markdown of any kind beyond the hyphen bullet.
17. In the SKILLS section, write each skill on its own line starting with a hyphen and a space (- ). Group related platforms together on one line when they form a natural unit (e.g. "- Google Ads, Meta Ads y LinkedIn Ads"). Do NOT include Amazon Seller Central or Amazon Vendor Central — her Amazon experience is exclusively in paid media (Amazon Ads, DSP, AMC). One skill or skill group per line.
17. No hashtags.
18. No unnecessary adjectives. Every word must earn its place.

TONE
19. Write in an active, direct voice. Use short, informative sentences. \
State facts and results. Avoid corporate filler and inflated language.

LENGTH AND STRUCTURE
20. The rewritten CV must fit in exactly 2 pages on A4 paper (9pt Helvetica, 1.8cm margins). \
Prioritize density. Cut redundancy before cutting keywords.
21. Apply these bullet budgets per role:
    Roles active since 2025 (LinkedIn, Amazon): maximum 5 bullets of 20 words each.
    Roles from 2021 to 2025 (Avanti IT): maximum 3 bullets of 15 words each.
    Roles before 2021 (Alcalisa, GRC): maximum 2 bullets of 15 words each.
22. Professional profile: maximum 50 words.
23. Page 1 must contain the professional profile and the 2 most recent roles. \
Page 2 contains all remaining roles, education, skills, and languages. \
This structure ensures the first page works as a compelling standalone preview.

SECTION HEADERS
24. Use these exact section headers, in English, in uppercase. Do not rename, translate, or combine them:
    PROFESSIONAL PROFILE, WORK EXPERIENCE, EDUCATION, SKILLS, LANGUAGES

EDUCATION FORMAT
25. Each education entry must appear on exactly three separate lines, in this order:
    Line 1: degree title only (e.g. "Diploma in AI and Community Management")
    Line 2: date range only (e.g. "Aug 2023 – Nov 2023" or "2011 – 2012")
    Line 3: institution and location (e.g. "Universidad del Valle, Cali, Colombia")
    Do NOT merge these into a single line. Do NOT add periods at the end of any line.

OUTPUT FORMAT: use these exact delimiters and nothing else.
<CV>
[full rewritten CV, plain text]
</CV>
<ATS_SCORE>[integer 0-100: your assessment of how well the rewritten CV matches the job \
description, based on keyword density, role alignment, and terminology mirroring]</ATS_SCORE>
<KEYWORDS>[comma-separated list of keywords injected from the job description]</KEYWORDS>\
"""


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

    cv_text = _fix_static_fields(cv_text)

    return {"cv_text": cv_text, "ats_score": ats_score, "keywords_added": keywords}


# ── API pública ────────────────────────────────────────────────────────────────

def rewrite(
    cv: dict,
    job: dict,
    rama: str,
    auditor_feedback: str = "",
    previous_cv_text: str = "",
    evidence_map: dict | None = None,
) -> dict:
    """
    Reescribe el CV optimizado para ATS usando evidence mapping.
    Hasta MAX_ATTEMPTS si score < 95 y no es poor fit.

    Args:
        cv:               dict del CV (de cv_parser).
        job:              dict del cargo {"cargo", "empresa", "descripcion", ...}.
        rama:             "A" | "B" | "C".
        auditor_feedback: feedback del auditor para ciclos posteriores.
        previous_cv_text: CV mejorado del ciclo anterior (carry-forward).
        evidence_map:     Si se provee (no None), se usa directamente sin llamar a
                          build_evidence_map internamente. poor_fit no se chequea
                          adentro — el caller (main.py) ya lo hizo.

    Returns:
        {
            "cv_text":         str,
            "ats_score":       int,
            "keywords_added":  list,
            "attempts":        int,
            "passed_ats":      bool,
            "poor_fit":        bool,
            "poor_fit_reason": str,
        }
    """
    import json

    if evidence_map is None:
        # Comportamiento original: cargar narrativas y construir evidence_map internamente.
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

        built_map = {}
        if job.get("descripcion") and narrativas:
            try:
                built_map = build_evidence_map(job["descripcion"], narrativas)
                tier3_count = sum(1 for v in built_map.values() if v["tier"] == 3)
                print(f"[CVRewriter] Evidence map: {len(built_map)} skills — "
                      f"{sum(1 for v in built_map.values() if v['tier']==1)} T1, "
                      f"{sum(1 for v in built_map.values() if v['tier']==2)} T2, "
                      f"{tier3_count} T3")
                if tier3_count > POOR_FIT_THRESHOLD:
                    print(f"[CVRewriter] POOR FIT: {tier3_count} skills sin evidencia")
                    is_carry = bool(previous_cv_text)
                    cv_plain = previous_cv_text if is_carry else _cv_to_plain_text(cv, rama)
                    cv_enriched = cv_plain if is_carry else _enrich_with_narratives(cv_plain, rama)
                    result = _rewrite_once(cv_enriched, job, None,
                                           evidence_map=built_map,
                                           auditor_feedback=auditor_feedback)
                    result["attempts"] = 1
                    result["passed_ats"] = result["ats_score"] >= config.THRESHOLD_ATS
                    result["poor_fit"] = True
                    result["poor_fit_reason"] = (
                        f"{tier3_count} skills del JD sin evidencia en narrativas"
                    )
                    return result
            except Exception as e:
                print(f"[CVRewriter] evidence_mapper error: {e} — continuando sin mapa")
        evidence_map = built_map
    # else: evidence_map fue provisto — usarlo directamente, sin poor_fit check interno.

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
            # Verificar que evidencia Tier 1 está presente en el CV
            if evidence_map and attempt < max_attempts:
                missing = verify_evidence(result["cv_text"], evidence_map)
                if missing:
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
