"""
Orquestador Principal — JobAppAgent
Coordina el pipeline completo para las 3 ramas en loop diario.

Flujo por cargo:
  Scraper -> Skill Matcher -> [passed?] -> CV Rewriter -> PDF -> Reporter (BD + Telegram)

Uso:
  python main.py          # ejecuta ahora + programa loop diario a las 08:00
  python main.py --once   # ejecuta una sola vez y sale
  python main.py --rama A # solo procesa Rama A
  python main.py --dry-run # usa datos mock (sin Apify)
"""
import argparse
import os
import sys
import traceback
from datetime import datetime

# Fix Unicode en terminales Windows (cp1252 no soporta emojis ni algunos caracteres LinkedIn)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import schedule
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.cv_parser    import parse_cv
from agents.scraper      import search_jobs
from agents.skill_matcher import analyze
from agents.cv_rewriter  import rewrite
from agents.ats_auditor  import audit, MAX_AUDIT_CYCLES
from agents.pdf_generator import generate
from agents.reporter     import register, send_daily_report, send_alert, get_daily_stats
from agents.applicator   import apply as aplicar
from agents.evidence_mapper import load_narrativas, build_evidence_map, POOR_FIT_THRESHOLD

RAMAS = ["A", "B", "C"]
HORA_DIARIA = "08:00"


# ── Pipeline por cargo ─────────────────────────────────────────────────────────

def _process_job(cv: dict, job: dict, rama: str, dry_run: bool = False) -> dict:
    """Procesa un cargo a través del pipeline completo. Retorna resumen del resultado."""
    resultado = {
        "cargo":   job["cargo"],
        "empresa": job["empresa"],
        "rama":    rama,
        "score":   0,
        "status":  "descartado",
        "motivo":  "",
        "pdf":     "",
    }

    # 1. Skill Matching
    try:
        match = analyze(cv, job, rama)
        resultado["score"] = match["score"]
    except Exception as e:
        resultado["motivo"] = f"Error en skill_matcher: {e}"
        return resultado

    if not match["passed"]:
        resultado["motivo"] = f"Score bajo ({match['score']}% < {match['threshold']}%)"
        print(f"  [SKIP] {job['cargo']} @ {job['empresa']} — {resultado['motivo']}")
        register(job, match, "", resultado="Fallido")
        return resultado

    # 1b. Evidence map — construir ANTES del rewrite para evitar llamada duplicada a Claude.
    #     Si tier3_count > POOR_FIT_THRESHOLD: poor_fit early exit (ahorra el ciclo de rewrite).
    #     Si falla: continúa con evidence_map=None (rewrite usa fallback interno).
    evidence_map = None
    try:
        narrativas = load_narrativas()
        if narrativas and job.get("descripcion"):
            evidence_map = build_evidence_map(job["descripcion"], narrativas)
            tier3_count = sum(1 for v in evidence_map.values() if v["tier"] == 3)
            print(
                f"  [EvidenceMap] {len(evidence_map)} skills — "
                f"{sum(1 for v in evidence_map.values() if v['tier'] == 1)} T1, "
                f"{sum(1 for v in evidence_map.values() if v['tier'] == 2)} T2, "
                f"{tier3_count} T3"
            )
            if tier3_count > POOR_FIT_THRESHOLD:
                resultado["motivo"] = (
                    f"Poor fit: {tier3_count} skills del JD sin evidencia "
                    f"(skill_score {match['score']}%)"
                )
                print(f"  [POOR FIT] {job['cargo']} @ {job['empresa']} — {resultado['motivo']}")
                register(job, match, "", resultado="Fallido")
                return resultado
    except Exception as e:
        print(f"  [EvidenceMap] Error — continuando sin mapa: {e}")
        evidence_map = None

    # 2. CV Rewriting + ATS Audit loop
    audit_result    = None
    rewrite_result  = None
    audit_feedback  = ""
    previous_cv_text = ""    # CV del ciclo anterior — base para el siguiente

    for cycle in range(1, MAX_AUDIT_CYCLES + 1):
        # 2a. Rewrite — construye sobre el CV mejorado del ciclo anterior
        try:
            rewrite_result = rewrite(
                cv, job, rama,
                auditor_feedback=audit_feedback,
                previous_cv_text=previous_cv_text,
                evidence_map=evidence_map,
            )
        except Exception as e:
            resultado["motivo"] = f"Error en cv_rewriter (ciclo {cycle}): {e}"
            register(job, match, "", resultado="Fallido")
            return resultado

        # En ciclos 2+, el CV ya pasó ATS en el ciclo anterior — no bloquear por re-evaluación
        if not rewrite_result["passed_ats"] and cycle == 1:
            if rewrite_result.get("poor_fit"):
                resultado["motivo"] = (
                    f"Poor fit: {rewrite_result['poor_fit_reason']} "
                    f"(ATS {rewrite_result['ats_score']}%)"
                )
            else:
                resultado["motivo"] = (
                    f"ATS score bajo ({rewrite_result['ats_score']}% "
                    f"tras {rewrite_result['attempts']} intentos)"
                )
            print(f"  [ATS FAIL] {job['cargo']} — {resultado['motivo']}")
            register(job, match, "", resultado="Fallido")
            return resultado

        # 2b. Auditoría independiente (Haiku hostil, cross-reference oferta↔CV)
        print(f"  [Auditor] Ciclo {cycle}/{MAX_AUDIT_CYCLES} — evaluando {job['cargo']}")
        try:
            audit_result = audit(job, rewrite_result["cv_text"])
        except Exception as e:
            print(f"  [Auditor] Error en ciclo {cycle}: {e} — omitiendo auditoría")
            break   # si el auditor falla, aceptamos el CV del rewriter

        score_str = f"ATS {rewrite_result['ats_score']}% | Audit {audit_result['audit_score']}%"
        print(f"  [Auditor] {audit_result['verdict']} — {score_str}")

        if audit_result["passed_audit"]:
            break   # PASS → salir del loop y generar PDF

        if cycle == MAX_AUDIT_CYCLES:
            # Agotados los ciclos → alerta y continuar con el mejor CV disponible
            msg = (
                f"[JobAppAgent] ALERTA: {MAX_AUDIT_CYCLES} ciclos sin PASS para "
                f"{job['cargo']} @ {job['empresa']} — {score_str}\n"
                f"Keywords ausentes: {', '.join(audit_result.get('keywords_missing', []))}"
            )
            print(f"  [Auditor] {msg}")
            try:
                send_alert(msg)
            except Exception:
                pass
            break

        # Preparar feedback + base para el siguiente ciclo
        previous_cv_text = rewrite_result["cv_text"]   # construir sobre el mejor CV
        missing = ", ".join(audit_result.get("keywords_missing", []))
        audit_feedback = (
            f"INDEPENDENT AUDIT SCORE: {audit_result['audit_score']}% "
            f"— {audit_result['verdict']}.\n"
            f"Keywords missing from the offer: {missing}.\n"
            f"Specific feedback:\n{audit_result['feedback_to_rewriter']}"
        )

    # 3. Generar PDF
    try:
        pdf_path = generate(rewrite_result["cv_text"], job)
        resultado["pdf"] = pdf_path
    except Exception as e:
        resultado["motivo"] = f"Error en pdf_generator: {e}"
        register(job, match, "", resultado="Fallido")
        return resultado

    # 4. Aplicar — determina canal y envía
    try:
        apply_result = aplicar(
            job, pdf_path,
            dry_run=dry_run,
            cv_text=rewrite_result["cv_text"],
            job_description=job.get("descripcion", ""),
        )
        canal        = apply_result["canal"]
        final_status = "Enviado" if apply_result["enviado"] else "Pendiente"
        print(f"  [Applicator] Canal {canal} — {apply_result['mensaje']}")
    except Exception as e:
        apply_result = {"enviado": False, "canal": "A", "mensaje": str(e)}
        canal        = "A"
        final_status = "Pendiente"
        print(f"  [Applicator] Error: {e} — marcando como Pendiente")

    # 5. Registrar resultado final en BD
    register(job, match, pdf_path, resultado=final_status, status_aplicacion=canal)

    resultado["status"] = "enviado" if final_status == "Enviado" else "pendiente_envio"
    resultado["motivo"]  = (
        f"Score {match['score']}% | ATS {rewrite_result['ats_score']}% | "
        f"Canal {canal} — {apply_result['mensaje']}"
    )
    print(
        f"  [OK] {job['cargo']} @ {job['empresa']} "
        f"— {final_status} | canal {canal} | score {match['score']}%"
    )
    return resultado


# ── Ciclo de una rama ──────────────────────────────────────────────────────────

def _run_rama(cv: dict, rama: str, dry_run: bool, limit: int | None = None) -> list[dict]:
    rama_nombres = {"A": "Consultoria", "B": "Retail", "C": "Paid Media"}
    print(f"\n{'='*50}")
    print(f"RAMA {rama} — {rama_nombres.get(rama, rama)}")
    print(f"{'='*50}")

    try:
        jobs = search_jobs(rama, dry_run=dry_run, limit=limit)
    except Exception as e:
        print(f"  [ERROR Scraper] {e}")
        return []

    if not jobs:
        print("  Sin cargos nuevos.")
        return []

    resultados = []
    for job in jobs:
        print(f"\n  Procesando: {job['cargo']} @ {job['empresa']}")
        r = _process_job(cv, job, rama, dry_run=dry_run)
        resultados.append(r)

    return resultados


# ── Ejecución completa del día ─────────────────────────────────────────────────

def run_daily(ramas: list[str] | None = None, dry_run: bool = False, limit: int | None = None) -> None:
    start = datetime.now()
    print(f"\n{'#'*55}")
    print(f"# JobAppAgent — {start.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*55}")

    # Cargar CV una sola vez (se cachea en memoria para toda la sesión)
    print("\nCargando CV...")
    try:
        cv = parse_cv()
        print(f"CV listo: {cv['nombre']} | {len(cv['experiencia'])} roles")
    except Exception as e:
        msg = f"Error fatal al cargar CV: {e}"
        print(msg)
        try:
            send_alert(f"[JobAppAgent] ERROR FATAL: {msg}")
        except Exception:
            pass
        return

    ramas_a_procesar = ramas or RAMAS
    todos_resultados = []

    for rama in ramas_a_procesar:
        try:
            r = _run_rama(cv, rama, dry_run=dry_run, limit=limit)
            todos_resultados.extend(r)
        except Exception:
            print(f"  [ERROR] Rama {rama} falló inesperadamente:")
            traceback.print_exc()

    elapsed = (datetime.now() - start).seconds
    print(f"\nEjecucion completada en {elapsed}s")

    # Reporte final
    stats = get_daily_stats()
    print(f"\n--- RESUMEN ---")
    print(f"Exitosas: {len(stats['exitosas'])} | Fallidas: {len(stats['fallidas'])} | Pendientes: {len(stats['pendientes'])}")

    try:
        send_daily_report(stats)
    except RuntimeError as e:
        print(f"[Telegram] No configurado: {e}")
    except Exception as e:
        print(f"[Telegram] Error al enviar reporte: {e}")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler(ramas: list[str] | None, dry_run: bool, limit: int | None = None) -> None:
    print(f"Scheduler activo — ejecutara diariamente a las {HORA_DIARIA}")
    print("Ctrl+C para detener.\n")

    schedule.every().day.at(HORA_DIARIA).do(run_daily, ramas=ramas, dry_run=dry_run, limit=limit)

    # Ejecutar inmediatamente en el arranque
    run_daily(ramas=ramas, dry_run=dry_run, limit=limit)

    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JobAppAgent Orchestrator")
    parser.add_argument("--once",    action="store_true", help="Ejecuta una vez y sale")
    parser.add_argument("--rama",    type=str,            help="Solo procesa rama A, B o C")
    parser.add_argument("--dry-run", action="store_true", help="Usa datos mock sin llamar Apify")
    parser.add_argument("--limit",   type=int, default=None, help="Limita N cargos por rama")
    args = parser.parse_args()

    ramas_arg = [args.rama.upper()] if args.rama else None

    if args.once:
        run_daily(ramas=ramas_arg, dry_run=args.dry_run, limit=args.limit)
    else:
        start_scheduler(ramas=ramas_arg, dry_run=args.dry_run, limit=args.limit)
