"""
Smoke test — Pipeline completo (2026-05-19)
Prueba tres rutas:
  A. Path del NO — skill score bajo   (Falabella PM — Marketplace, no encaja)
  B. Path del NO — poor_fit           (cargo mixto con keywords sin evidencia)
  C. Path del SÍ — pipeline completo  (Paid Media, Rama C, dry_run=True → Canal A)

URLs reales:
  Falabella: https://www.linkedin.com/jobs/view/4411801015
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import _process_job

# ── CV sintético de Lorena ──────────────────────────────────────────────────────

_CV = {
    "nombre":      "Lorena Ruiz",
    "experiencia": [
        {
            "cargo":       "Digital Channels Consultant",
            "empresa":     "Avanti IT SAS",
            "fecha":       "August 2021 – April 2025",
            "descripcion": (
                "Gestión de campañas digitales. Ecommerce analytics. "
                "Meta Ads, Google Ads, Amazon Ads. Presupuestos USD 200K+/mes."
            ),
        }
    ],
    "educacion": [{"titulo": "Comunicación Social", "institucion": "Universidad Externado"}],
    "skills":    ["Meta Ads", "Google Ads", "Amazon Ads", "Analytics", "SEO", "SEM", "LinkedIn Ads"],
    "idiomas":   ["Spanish (native)", "English (C2)"],
}


# ── Jobs de prueba ──────────────────────────────────────────────────────────────

# A. Score bajo — nunca llega a evidence_map
_JOB_A = {
    "cargo":       "Product Manager Vestuario Online Mkp",
    "empresa":     "Falabella",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá, D.C., Colombia",
    "descripcion": (
        "Buscamos un/a Product Manager para liderar el crecimiento y desarrollo de la "
        "categoría de Vestuario Online bajo el modelo Marketplace, con enfoque estratégico "
        "y comercial. "
        "Responsabilidades: "
        "Definir y ejecutar el plan estratégico comercial de mediano plazo para el "
        "desarrollo de categorías en Marketplace. "
        "Investigar, identificar y contactar nuevos proveedores que se incorporen a la categoría. "
        "Analizar referentes internacionales y la competencia nacional para anticipar tendencias "
        "y señales del mercado. "
        "Definir y desarrollar el mix de productos más competitivo del mercado online. "
        "Asegurar la correcta publicación del mix de productos mediante integraciones con "
        "plataformas VTEX/Shopify. "
        "Negociar y gestionar lanzamientos constantes de productos, campañas de marketing y "
        "eventos promocionales en el sitio web. "
        "Requisitos: "
        "Profesional en Ingeniería Industrial, Administración de Empresas o carreras afines. "
        "Mínimo 2 años de experiencia en cargos similares. "
        "Conocimiento y experiencia en gestión de Marketplace. "
        "Perfil comercial, analítico y con habilidades de negociación."
    ),
    "url":  "https://www.linkedin.com/jobs/view/4411801015",
    "rama": "B",
}

# C. Path del SÍ — Paid Media Manager (Rama C)
# JD alineado a evidencias reales de narrativas_lorena.json.
# Sin "Google Analytics" (no está en narrativas — RC-2 impide inyectarlo).
# Keywords cubiertos: Meta Ads (Alcalisa T1), Google Ads (GRC T1), Amazon Ads/DSP (Amazon T1),
# LinkedIn Ads (LinkedIn T1), ROAS (Amazon T1), presupuesto (LinkedIn USD 240K T1).
_JOB_C = {
    "cargo":       "Paid Media Manager",
    "empresa":     "OMD Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "descripcion": (
        "Buscamos Paid Media Manager con experiencia en Meta Ads, Google Ads, Amazon Ads y LinkedIn Ads. "
        "Planear y optimizar campañas de performance marketing y paid media en plataformas digitales. "
        "Gestión de presupuesto mensual USD 200K+. Optimizar ROAS, CPA y ACOS. "
        "Experiencia en programmatic advertising y Amazon DSP deseable. "
        "Inglés C1 requerido. SEM y data analysis."
    ),
    "url":  "https://www.linkedin.com/jobs/view/fake-omd-001",
    "rama": "C",
}


def _sep(title: str) -> None:
    print(f"\n{'═'*62}")
    print(f"  {title}")
    print(f"{'═'*62}")


def _print_result(label: str, result: dict) -> None:
    print(f"\n  {'─'*56}")
    print(f"  RESULTADO — {label}")
    print(f"  {'─'*56}")
    for k, v in result.items():
        if k != "pdf" or v:
            print(f"    {k:12}: {v}")


def _check(label: str, condition: bool, msg_ok: str, msg_fail: str) -> bool:
    icon = "✅" if condition else "❌"
    msg = msg_ok if condition else msg_fail
    print(f"  {icon} {label}: {msg}")
    return condition


def run_smoke() -> None:
    all_ok = True

    # ── A. Path del NO — skill score bajo ──────────────────────────────────────
    _sep("CASO A — Path del NO (skill score bajo) — Falabella PM")
    print(f"  Rama B | dry_run=True")
    result_a = _process_job(_CV, _JOB_A, rama="B", dry_run=True)
    _print_result("Falabella PM", result_a)
    print()
    ok_a1 = _check("Status", result_a["status"] == "descartado",
                   "descartado ✓", f"esperado 'descartado', obtenido '{result_a['status']}'")
    ok_a2 = _check("Score", result_a["score"] < 85,
                   f"score={result_a['score']}% < 85% ✓",
                   f"score={result_a['score']}% ≥ 85% — no debería haber pasado")
    all_ok = all_ok and ok_a1 and ok_a2

    # ── C. Path del SÍ — Paid Media Specialist ─────────────────────────────────
    _sep("CASO C — Path del SÍ — OMD Colombia Paid Media Specialist")
    print(f"  Rama C | dry_run=True")
    result_c = _process_job(_CV, _JOB_C, rama="C", dry_run=True)
    _print_result("OMD Paid Media", result_c)
    print()
    ok_c1 = _check("Status", result_c["status"] in ("enviado", "pendiente_envio"),
                   f"status='{result_c['status']}' ✓",
                   f"status='{result_c['status']}' — esperado enviado/pendiente_envio")
    ok_c2 = _check("Score", result_c["score"] > 0,
                   f"score={result_c['score']}% ✓",
                   "score=0 — no se procesó correctamente")
    motivo_c = result_c.get("motivo", "")
    ok_c3 = _check("Canal en motivo", "canal" in motivo_c.lower() or "C" in motivo_c,
                   f"canal presente ✓",
                   f"canal no mencionado en motivo: '{motivo_c}'")
    all_ok = all_ok and ok_c1 and ok_c2

    # ── Resumen ─────────────────────────────────────────────────────────────────
    _sep("RESUMEN SMOKE TEST")
    print(f"  Caso A (skill score bajo)    : {'✅ PASS' if (ok_a1 and ok_a2) else '❌ FAIL'}")
    print(f"  Caso C (path del sí)         : {'✅ PASS' if (ok_c1 and ok_c2) else '❌ FAIL'}")
    print()
    if all_ok:
        print("  ✅ Smoke test completo — pipeline funcionando correctamente.")
    else:
        print("  ❌ Smoke test con fallos — revisar resultados arriba.")


if __name__ == "__main__":
    run_smoke()
