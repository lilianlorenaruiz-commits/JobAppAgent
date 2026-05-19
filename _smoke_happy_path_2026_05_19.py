"""
Smoke Test Happy Path — 3 Ramas (2026-05-19)
TDD — Verificar que el CV rewriter PRODUCE CV completo (no solo descarta).

Usa JDs alineados al perfil real de Lorena para forzar el camino del SÍ:
  Rama A — Consultoría / Brand Digital: "Digital Marketing Consultant" @ Accenture Colombia
  Rama B — Retail / Trade Marketing:    "Ecommerce & Digital Trade Marketing Mgr" @ Grupo Éxito
  Rama C — Paid Media:                  "Paid Media Manager" @ OMD Colombia

Assertions por canal:
  T1  Pipeline sin excepción
  T2  Score ≥ threshold de rama (A/B=85, C=75)
  T3  Status enviado o pendiente_envio (no descartado)
  T4  ATS score ≥ threshold_ats del perfil (A/B: 92%, C: 95%) en motivo
  T5  PDF generado y existe en disco
  T6  Nombre PDF sin placeholders
  T7  ORPHAN CLAIMs = 0 (no hallucination de USD)
  T8  Canal reportado en motivo

Uso:
  cd "C:\\Users\\lilia\\Clientes\\Lorena Ruiz\\JobAppAgent"
  python _smoke_happy_path_2026_05_19.py
"""
import os
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from main import _process_job
from agents.cv_parser import parse_cv


# ══════════════════════════════════════════════════════════════════════════════
# JOBs — Happy path, alineados al perfil real de Lorena
# ══════════════════════════════════════════════════════════════════════════════

# Rama A: Digital Marketing / Brand Strategy — keywords que Lorena tiene
_JOB_A_HAPPY = {
    "cargo":       "Digital Marketing Consultant Senior",
    "empresa":     "Accenture Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá, D.C., Colombia",
    "descripcion": (
        "Buscamos Digital Marketing Consultant Senior para liderar proyectos de "
        "transformación digital y estrategia de marca para clientes multinacionales. "
        "Responsabilidades: "
        "Diseñar e implementar estrategias de brand strategy y digital transformation "
        "para clientes del sector consumo masivo y retail. "
        "Gestionar campañas integrales en Meta Ads, Google Ads y plataformas digitales. "
        "Realizar data analysis y reporting de performance para C-suite. "
        "Liderar procesos de consultoría de marketing digital y ecommerce analytics. "
        "Desarrollar frameworks de medición y KPIs para optimización de inversión digital. "
        "Acompañar a clientes en estrategia de canales digitales y SEO/SEM. "
        "Gestionar presupuestos de medios USD 100K+ mensuales. "
        "Requisitos: "
        "Profesional en Marketing, Comunicación, Administración o afines. "
        "Mínimo 3 años de experiencia en consultoría digital o agencia. "
        "Dominio de Meta Ads, Google Ads, analytics y herramientas de data. "
        "Brand strategy y digital transformation como competencias core. "
        "Inglés C1 obligatorio (el rol implica interacción con clientes globales). "
        "Excelentes habilidades de comunicación y presentación a stakeholders."
    ),
    "url":  "https://www.linkedin.com/jobs/view/fake-accenture-a-001",
    "rama": "A",
}

# Rama B: Ecommerce + Digital Trade Marketing — puente con el perfil de Lorena
_JOB_B_HAPPY = {
    "cargo":       "Ecommerce & Digital Trade Marketing Manager",
    "empresa":     "Grupo Éxito",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá, D.C., Colombia",
    "descripcion": (
        "Buscamos Ecommerce & Digital Trade Marketing Manager para liderar la estrategia "
        "digital de trade marketing y ecommerce analytics del portafolio de marcas propias. "
        "Responsabilidades: "
        "Liderar la estrategia de trade marketing digital en canales ecommerce (marketplace y D2C). "
        "Gestionar campañas de Meta Ads, Google Ads y Amazon Ads orientadas a conversión retail. "
        "Analizar performance de categorías en plataformas digitales y construir dashboards de KPIs. "
        "Ejecutar activaciones de shopper marketing digital y campañas de performance en PDV digital. "
        "Gestionar presupuesto mensual de medios digitales USD 150K+ con foco en ROAS y CPA. "
        "Coordinar con equipos comerciales y de category management el plan de visibilidad digital. "
        "Desarrollar estrategias de SEM, SEO y paid media para mejorar tráfico y conversión. "
        "Construir reportes de ecommerce analytics para la gerencia comercial. "
        "Requisitos: "
        "Profesional en Marketing, Comunicación, Administración o afines. "
        "3+ años de experiencia en ecommerce, digital marketing o trade marketing digital. "
        "Dominio de Meta Ads, Google Ads, Amazon Ads y plataformas de analytics. "
        "Experiencia en gestión de campañas paid media y optimización de ROAS. "
        "Inglés B2+ deseable. Perfil analítico orientado a datos."
    ),
    "url":  "https://www.linkedin.com/jobs/view/fake-exito-b-001",
    "rama": "B",
}

# Rama C: Paid Media Manager — idéntico al perfil más fuerte de Lorena (OMD pattern)
_JOB_C_HAPPY = {
    "cargo":       "Paid Media Manager",
    "empresa":     "OMD Colombia",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "descripcion": (
        "Buscamos Paid Media Manager con experiencia en Meta Ads, Google Ads, "
        "Amazon Ads y LinkedIn Ads. "
        "Planear y optimizar campañas de performance marketing y paid media en plataformas digitales. "
        "Gestión de presupuesto mensual USD 200K+. Optimizar ROAS, CPA y ACOS. "
        "Experiencia en programmatic advertising y Amazon DSP deseable. "
        "Inglés C1 requerido. SEM y data analysis."
    ),
    "url":  "https://www.linkedin.com/jobs/view/fake-omd-c-001",
    "rama": "C",
}

_JOBS = [
    ("A", _JOB_A_HAPPY, "Digital Marketing Consultant Senior — Accenture Colombia"),
    ("B", _JOB_B_HAPPY, "Ecommerce & Digital Trade Marketing Manager — Grupo Éxito"),
    ("C", _JOB_C_HAPPY, "Paid Media Manager — OMD Colombia"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers TDD
# ══════════════════════════════════════════════════════════════════════════════

def _chk(label: str, cond: bool, ok: str, fail: str, acc: list) -> bool:
    icon = "✅" if cond else "❌"
    msg  = ok if cond else fail
    print(f"    {icon} {label}: {msg}")
    acc.append({"label": label, "pass": cond, "detail": msg})
    return cond


def _extract_orphan_count(output_capture: str) -> int:
    """Cuenta líneas ORPHAN CLAIM en el output del proceso."""
    return output_capture.count("ORPHAN CLAIM:")


def _run_case(canal: str, job: dict, desc: str, cv: dict) -> dict:
    sep = "═" * 68
    print(f"\n{sep}")
    print(f"  HAPPY PATH — CANAL {canal} | {desc}")
    print(f"  Cargo:   {job['cargo']}")
    print(f"  Empresa: {job['empresa']}")
    print(f"  Rama:    {job['rama']}  | dry_run=True")
    print(sep)

    # Capturar stdout para detectar ORPHAN CLAIMs
    import io
    from contextlib import redirect_stdout, redirect_stderr
    buf = io.StringIO()

    t0 = time.time()
    assertions = []
    result = {}

    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            result = _process_job(cv, job, rama=job["rama"], dry_run=True)
        captured = buf.getvalue()
        # Re-imprimir en consola para visibilidad
        print(captured, end="")
    except Exception as exc:
        captured = buf.getvalue()
        print(captured, end="")
        tb = traceback.format_exc()
        print(f"  ❌ EXCEPCIÓN: {exc}\n{tb}")
        result = {"status": "error", "score": 0, "motivo": str(exc), "pdf": ""}

    elapsed  = round(time.time() - t0, 1)
    status   = result.get("status", "error")
    score    = result.get("score", 0)
    motivo   = result.get("motivo", "")
    pdf_path = result.get("pdf", "")

    print(f"\n  ── Assertions Canal {canal} (Happy Path) ──────────────────────")

    # T1: sin excepción
    _chk("T1 Pipeline", status != "error",
         "completó sin excepción",
         f"excepción: {motivo[:80]}",
         assertions)

    # T2: score ≥ threshold (leído del perfil JSON de la rama)
    import json as _json
    _profile_names = {
        "A": "perfil_a_consultoria.json",
        "B": "perfil_b_retail.json",
        "C": "perfil_c_paidmedia.json",
    }
    _profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "profiles", _profile_names[job["rama"]]
    )
    with open(_profile_path, encoding="utf-8") as _f:
        _perfil = _json.load(_f)
    threshold     = _perfil["threshold_match"]
    threshold_ats = _perfil["threshold_ats"]

    _chk("T2 Score matcher", score >= threshold,
         f"score={score}% ≥ {threshold}% ✓",
         f"score={score}% < {threshold}% — no pasó skill matching",
         assertions)

    # T3: status es enviado/pendiente (no descartado)
    _chk("T3 Happy path", status in ("enviado", "pendiente_envio"),
         f"status='{status}' — CV producido ✓",
         f"status='{status}' — debería ser enviado/pendiente_envio",
         assertions)

    # T4: ATS ≥ threshold_ats del perfil en motivo
    ats_match = re.search(r"ATS\s+(\d+)%", motivo, re.IGNORECASE)
    ats_val   = int(ats_match.group(1)) if ats_match else None
    if ats_val is not None:
        _chk(f"T4 ATS ≥ {threshold_ats}%", ats_val >= threshold_ats,
             f"ATS={ats_val}% ≥ {threshold_ats}% ✓",
             f"ATS={ats_val}% < {threshold_ats}% — CV no optimizado",
             assertions)
    else:
        _chk("T4 ATS en motivo", False, "",
             f"ATS score no encontrado en motivo: '{motivo[:60]}'",
             assertions)

    # T5: PDF existe en disco
    pdf_exists = bool(pdf_path) and os.path.exists(pdf_path)
    _chk("T5 PDF generado", pdf_exists,
         f"{os.path.basename(pdf_path)} ✓",
         f"PDF no generado: '{pdf_path}'",
         assertions)

    # T6: Nombre PDF sin placeholders
    if pdf_exists:
        bn = os.path.basename(pdf_path)
        no_ph = (
            "Cargo LinkedIn" not in bn
            and "Empresa LinkedIn" not in bn
            and bn.lower() != "lorena ruiz - cargo linkedin - empresa linkedin.pdf"
        )
        _chk("T6 Nombre PDF", no_ph,
             f"'{bn}' ✓",
             f"placeholder en nombre: '{bn}'",
             assertions)

    # T7: ORPHAN CLAIMs = 0
    orphan_count = _extract_orphan_count(captured)
    _chk("T7 Sin orphan claims", orphan_count == 0,
         "0 USD claims sin evidencia ✓",
         f"{orphan_count} ORPHAN CLAIM(s) detectados — posible hallucination",
         assertions)

    # T8: Canal en motivo
    canal_ok = any(k in motivo for k in
                   ["Canal A", "Canal B", "Canal C", "Easy Apply", "portal", "email",
                    "canal A", "canal B", "canal C"])
    _chk("T8 Canal en motivo", canal_ok,
         "canal de aplicación reportado ✓",
         f"canal no mencionado: '{motivo[:80]}'",
         assertions)

    passed = all(a["pass"] for a in assertions)
    n_pass = sum(a["pass"] for a in assertions)
    print(f"\n  Tiempo: {elapsed}s | {'✅ PASS' if passed else '❌ FAIL'} "
          f"({n_pass}/{len(assertions)} assertions)")

    return {
        "canal": canal,
        "cargo": job["cargo"],
        "empresa": job["empresa"],
        "score": score,
        "status": status,
        "motivo": motivo,
        "pdf": pdf_path,
        "ats_val": ats_val,
        "orphan_count": orphan_count,
        "assertions": assertions,
        "passed": passed,
        "elapsed_s": elapsed,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    banner = "═" * 68
    print(f"\n{banner}")
    print("  SMOKE TEST HAPPY PATH — 3 RAMAS (2026-05-19)")
    print("  TDD — Verifica redacción completa de CV en cada perfil de Lorena")
    print(banner)

    print("\nCargando CV desde PDF real...")
    try:
        cv = parse_cv()
        print(f"  CV listo: {cv['nombre']} | {len(cv.get('experiencia', []))} roles")
    except Exception as e:
        print(f"  ❌ ERROR cargando CV: {e}")
        sys.exit(1)

    t_total = time.time()
    resultados = []

    for canal, job, desc in _JOBS:
        r = _run_case(canal, job, desc, cv)
        resultados.append(r)

    total_elapsed = round(time.time() - t_total, 1)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n\n{'═'*68}")
    print("  RESUMEN HAPPY PATH — 3 RAMAS")
    print(f"{'═'*68}")

    total_pass = 0
    for r in resultados:
        verdict  = "✅ PASS" if r["passed"] else "❌ FAIL"
        n_pass   = sum(a["pass"] for a in r["assertions"])
        n_total  = len(r["assertions"])
        pdf_name = os.path.basename(r["pdf"]) if r["pdf"] else "(sin PDF)"

        print(f"\n  Rama {r['canal']} — {r['cargo']} @ {r['empresa']}")
        print(f"    Status:  {r['status']}  |  Score: {r['score']}%  |  ATS: {r['ats_val']}%")
        print(f"    Motivo:  {r['motivo'][:85]}")
        print(f"    PDF:     {pdf_name}")
        print(f"    Orphans: {r['orphan_count']} USD claims sin evidencia")
        print(f"    Tiempo:  {r['elapsed_s']}s")
        print(f"    Tests:   {n_pass}/{n_total} — {verdict}")

        if not r["passed"]:
            for a in r["assertions"]:
                if not a["pass"]:
                    print(f"      ❌ [{a['label']}] {a['detail']}")

        if r["passed"]:
            total_pass += 1

    total_fail = 3 - total_pass
    print(f"\n{'─'*68}")
    print(f"  TOTAL: {total_pass}/3 ramas PASS — {total_fail} FAIL — {total_elapsed}s")
    print(f"{'─'*68}")

    if total_fail == 0:
        print("\n  ✅ Happy path completo — CV rewriting funciona en los 3 perfiles.")
    else:
        print(f"\n  ❌ {total_fail} rama(s) con fallos — revisar arriba.")
    print()


if __name__ == "__main__":
    main()
