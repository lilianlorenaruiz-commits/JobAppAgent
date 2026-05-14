"""
Diagnostic script — Phase 1 evidence gathering.
Runs ONE rewrite + ONE audit and prints the FULL auditor response.
Does NOT loop. Does NOT fix anything. Only gathers evidence.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.cv_parser       import parse_cv
from agents.cv_rewriter     import rewrite
from agents.ats_auditor     import audit

JOB = {
    "cargo":       "Paid Media Manager",
    "empresa":     "Rappi",
    "descripcion": (
        "Buscamos Paid Media Manager con experiencia sólida en gestión de campañas de "
        "performance marketing en plataformas como Google Ads, Meta Ads (Facebook e Instagram), "
        "Amazon Ads y LinkedIn Ads. El candidato ideal tiene experiencia en programmatic "
        "advertising, optimización de ROAS y ACOS, análisis de métricas de performance "
        "(CTR, CPC, DPV, NTB Sales), y manejo de presupuestos B2B y B2C superiores a "
        "USD 500K. Inglés C1 indispensable para coordinación con equipos APAC y globales. "
        "Se valorará experiencia en Amazon Seller/Vendor Central, DSP, y herramientas de "
        "data analysis para optimización de campañas. Capacidad de liderazgo, pensamiento "
        "estratégico y orientación a resultados cuantificables."
    ),
    "url":       "https://linkedin.com/jobs/dry-C-001",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
}

print("=" * 60)
print("STEP 1 — Rewriting CV")
print("=" * 60)
cv = parse_cv()
rw = rewrite(cv, JOB, "C")
print(f"\nRewriter ATS self-score: {rw['ats_score']}%")
print(f"Keywords added by rewriter: {rw['keywords_added']}")
print(f"\n{'='*60}")
print("REWRITTEN CV (first 2000 chars):")
print("=" * 60)
print(rw["cv_text"][:2000])

print(f"\n{'='*60}")
print("STEP 2 — Running Auditor")
print("=" * 60)
result = audit(JOB, rw["cv_text"])

print(f"\nAUDIT SCORE:  {result['audit_score']}%")
print(f"VERDICT:      {result['verdict']}")
print(f"\nKEYWORDS MISSING:")
for kw in result["keywords_missing"]:
    print(f"  - {kw}")
print(f"\nWEAK POINTS (what a recruiter would challenge):")
for wp in result["weak_points"]:
    print(f"  - {wp}")
print(f"\nFEEDBACK TO REWRITER (full text):")
print("-" * 60)
print(result["feedback_to_rewriter"])
print("-" * 60)

# Save full evidence to file
with open("_debug_audit_output.json", "w", encoding="utf-8") as f:
    json.dump({
        "rewriter_ats_score": rw["ats_score"],
        "rewriter_keywords_added": rw["keywords_added"],
        "cv_text_full": rw["cv_text"],
        "audit_score": result["audit_score"],
        "verdict": result["verdict"],
        "keywords_missing": result["keywords_missing"],
        "weak_points": result["weak_points"],
        "feedback_to_rewriter": result["feedback_to_rewriter"],
    }, f, ensure_ascii=False, indent=2)
print("\nFull evidence saved to _debug_audit_output.json")
