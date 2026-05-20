"""
Smoke test Nivel 3 — Canal A real con pipeline completo (Rama A — Consultoría).

Flujo:
  0. Skill Matching — CV vs JD, threshold 82%
  1. Extraer cargo, empresa y descripción de la URL de LinkedIn (Playwright breve)
  2. Reescribir CV adaptado a ese cargo (Claude API — puede tardar 2-4 min)
  3. Generar PDF del CV reescrito
  4. Aplicar via Easy Apply (Playwright + HITL Telegram)

Uso:
  python _smoke_canal_a.py                                     # URL por defecto
  python _smoke_canal_a.py <URL>                               # job específico
  python _smoke_canal_a.py <URL> --bypass-skill-match          # salta gate de score (solo para test de flujo)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.cv_parser import parse_cv
from agents.cv_rewriter import rewrite
from agents.pdf_generator import generate
from agents.applicator import apply, _extract_linkedin_job_info
from agents.skill_matcher import analyze as skill_match

# ── CLI args ─────────────────────────────────────────────────────────────────
_DEFAULT_URL = "https://co.linkedin.com/jobs/view/digital-marketing-account-manager-fully-remote-at-valatam-4413843121"
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
_flags = [a for a in sys.argv[1:] if a.startswith("--")]

TEST_URL  = _args[0] if _args else _DEFAULT_URL
TEST_RAMA = "A"   # A=Consultoría  B=Retail  C=Paid Media
BYPASS_SKILL_MATCH = "--bypass-skill-match" in _flags  # solo para validar flujo

# ─────────────────────────────────────────────────────────────────────────────

def _scrape_job_from_url(url: str) -> dict:
    """
    Abre la URL en el browser con sesión persistente, extrae cargo/empresa/JD,
    cierra el browser y retorna un dict de job.
    Sesión breve — el profile lock se libera antes de llamar apply().
    """
    from playwright.sync_api import sync_playwright
    job = {"url": url, "cargo": "", "empresa": "", "descripcion": "",
           "modalidad": "Híbrido", "ubicacion": "Bogotá D.C.", "rama": TEST_RAMA, "score": 90}
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                config.PLAYWRIGHT_USER_DATA_DIR,
                headless=False,
                slow_mo=300,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            print(f"  [Scrape] Navegando a {url}")
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            time.sleep(3)  # render completo de componentes LinkedIn

            # Hacer scroll para disparar lazy-loading de la descripción
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(0.5)
            except Exception:
                pass

            info = _extract_linkedin_job_info(page)
            job["cargo"]       = info["cargo"]       or "Cargo LinkedIn"
            job["empresa"]     = info["empresa"]      or "Empresa LinkedIn"
            job["descripcion"] = info["descripcion"]  or ""

            print(f"  [Scrape] Cargo:   {job['cargo']}")
            print(f"  [Scrape] Empresa: {job['empresa']}")
            print(f"  [Scrape] JD:      {len(job['descripcion'])} chars extraídos")
            ctx.close()
    except Exception as e:
        safe_msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  [Scrape] Error al extraer info: {safe_msg} — usando placeholders")
    return job


def main():
    print("=" * 60)
    print("SMOKE TEST — CANAL A (pipeline completo)")
    print("=" * 60)
    print(f"URL:    {TEST_URL}")
    print(f"Rama:   {TEST_RAMA}")
    print(f"HITL:   {'ACTIVADO (' + str(config.HITL_TIMEOUT_S // 60) + ' min)' if config.HITL_ENABLED else 'DESACTIVADO'}")
    print()

    # ── 0. Leer CV base ───────────────────────────────────────────────────────
    print("PASO 0 — Leyendo CV base desde PDF...")
    try:
        cv = parse_cv()
        print(f"  CV listo: {cv['nombre']} | {len(cv['experiencia'])} roles")
    except Exception as e:
        print(f"  ERROR parse_cv: {e}")
        sys.exit(1)
    print()

    # ── 1. Extraer info del cargo ─────────────────────────────────────────────
    print("PASO 1 — Extrayendo info del cargo desde LinkedIn...")
    job = _scrape_job_from_url(TEST_URL)
    job["rama"] = TEST_RAMA
    print()

    # ── 1b. Skill matching ────────────────────────────────────────────────────
    print(f"PASO 1b — Skill Matching (Rama A threshold 82%)"
          + (" [BYPASS ACTIVADO — solo test de flujo]" if BYPASS_SKILL_MATCH else "") + "...")
    try:
        match_result = skill_match(cv, job, rama=TEST_RAMA)
        score = match_result["score"]
        threshold = match_result["threshold"]
        passed = match_result["passed"]
        print(f"  Score: {score}% | Threshold: {threshold}% | Passed: {passed}")
        print(f"  Skills match ({len(match_result['skills_match'])}): {match_result['skills_match']}")
        print(f"  Skills gap  ({len(match_result['skills_gap'])}):   {match_result['skills_gap']}")
        print(f"  Razon: {match_result['reason']}")
        if not passed:
            if BYPASS_SKILL_MATCH:
                print(f"  [BYPASS] score {score}% < {threshold}% — continuando igualmente (modo test de flujo)")
            else:
                print(f"\n  [DESCARTADO] score {score}% < {threshold}% umbral Rama A")
                print("  Reemplaza la URL o usa --bypass-skill-match para test de flujo.")
                sys.exit(0)
        else:
            print(f"  [OK] PASA skill matching — continuando con CV rewriting")
        job["score"] = score
    except Exception as e:
        print(f"  ERROR skill_matcher: {e} — continuando con score manual 90%")
        job["score"] = 90
    print()

    # ── 2. Reescribir CV adaptado al cargo ────────────────────────────────────
    print(f"PASO 2 — Reescribiendo CV para '{job['cargo']}' @ '{job['empresa']}'...")
    print("  (Claude API — puede tardar 2-4 minutos)")
    try:
        rewrite_result = rewrite(cv, job, rama=TEST_RAMA)
        print(f"  ATS Score: {rewrite_result['ats_score']}% | "
              f"Intentos: {rewrite_result['attempts']} | "
              f"Pasa: {rewrite_result['passed_ats']}")
        if not rewrite_result["passed_ats"]:
            ats_thresh = rewrite_result.get("ats_threshold", "?")
            print(f"  ADVERTENCIA: ATS {rewrite_result['ats_score']}% < {ats_thresh}% — CV puede no estar optimizado")
    except Exception as e:
        print(f"  ERROR cv_rewriter: {e}")
        sys.exit(1)
    cv_text = rewrite_result["cv_text"]
    print()

    # ── 3. Generar PDF ────────────────────────────────────────────────────────
    print("PASO 3 — Generando PDF...")
    try:
        pdf_path = generate(cv_text, job)
        print(f"  PDF generado: {os.path.basename(pdf_path)}")
    except Exception as e:
        print(f"  ERROR pdf_generator: {e}")
        sys.exit(1)
    print()

    # ── 4. Aplicar — Easy Apply ───────────────────────────────────────────────
    print("PASO 4 — Aplicando via Canal A (Easy Apply)...")
    print("  Browser abriendo LinkedIn...")
    if config.HITL_ENABLED:
        print(f"  Telegram recibirá screenshot para aprobación ({config.HITL_TIMEOUT_S // 60} min timeout)")
    print()

    result = apply(
        job, pdf_path,
        dry_run=False,
        cv_text=cv_text,
        job_description=job.get("descripcion", ""),
    )

    # ── Resultado ─────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESULTADO FINAL:")
    print(f"  Cargo:   {job['cargo']} @ {job['empresa']}")
    print(f"  Canal:   {result['canal']}")
    print(f"  Enviado: {result['enviado']}")
    print(f"  Mensaje: {result['mensaje']}")
    print("=" * 60)
    print()
    print("Checklist de verificación:")
    print("  [ ] ¿Se extrajo cargo y empresa correctamente?")
    print("  [ ] ¿El CV reescrito menciona keywords del cargo?")
    print("  [ ] ¿El PDF generado se subió al formulario?")
    print("  [ ] ¿Se llenaron teléfono y email?")
    print("  [ ] ¿El campo de aspiración salarial aceptó el número? (sin error rojo)")
    print("  [ ] ¿Telegram recibió el screenshot de Review?")
    if config.HITL_ENABLED:
        print("  [ ] ¿Lorena respondió SI y se hizo submit?")
    else:
        print("  [ ] ¿Submit automático ejecutado?")
    print()
    if result["enviado"]:
        print("SMOKE TEST COMPLETO — CANAL A APROBADO")
    else:
        print("Smoke test completado — revisar checklist arriba")


if __name__ == "__main__":
    main()
