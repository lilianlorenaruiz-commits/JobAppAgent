"""
Regenerate Grupo RED PDF with the new professional monochrome design.
Runs cv_rewriter to get fresh optimized text, then generates PDF.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.cv_parser import parse_cv
from agents.cv_rewriter import rewrite
from agents.pdf_generator import generate

cv = parse_cv()

job = {
    "cargo":       "Trafficker Digital Senior Bilingüe",
    "empresa":     "Grupo RED",
    "url":         "https://linkedin.com/jobs/dry-C-grupo-red",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "descripcion": (
        "Buscamos Trafficker Digital Senior con experiencia sólida en gestión y optimización "
        "de campañas de paid media en plataformas Google Ads, Meta Ads (Facebook e Instagram), "
        "Amazon Ads y LinkedIn Ads. El candidato ideal maneja programmatic advertising, "
        "optimización de ROAS y ACOS, análisis de métricas de performance (CTR, CPC, DPV, "
        "NTB Sales) y presupuestos superiores a USD 200K. Inglés C1/C2 indispensable para "
        "coordinación con clientes y equipos internacionales. Se valorará experiencia en "
        "Amazon DSP, Amazon Seller/Vendor Central, Amazon Marketing Cloud y herramientas "
        "de data analysis. Capacidad de liderazgo de cuentas B2B y B2C, pensamiento "
        "estratégico y orientación a resultados cuantificables. Modalidad híbrida, Bogotá."
    ),
    "rama": "C",
}

print("[Regen] Iniciando reescritura CV para Grupo RED...")
result = rewrite(cv, job, rama="C")
print(f"[Regen] ATS Score: {result['ats_score']}% | Intentos: {result['attempts']} | Pasó: {result['passed_ats']}")
print(f"[Regen] Keywords: {result['keywords_added']}")

path = generate(result["cv_text"], job)
print(f"\n[Regen] PDF generado exitosamente: {path}")
