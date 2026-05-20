"""
Smoke Test Full Pipeline — 3 Canales (2026-05-19)
TDD-style: cada caso define assertions explícitas y reporta PASS/FAIL con evidencia.

Canales:
  A — Brand & Sales Ambassador Licores · DISLICORES S.A.S (elempleo.com)   → Rama A
  B — Category Manager / Brand Buying Manager · Helti (computrabajo.com)   → Rama B
  C — Director de Retail Media · Cruz Verde Colombia (LinkedIn)             → Rama C

Pipeline completo por caso:
  1. Skill Matcher  → score ≥ 75% para pasar (threshold Rama A/B/C — calibrado 2026-05-20)
  2. Evidence Map   → build_evidence_map() + poor_fit check
  3. CV Rewriter    → ATS ≥ 92% (A/B) / ≥ 95% (C), idioma correcto, sin orphan USD claims
  4. ATS Auditor    → audit() PASS
  5. PDF Generator  → archivo generado con nombre correcto
  6. Applicator     → dry_run=True (no envío real)

Uso:
  cd "C:\\Users\\lilia\\Clientes\\Lorena Ruiz\\JobAppAgent"
  python _smoke_3canales_2026_05_19.py
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Unicode en terminales Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from main import _process_job
from agents.cv_parser import parse_cv

# ══════════════════════════════════════════════════════════════════════════════
# CV — Lorena Ruiz (desde PDF real)
# ══════════════════════════════════════════════════════════════════════════════

def _load_cv() -> dict:
    """Carga CV desde PDF real (agents/cv_parser.py)."""
    return parse_cv()


# ══════════════════════════════════════════════════════════════════════════════
# JOBs — Datos reales de los 3 portales
# ══════════════════════════════════════════════════════════════════════════════

_JOB_A = {
    "cargo":       "Brand & Sales Ambassador Licores",
    "empresa":     "DISLICORES S.A.S",
    "modalidad":   "Presencial",
    "ubicacion":   "Medellín, Antioquia, Colombia",
    "descripcion": (
        "Brand & Sales Ambassador Licores — Medellín. "
        "Inspirar la apreciación y el gusto por la categoría mediante la educación a stakeholders. "
        "Actúa como vínculo crítico entre la marca, el sector y los consumidores, "
        "impulsando el posicionamiento, visibilidad y crecimiento de mercado a largo plazo. "
        "Responsabilidades: "
        "Desarrollar estrategia de marca y activaciones BTL/ATL en punto de venta. "
        "Capacitar a equipos de ventas y canales de distribución sobre el portafolio de licores. "
        "Gestionar relaciones con distribuidores y clientes clave del canal on-trade y off-trade. "
        "Analizar datos de mercado y comportamiento del consumidor para identificar oportunidades. "
        "Ejecutar planes de trade marketing y visibilidad en PDV. "
        "Monitorear participación de mercado y desempeño de la categoría. "
        "Requisitos: "
        "Profesional en Administración de Empresas, Mercadeo, Administración Comercial o afines. "
        "Mínimo 4 años de experiencia en marketing, ventas o trade marketing en consumo masivo. "
        "Conocimiento del sector de bebidas y licores deseable. "
        "Perfil comercial, analítico, con habilidades de negociación y comunicación. "
        "Salary: $6 a $8 millones COP."
    ),
    "url":  "https://www.elempleo.com/co/ofertas-trabajo/brand-sales-ambassador-licores-medellin-1886710436",
    "rama": "A",
}

_JOB_B = {
    "cargo":       "Category Manager / Brand & Buying Manager",
    "empresa":     "Helti",
    "modalidad":   "Presencial",
    "ubicacion":   "Itagüí, Antioquia, Colombia",
    "descripcion": (
        "Category Manager / Product Manager / Brand & Buying Manager — Sector Textil: Lencería Íntima. "
        "Itagüí, Colombia. Contrato a término indefinido. Salario $4.500.000 a $5.000.000 COP. "
        "Operación en 3 países. Gestión estratégica · Branding 360° · Buying · Data Driven. "
        "Objetivo del cargo: "
        "Buscamos un(a) Brand & Buying Manager con visión estratégica y enfoque analítico para liderar "
        "integralmente la estrategia de marca y el proceso comercial de nuestra línea de lencería íntima. "
        "Responsable de garantizar el posicionamiento de la marca en diferentes mercados, la rentabilidad "
        "del portafolio y la eficiencia de la cadena de abastecimiento nacional e internacional, "
        "tomando decisiones basadas en datos y tendencias de consumo. "
        "Estrategia de marca: "
        "Definir e implementar el plan estratégico de marca para los países asignados. "
        "Liderar el posicionamiento, identidad visual y propuesta de valor de la categoría. "
        "Garantizar coherencia de marca en todos los puntos de contacto. "
        "Posicionamiento internacional: "
        "Adaptar la estrategia comercial y de marca según cada mercado. "
        "Analizar tendencias y oportunidades de crecimiento regional. "
        "Monitorear participación de mercado y desempeño competitivo. "
        "Buying & gestión de portafolio: "
        "Definir el mix de producto y curar colecciones por temporada. "
        "Gestionar compras nacionales e internacionales. "
        "Negociar con proveedores y asegurar abastecimiento eficiente. "
        "Análisis comercial y financiero: "
        "Monitorear KPIs comerciales, márgenes y rentabilidad por SKU. "
        "Analizar sell-in, sell-out y rotación de inventario. "
        "Gestionar presupuesto de categoría y proyecciones de compra. "
        "Gestión de inventario: "
        "Planificar abastecimiento y niveles óptimos de stock. "
        "Reducir obsolescencia y minimizar quiebres. "
        "Data & reporting: "
        "Construir dashboards y reportes estratégicos en Power BI y Excel. "
        "Analizar tendencias de consumo, comportamiento de compra y oportunidades de negocio. "
        "Conocimientos y habilidades técnicas: Excel avanzado, KPI comerciales, Gestión de Compras, "
        "Visión estratégica, Análisis financiero básico, Relación con Proveedores, "
        "Estrategia de comunicación y ventas, Selección y rentabilidad de portafolio, Inglés B2+. "
        "Profesional en Administración de Empresas, Negocios Internacionales, Ingeniería Industrial, "
        "Mercadeo o carreras afines."
    ),
    "url":  "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-category-manager-brand-buying-manager-en-itagui-1A8D799076F9398661373E686DCF3405",
    "rama": "B",
}

_JOB_C = {
    "cargo":       "Director de Retail Media",
    "empresa":     "Cruz Verde Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá, D.C., Colombia",
    "descripcion": (
        "Director de Retail Media — Cruz Verde Colombia. Bogotá D.C. Full-time. Nivel Director. "
        "Diseñar e implementar la estrategia de retail media a nivel nacional. "
        "Desarrollar y gestionar el portafolio de productos publicitarios en canales on-site, "
        "off-site e in-store. "
        "Liderar relaciones con marcas y anunciantes. "
        "Fortalecer la monetización de audiencias y optimización de activos digitales. "
        "Definir modelos de medición, atribución y análisis de ROI. "
        "Colaborar transversalmente con equipos comercial, marketing, datos y tecnología. "
        "Requisitos: "
        "Experiencia comprobada liderando iniciativas de retail media, medios digitales o "
        "monetización de audiencias. "
        "Visión estratégica con enfoque en resultados. "
        "Capacidades analíticas sólidas y toma de decisiones basada en datos. "
        "Negociación con clientes y gestión de relaciones. "
        "Experiencia liderando equipos multidisciplinarios. "
        "Conocimiento en paid media, programmatic advertising, Meta Ads, Google Ads, Amazon Ads. "
        "Gestión de presupuestos de medios y optimización de ROAS y CPA."
    ),
    "url":  "https://www.linkedin.com/jobs/view/4408882370",
    "rama": "C",
}

_JOBS = [
    ("A", _JOB_A, "Brand Sales Ambassador Licores — DISLICORES S.A.S"),
    ("B", _JOB_B, "Category Manager Brand Buying — Helti"),
    ("C", _JOB_C, "Director Retail Media — Cruz Verde Colombia"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Assertions TDD
# ══════════════════════════════════════════════════════════════════════════════

def _assert(label: str, condition: bool, msg_ok: str, msg_fail: str,
            results: list) -> bool:
    icon = "✅" if condition else "❌"
    msg  = msg_ok if condition else msg_fail
    line = f"    {icon} {label}: {msg}"
    print(line)
    results.append({"label": label, "pass": condition, "detail": msg})
    return condition


def _run_case(canal: str, job: dict, description: str, cv: dict) -> dict:
    """Ejecuta pipeline completo dry_run=True y valida assertions TDD."""
    sep = "═" * 68
    print(f"\n{sep}")
    print(f"  CANAL {canal} — {description}")
    print(f"  Cargo:   {job['cargo']}")
    print(f"  Empresa: {job['empresa']}")
    print(f"  Rama:    {job['rama']} | Modalidad: {job['modalidad']}")
    print(f"  Portal:  {job['url'][:70]}...")
    print(sep)

    t0 = time.time()
    assertions = []
    result = {}

    try:
        result = _process_job(cv, job, rama=job["rama"], dry_run=True)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"  ❌ EXCEPCIÓN en pipeline: {exc}")
        print(tb)
        result = {
            "status": "error",
            "score": 0,
            "motivo": str(exc),
            "pdf": "",
        }

    elapsed = round(time.time() - t0, 1)
    print(f"\n  ── Assertions Canal {canal} ──────────────────────────────────────")

    status   = result.get("status", "")
    score    = result.get("score", 0)
    motivo   = result.get("motivo", "")
    pdf_path = result.get("pdf", "")

    # ── T1: Pipeline no crasheó ───────────────────────────────────────────────
    _assert("T1 Pipeline", status != "error",
            "completó sin excepción",
            f"excepción: {motivo[:80]}",
            assertions)

    if status == "descartado":
        # ── T2: Si se descartó, debe tener razón clara ────────────────────────
        _assert("T2 Descarte", bool(motivo),
                f"motivo registrado ({motivo[:60]})",
                "descartado sin motivo",
                assertions)
        _assert("T3 Score bajo esperado", score < 75,
                f"score={score}% bajo threshold ✓",
                f"score={score}% ≥ 75% — descarte inesperado",
                assertions)

    else:
        # ── T2: Score ≥ 75 (threshold calibrado 2026-05-20) ──────────────────
        _assert("T2 Score matcher", score >= 75,
                f"score={score}% ≥ 75% ✓",
                f"score={score}% < 75% — no debería haber pasado",
                assertions)

        # ── T3: ATS en motivo ─────────────────────────────────────────────────
        has_ats = "ATS" in motivo or "ats" in motivo.lower()
        _assert("T3 ATS en motivo", has_ats,
                f"ATS score reportado en motivo ✓",
                f"ATS no aparece en motivo: '{motivo[:60]}'",
                assertions)

        # ── T4: PDF generado ──────────────────────────────────────────────────
        pdf_exists = bool(pdf_path) and os.path.exists(pdf_path)
        _assert("T4 PDF generado", pdf_exists,
                f"PDF existe: {os.path.basename(pdf_path)} ✓",
                f"PDF no generado o ruta vacía: '{pdf_path}'",
                assertions)

        if pdf_exists:
            # ── T5: Nombre PDF sin placeholders ───────────────────────────────
            basename = os.path.basename(pdf_path)
            no_placeholder = (
                "Cargo LinkedIn" not in basename
                and "Empresa LinkedIn" not in basename
                and "cargo" not in basename.lower().replace("lorena", "")
            )
            _assert("T5 Nombre PDF", no_placeholder,
                    f"nombre correcto '{basename}' ✓",
                    f"placeholder en nombre: '{basename}'",
                    assertions)

        # ── T6: Canal reportado ───────────────────────────────────────────────
        canal_ok = any(
            kw in motivo for kw in ["Canal A", "Canal B", "Canal C",
                                    "canal A", "canal B", "canal C",
                                    "Easy Apply", "portal", "email"]
        )
        _assert("T6 Canal en motivo", canal_ok,
                "canal de aplicación reportado ✓",
                f"canal no mencionado en motivo: '{motivo[:80]}'",
                assertions)

        # ── T7: ATS score ≥ threshold (92% A/B, 95% C) ───────────────────────
        import re as _re
        ats_threshold = 95 if canal == "C" else 92
        ats_match = _re.search(r"ATS\s+(\d+)%", motivo, _re.IGNORECASE)
        ats_val   = int(ats_match.group(1)) if ats_match else None
        if ats_val is not None:
            _assert(f"T7 ATS ≥ {ats_threshold}%", ats_val >= ats_threshold,
                    f"ATS={ats_val}% ≥ {ats_threshold}% ✓",
                    f"ATS={ats_val}% < {ats_threshold}% — CV no optimizado",
                    assertions)
        else:
            _assert(f"T7 ATS ≥ {ats_threshold}%", False,
                    "",
                    "no se pudo extraer ATS score del motivo",
                    assertions)

    passed = all(a["pass"] for a in assertions)
    print(f"\n  Tiempo: {elapsed}s | {'✅ PASS' if passed else '❌ FAIL'} "
          f"({sum(a['pass'] for a in assertions)}/{len(assertions)} assertions)")

    return {
        "canal":      canal,
        "cargo":      job["cargo"],
        "empresa":    job["empresa"],
        "score":      score,
        "status":     status,
        "motivo":     motivo,
        "pdf":        pdf_path,
        "assertions": assertions,
        "passed":     passed,
        "elapsed_s":  elapsed,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Runner principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    banner = "═" * 68
    print(f"\n{banner}")
    print("  SMOKE TEST — FULL PIPELINE 3 CANALES (2026-05-19)")
    print("  TDD — Pipeline: SkillMatcher → EvidenceMap → CVRewriter → ATS → PDF → Apply")
    print(banner)

    print("\nCargando CV desde PDF real...")
    try:
        cv = _load_cv()
        print(f"  CV listo: {cv['nombre']} | {len(cv.get('experiencia', []))} roles")
    except Exception as e:
        print(f"  ❌ ERROR cargando CV: {e}")
        sys.exit(1)

    t_total = time.time()
    resultados = []

    for canal, job, desc in _JOBS:
        r = _run_case(canal, job, desc, cv)
        resultados.append(r)

    # ── Resumen final ─────────────────────────────────────────────────────────
    total_elapsed = round(time.time() - t_total, 1)
    print(f"\n\n{'═'*68}")
    print("  RESUMEN SMOKE TEST — 3 CANALES")
    print(f"{'═'*68}")

    total_pass = 0
    total_fail = 0

    for r in resultados:
        verdict = "✅ PASS" if r["passed"] else "❌ FAIL"
        a_pass  = sum(a["pass"] for a in r["assertions"])
        a_total = len(r["assertions"])
        print(f"\n  Canal {r['canal']} — {r['cargo']} @ {r['empresa']}")
        print(f"    Status:  {r['status']}  |  Score: {r['score']}%")
        print(f"    Motivo:  {r['motivo'][:80]}")
        pdf_name = os.path.basename(r["pdf"]) if r["pdf"] else "(sin PDF)"
        print(f"    PDF:     {pdf_name}")
        print(f"    Tiempo:  {r['elapsed_s']}s")
        print(f"    Tests:   {a_pass}/{a_total} assertions — {verdict}")

        if not r["passed"]:
            for a in r["assertions"]:
                if not a["pass"]:
                    print(f"      ❌ [{a['label']}] {a['detail']}")

        if r["passed"]:
            total_pass += 1
        else:
            total_fail += 1

    print(f"\n{'─'*68}")
    print(f"  TOTAL: {total_pass}/3 canales PASS — {total_fail} FAIL — {total_elapsed}s")
    print(f"{'─'*68}")

    if total_fail == 0:
        print("\n  ✅ Smoke test completo — pipeline funcionando en los 3 canales.")
    else:
        print(f"\n  ❌ {total_fail} canal(es) con fallos — revisar resultados arriba.")
    print()


if __name__ == "__main__":
    main()
