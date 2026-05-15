"""
Narrative Builder — Agente 0 (pre-pipeline)
Lee narrativas_lorena.json y genera bullets ATS listos por rama.
Output: dict con secciones listas para inyectar en cv_rewriter._cv_to_plain_text().

Uso:
    from agents.narrative_builder import build_narratives
    narratives = build_narratives()          # genera para las 3 ramas
    narratives = build_narratives(rama="C")  # solo Paid Media
"""
import json
import os
import sys

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

NARRATIVAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "narrativas", "narrativas_lorena.json"
)

_client: anthropic.Anthropic | None = None
_cache: dict[str, str] = {}   # rama → bullets (vive mientras dure el proceso)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key or key.startswith("PEGA_AQUI"):
            raise RuntimeError("API key de Anthropic no configurada.")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _load_narrativas() -> dict:
    if not os.path.exists(NARRATIVAS_PATH):
        raise FileNotFoundError(f"No se encontró {NARRATIVAS_PATH}")
    with open(NARRATIVAS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Prompts por rama ───────────────────────────────────────────────────────────

_SYSTEM = """\
You are a senior CV writer specialized in ATS optimization for Latin American \
marketing and digital professionals. You receive a structured JSON with real \
professional data (numbers, metrics, company names, dates) and write ATS-ready \
bullet points in plain English.

RULES:
1. Every bullet must start with a strong action verb.
2. Every bullet must contain at least one specific number, metric, or percentage.
3. No filler phrases ("results-oriented", "passionate", "dynamic").
4. Plain text only. No markdown, no asterisks, no bullet symbols.
5. Mirror the exact language of the TARGET_RAMA keywords.
6. Maximum 2 lines per bullet. Keep it scannable for ATS parsers.
7. Write in the same bilingual Spanish/English tone as a senior Latin American professional.
8. NEVER attribute total company revenue or total brand sales as the candidate's personal paid media ROI. Only attribute metrics directly tied to campaigns the candidate managed.
9. MARKET ATTRIBUTION. Respect strict geographic scope per role:
   LinkedIn/Teleperformance role (Feb 2026, Present): Latin America ONLY. NEVER write "APAC" for this role.
   Amazon Campaign Planner role: APAC markets ONLY. NEVER write "Latin America" for this role.
   The LinkedIn AEs in Singapore, Sydney, and Tokyo are supervisors she reports to. They are not the market she manages.
10. USE ONLY DATA FROM THE SOURCE. Never extrapolate, invent, or reframe metrics. If a number does not appear explicitly in the candidate data for a given role, do not create it. Write only what is documented.

OUTPUT: Return ONLY the bullet points, one per line, no headers, no explanations.\
"""

_RAMA_CONTEXT = {
    "A": (
        "TARGET_RAMA: Brand Strategy & Marketing Consultancy\n"
        "KEY KEYWORDS TO MIRROR: brand strategy, digital transformation, B2B/B2C, "
        "P&L management, brand equity, data analysis, C-suite presentations, "
        "360° campaigns, market positioning, consumer insights\n"
        "FOCUS: leadership of brand projects, budget ownership, measurable brand impact, "
        "strategic planning at executive level"
    ),
    "B": (
        "TARGET_RAMA: Trade Marketing & Retail\n"
        "KEY KEYWORDS TO MIRROR: trade marketing, category management, shopper marketing, "
        "P&L, retail activation, point of sale, distributor management, market share, "
        "shopper insights, sell-out\n"
        "FOCUS: retail chain relationships, category P&L, activation ROI, market share growth"
    ),
    "C": (
        "TARGET_RAMA: Paid Media & Performance Marketing\n"
        "KEY KEYWORDS TO MIRROR: paid media, performance marketing, Amazon Ads, Google Ads, "
        "Meta Ads, LinkedIn Ads, DSP, programmatic, ROAS, ACOS, tROAS, NTB sales, "
        "campaign optimization, budget management, data analysis\n"
        "FOCUS: platform-specific metrics, budget scale, before/after ROAS/ACOS improvements, "
        "cross-platform expertise. "
        "NOTE: APAC market belongs to Amazon role only. LinkedIn role = Latin America market only."
    ),
}


def _build_for_rama(narrativas: dict, rama: str) -> str:
    rama_context = _RAMA_CONTEXT.get(rama, "")
    data_str = json.dumps(narrativas, ensure_ascii=False, indent=2)

    user = (
        f"{rama_context}\n\n"
        f"CANDIDATE DATA (real numbers — do NOT fabricate or modify):\n{data_str}\n\n"
        f"Write 12-15 ATS-optimized bullet points selecting the most relevant achievements "
        f"for {rama_context.split(chr(10))[0]}. Prioritize bullets with the strongest metrics."
    )

    response = _get_client().messages.create(
        model=config.MODEL_FAST,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
    )

    return response.content[0].text.strip()


# ── API pública ────────────────────────────────────────────────────────────────

def build_narratives(rama: str | None = None) -> dict[str, str]:
    """
    Genera bullets ATS listos por rama a partir de narrativas_lorena.json.

    Args:
        rama: "A" | "B" | "C" | None (todas)

    Returns:
        {"A": "bullet1\\nbullet2\\n...", "B": "...", "C": "..."}
    """
    narrativas = _load_narrativas()
    ramas = [rama.upper()] if rama else ["A", "B", "C"]
    result = {}

    for r in ramas:
        if r in _cache:
            print(f"[NarrativeBuilder] Rama {r} — usando cache ({len(_cache[r].splitlines())} bullets)")
            result[r] = _cache[r]
        else:
            print(f"[NarrativeBuilder] Generando bullets para Rama {r}...")
            _cache[r] = _build_for_rama(narrativas, r)
            result[r] = _cache[r]
            print(f"[NarrativeBuilder] Rama {r} — {len(result[r].splitlines())} bullets generados")

    return result


def get_bullets_for_cv(rama: str) -> str:
    """
    Retorna bullets validados para inyectar en cv_rewriter.
    Prioriza bullets_validados del JSON (sin LLM). Solo usa LLM como fallback.
    """
    rama = rama.upper()
    try:
        narrativas = _load_narrativas()
        validados = narrativas.get("bullets_validados", {})
        if rama in validados and validados[rama]:
            bullets = validados[rama]
            print(f"[NarrativeBuilder] Rama {rama} — {len(bullets)} bullets validados (sin LLM)")
            return "\n".join(bullets)
    except Exception as e:
        print(f"[NarrativeBuilder] Error leyendo bullets_validados: {e}")

    print(f"[NarrativeBuilder] Rama {rama} — fallback a generación LLM")
    result = build_narratives(rama)
    return result.get(rama, "")


# ── CLI / Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rama_arg = sys.argv[1].upper() if len(sys.argv) > 1 else None
    results  = build_narratives(rama_arg)
    for r, bullets in results.items():
        print(f"\n{'='*55}")
        print(f"RAMA {r} — BULLETS ATS")
        print(f"{'='*55}")
        print(bullets)
