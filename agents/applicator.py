"""
Applicator — Agente 5
Determina el canal de aplicación y ejecuta el envío del CV.

Canales:
  A: LinkedIn Easy Apply (Playwright headful con perfil persistente de sesión)
  B: Web empresa (abre navegador headful en la URL — aplicación semi-manual)
  C: Email draft (abre cliente de correo con mailto:)

En dry_run=True simula la acción sin abrir navegador.

Input:  job (dict), pdf_path (str), dry_run (bool)
Output: {"enviado": bool, "canal": str, "url": str, "mensaje": str}
"""
import os
import sys
import time
import random
import urllib.parse
import subprocess
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import anthropic as anthropic
except ImportError:
    anthropic = None  # Usado solo en Canal C LLM body y Canal A smart fill

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # Playwright opcional — dry_run funciona sin él

try:
    from agents.telegram_hitl import (
        send_cv_ready_email,
        send_cv_ready_browser,
        send_email_body,
        send_screenshot_for_approval_sync,
        wait_for_approval,
    )
except ImportError:
    def send_cv_ready_email(jobs):  # noqa: E301
        pass
    def send_cv_ready_browser(jobs, timeout_min=5):  # noqa: E301
        pass
    def send_email_body(job, body_text):  # noqa: E301
        pass
    def send_screenshot_for_approval_sync(image_path, job):  # noqa: E301
        pass
    def wait_for_approval(timeout_s=300):  # noqa: E301
        return True

# Sitios de empleo → canal B (portal empresa, no LinkedIn)
_WEB_JOB_SITES = (
    "elempleo.com",
    "computrabajo.com",
    "indeed.com",
    "glassdoor.com",
    "bumeran.com",
    "multitrabajos.com",
)

# Tiempo máximo de espera por elemento (ms)
_TIMEOUT_MS = 15_000
# Pausa máxima entre acciones para simular comportamiento humano (segundos)
_MAX_HUMAN_DELAY_S = 1.5


# ── Helpers internos ───────────────────────────────────────────────────────────

def _detect_channel(url: str) -> str:
    """Determina el canal a partir de la URL de la oferta."""
    url_lower = url.lower()
    if "linkedin.com" in url_lower:
        return "A"
    if any(site in url_lower for site in _WEB_JOB_SITES):
        return "B"
    return "C"


def _human_pause(min_s: float = 0.3, max_s: float = _MAX_HUMAN_DELAY_S) -> None:
    """Pausa aleatoria para simular comportamiento humano."""
    time.sleep(random.uniform(min_s, max_s))


def _screenshot_on_error(page, context: str) -> str | None:
    """Guarda screenshot en output/ y retorna la ruta. Silencia errores."""
    try:
        shots_dir = os.path.join(config.BASE_DIR, "screenshots")
        os.makedirs(shots_dir, exist_ok=True)
        ts = int(time.time())
        path = os.path.join(shots_dir, f"applicator_error_{context}_{ts}.png")
        page.screenshot(path=path)
        return path
    except Exception:
        return None


# ── Canal A: LinkedIn Easy Apply ──────────────────────────────────────────────

def _get_field_question(page, field) -> str:
    """
    Extrae el texto de la pregunta asociada a un campo de formulario.
    Prioridad: placeholder → aria-label → label en DOM → cadena vacía.
    Nunca lanza excepción.
    """
    try:
        ph = field.get_attribute("placeholder", timeout=1_000) or ""
        if ph.strip():
            return ph.strip()
        aria = field.get_attribute("aria-label", timeout=1_000) or ""
        if aria.strip():
            return aria.strip()
        # Intentar buscar un <label> asociado por el 'id' del campo
        fid = field.get_attribute("id", timeout=1_000) or ""
        if fid:
            try:
                label = page.locator(f"label[for='{fid}']").first
                if label.is_visible(timeout=1_000):
                    txt = label.text_content(timeout=1_000) or ""
                    if txt.strip():
                        return txt.strip()
            except Exception:
                pass
        return ""
    except Exception:
        return ""


def _generate_field_answer(question: str, cv_text: str, job_description: str) -> str:
    """
    Llama a Claude para generar una respuesta a un campo de texto libre.
    Usa ÚNICAMENTE información del CV — no inventa hechos.
    Máximo 150 caracteres.
    Retorna cadena vacía si anthropic no está disponible.
    """
    if anthropic is None:
        return ""

    prompt = (
        f"You are Lorena Ruiz. Answer this application form question in one or two sentences. "
        f"Use ONLY facts from the CV. Do NOT invent metrics or experience.\n\n"
        f"QUESTION: {question}\n\n"
        f"CV (use this as your only source):\n{cv_text[:2000]}\n\n"
        f"JOB DESCRIPTION (for context):\n{job_description[:1000]}\n\n"
        f"Answer (max 150 characters, no quotes):"
    )
    try:
        client   = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.MODEL_FAST,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip()
        return answer[:150]
    except Exception as e:
        print(f"  [Applicator-A] _generate_field_answer error: {e}")
        return ""


def _fill_free_text_fields(page, cv_text: str, job_description: str) -> int:
    """
    Detecta campos de texto libre visibles y vacíos en la página actual y
    los llena con respuestas generadas por Claude.

    Retorna el número de campos llenados.
    Nunca lanza excepción — errores de Playwright se silencian.
    Si anthropic no está disponible, retorna 0 sin tocar la página.
    """
    if anthropic is None:
        return 0

    filled = 0
    try:
        selector = "textarea, input[type='text']:not([name*='phone']):not([name*='email'])"
        fields = page.locator(selector).all()
        for field in fields:
            try:
                if not field.is_visible(timeout=1_000):
                    continue
                current_val = field.input_value() or field.text_content() or ""
                if current_val.strip():
                    continue  # campo ya tiene contenido — no tocar
                question = _get_field_question(page, field)
                if not question:
                    continue  # sin pregunta identificable — saltar
                answer = _generate_field_answer(question, cv_text, job_description)
                if answer:
                    field.fill(answer)
                    _human_pause(0.3, 0.8)
                    print(f"  [Applicator-A] Campo llenado: {question[:50]!r} → {answer[:50]!r}")
                    filled += 1
            except Exception:
                continue
    except Exception:
        pass
    return filled


def _apply_linkedin(job: dict, pdf_path: str,
                    cv_text: str = "", job_description: str = "") -> dict:
    """
    Intenta LinkedIn Easy Apply con Playwright headful.

    Flujo:
      1. Abre navegador con perfil persistente (sesión guardada).
      2. Navega a la URL del cargo.
      3. Hace clic en Easy Apply.
      4. Completa cada paso: CV upload, campos simples, smart fill de texto libre.
      5. En la página Review/Submit:
           - HITL_ENABLED=True: screenshot → Telegram → espera SI/NO → submit o cancela.
           - HITL_ENABLED=False: submit directo.

    Si cualquier paso falla o aparece un formulario inesperado, deja el
    navegador abierto 60s para que Lorena complete manualmente y devuelve
    "enviado=False" para que el orquestador lo marque como Pendiente.
    """
    from playwright.sync_api import TimeoutError as PwTimeout

    url    = job.get("url", "")
    cargo  = job.get("cargo", "")
    empresa = job.get("empresa", "")

    print(f"  [Applicator-A] Abriendo LinkedIn: {cargo} @ {empresa}")

    with sync_playwright() as p:
        # Perfil persistente: mantiene cookies y sesión de LinkedIn
        os.makedirs(config.PLAYWRIGHT_USER_DATA_DIR, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_USER_DATA_DIR,
            headless=False,
            slow_mo=400,
            viewport={"width": 1280, "height": 800},
            args=["--start-maximized"],
        )

        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            # ── 1. Navegar al cargo ──────────────────────────────────────────
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            _human_pause()

            # ── 2. Verificar que la página cargó (no es login wall) ─────────
            if "linkedin.com/login" in page.url or "authwall" in page.url:
                print("  [Applicator-A] Sin sesión activa. Inicia sesión manualmente y re-ejecuta.")
                _screenshot_on_error(page, "no_session")
                ctx.close()
                return {
                    "enviado": False,
                    "canal": "A",
                    "url": url,
                    "mensaje": "Sin sesión LinkedIn — inicia sesión en el navegador del perfil",
                }

            # ── 3. Easy Apply button ─────────────────────────────────────────
            # LinkedIn usa varios selectores según versión de página
            btn_selectors = [
                "button.jobs-apply-button",
                "button[data-job-id]",
                ".jobs-s-apply button",
                "button:has-text('Easy Apply')",
            ]
            easy_apply_btn = None
            for sel in btn_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=3_000):
                        easy_apply_btn = loc
                        break
                except Exception:
                    continue

            if easy_apply_btn is None:
                # Puede ser "Apply" externo (redirige a empresa) — tratar como canal B
                print("  [Applicator-A] No hay Easy Apply — redirigiendo a canal B (web empresa).")
                ctx.close()
                return _apply_web(job, pdf_path)

            _human_pause()
            easy_apply_btn.click()
            print("  [Applicator-A] Easy Apply abierto.")

            # ── 4. Esperar modal ─────────────────────────────────────────────
            modal_selectors = [
                ".jobs-easy-apply-modal",
                ".artdeco-modal",
                "[data-test-modal]",
            ]
            modal = None
            for sel in modal_selectors:
                try:
                    modal = page.locator(sel).first
                    modal.wait_for(state="visible", timeout=10_000)
                    break
                except Exception:
                    modal = None

            if modal is None:
                _screenshot_on_error(page, "no_modal")
                ctx.close()
                return {
                    "enviado": False, "canal": "A", "url": url,
                    "mensaje": "Modal Easy Apply no apareció",
                }

            # ── 5. Navegar pasos del formulario ──────────────────────────────
            max_steps = 10
            for step in range(max_steps):
                _human_pause(0.8, 1.5)
                print(f"  [Applicator-A] Paso {step + 1}")

                # a) Subir CV si hay campo de archivo
                _maybe_upload_cv(page, pdf_path)

                # b) Rellenar campos simples (teléfono, email)
                _fill_simple_fields(page)

                # c) Smart fill: campos de texto libre con Claude
                _fill_free_text_fields(page, cv_text, job_description)

                # d) Detectar si hay el botón Submit (último paso)
                submit_btn = page.locator(
                    "button[aria-label='Submit application'], "
                    "button:has-text('Submit application')"
                ).first
                if submit_btn.is_visible(timeout=2_000):
                    _human_pause(0.5, 1.0)

                    if config.HITL_ENABLED:
                        # HITL: screenshot → Telegram → esperar SI/NO
                        shot_path = _screenshot_on_error(page, "review")
                        send_screenshot_for_approval_sync(shot_path or "", job)
                        approved = wait_for_approval(config.HITL_TIMEOUT_S)
                        if approved:
                            submit_btn.click()
                            _human_pause(2.0, 3.0)
                            print("  [Applicator-A] Aplicación enviada (HITL aprobado).")
                            ctx.close()
                            return {
                                "enviado": True, "canal": "A", "url": url,
                                "mensaje": f"Easy Apply enviado: {cargo} @ {empresa}",
                            }
                        else:
                            print("  [Applicator-A] HITL cancelado — browser abierto para completar manualmente.")
                            try:
                                page.wait_for_event("close", timeout=config.HITL_TIMEOUT_S * 1_000)
                            except Exception:
                                pass
                            ctx.close()
                            return {
                                "enviado": False, "canal": "A", "url": url,
                                "mensaje": "HITL cancelado — completar manualmente",
                            }
                    else:
                        # Sin HITL: submit directo
                        submit_btn.click()
                        _human_pause(2.0, 3.0)
                        print("  [Applicator-A] Aplicación enviada (sin HITL).")
                        _screenshot_on_error(page, "submitted")
                        ctx.close()
                        return {
                            "enviado": True, "canal": "A", "url": url,
                            "mensaje": f"Easy Apply enviado: {cargo} @ {empresa}",
                        }

                # e) Buscar botón Next / Review
                next_btn = _find_next_button(page)
                if next_btn is None:
                    # Formulario con preguntas no esperadas — dejar abierto
                    print("  [Applicator-A] Formulario inesperado — deja el navegador abierto para completar manualmente.")
                    try:
                        page.wait_for_event("close", timeout=300_000)
                    except Exception:
                        pass
                    ctx.close()
                    return {
                        "enviado": False, "canal": "A", "url": url,
                        "mensaje": "Formulario con preguntas adicionales — completar manualmente",
                    }

                next_btn.click()

            # Si llegamos aquí, agotamos los pasos sin submit
            _screenshot_on_error(page, "max_steps")
            ctx.close()
            return {
                "enviado": False, "canal": "A", "url": url,
                "mensaje": "Demasiados pasos en el formulario Easy Apply",
            }

        except PwTimeout as e:
            _screenshot_on_error(page, "timeout")
            ctx.close()
            return {
                "enviado": False, "canal": "A", "url": url,
                "mensaje": f"Timeout en LinkedIn Easy Apply: {e}",
            }
        except Exception as e:
            _screenshot_on_error(page, "error")
            ctx.close()
            return {
                "enviado": False, "canal": "A", "url": url,
                "mensaje": f"Error inesperado en LinkedIn Easy Apply: {e}",
            }


def _maybe_upload_cv(page, pdf_path: str) -> None:
    """Sube el PDF si hay un campo de archivo visible en la página actual."""
    if not pdf_path or not os.path.exists(pdf_path):
        return
    selectors = [
        ".jobs-document-upload__input",
        "input[type='file'][name*='resume']",
        "input[type='file']",
    ]
    for sel in selectors:
        try:
            inp = page.locator(sel).first
            if inp.is_visible(timeout=1_500):
                inp.set_input_files(pdf_path)
                _human_pause(0.5, 1.0)
                print(f"  [Applicator-A] CV subido: {os.path.basename(pdf_path)}")
                return
        except Exception:
            continue


def _fill_simple_fields(page) -> None:
    """Rellena campos comunes de contacto si están vacíos."""
    fields = [
        ("input[name*='phone'], input[placeholder*='Phone'], input[id*='phone']", config.APPLICANT_PHONE),
        ("input[name*='email'], input[placeholder*='Email'], input[id*='email']", config.APPLICANT_EMAIL),
    ]
    for selector, value in fields:
        try:
            field = page.locator(selector).first
            if field.is_visible(timeout=1_000) and not field.input_value():
                field.fill(value)
                _human_pause(0.3, 0.7)
        except Exception:
            continue


def _find_next_button(page):
    """Retorna el botón Next / Review / Continue si está visible."""
    labels = [
        "Continue to next step",
        "Review your application",
        "Next",
        "Continue",
    ]
    for label in labels:
        try:
            btn = page.locator(
                f"button[aria-label='{label}'], button:has-text('{label}')"
            ).first
            if btn.is_visible(timeout=1_500):
                return btn
        except Exception:
            continue
    return None


# ── Canal B: Web empresa (headful semi-manual) ────────────────────────────────

def _click_apply_button(page) -> bool:
    """
    Intenta hacer click en el botón Apply/Aplicar/Postularme de la página.
    Prueba selectores comunes en portales hispanohablantes y en inglés.
    Retorna True si encontró y clickeó el botón, False si no encontró ninguno.
    Nunca lanza excepción — errores de Playwright se silencian internamente.
    """
    selectors = [
        "button:has-text('Aplicar')",
        "button:has-text('Apply')",
        "button:has-text('Postularme')",
        "button:has-text('Postulate')",
        "button:has-text('Aplicarme')",
        "a:has-text('Aplicar')",
        "a:has-text('Apply')",
        "button[class*='apply']",
        "a[class*='apply']",
        ".apply-button",
        "#apply-button",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                _human_pause(0.5, 1.0)
                loc.click()
                print(f"  [Applicator-B] Botón clickeado: {sel}")
                return True
        except Exception:
            continue
    print("  [Applicator-B] No se encontró botón Apply — Lorena navega manualmente.")
    return False


def _apply_web(job: dict, pdf_path: str) -> dict:
    """
    Abre el portal de empleo en browser headful, intenta clickear Apply
    y notifica a Lorena por Telegram para que complete el formulario.

    Lorena tiene HITL_TIMEOUT_S segundos para completar y cerrar el browser.
    Nunca hace submit automático.
    """
    url         = job.get("url", "")
    cargo       = job.get("cargo", "")
    empresa     = job.get("empresa", "")
    timeout_min = config.HITL_TIMEOUT_S // 60

    print(f"  [Applicator-B] Abriendo portal: {cargo} @ {empresa}")
    print(f"  URL: {url}")
    print(f"  CV para subir: {pdf_path}")

    # Notificación Telegram ANTES de abrir Playwright — asyncio.run() no puede
    # ejecutarse dentro del event loop interno de Playwright sync API.
    try:
        send_cv_ready_browser([{**job}], timeout_min=timeout_min)
    except Exception as e:
        print(f"  [Applicator-B] Telegram no enviado: {e}")

    with sync_playwright() as p:
        os.makedirs(config.PLAYWRIGHT_USER_DATA_DIR, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_USER_DATA_DIR,
            headless=False,
            slow_mo=200,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page() if not ctx.pages else ctx.pages[0]
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        _human_pause(1.0, 2.0)

        # Intentar click automático en Apply
        clicked = _click_apply_button(page)

        if clicked:
            msg = (f"Botón Apply clickeado. Completa el formulario "
                   f"en {timeout_min} min y cierra el browser.")
        else:
            msg = (f"Browser abierto. Navega a Apply manualmente, "
                   f"completa en {timeout_min} min y cierra.")

        print(f"  [Applicator-B] {msg}")
        print(f"  CV disponible en: {pdf_path}")

        try:
            page.wait_for_event("close", timeout=config.HITL_TIMEOUT_S * 1_000)
        except Exception:
            pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    return {
        "enviado": False,
        "canal":   "B",
        "url":     url,
        "mensaje": f"{msg} | CV: {os.path.basename(pdf_path)}",
    }


def _apply_web_in_browser(page, job: dict, pdf_path: str, ctx) -> dict:
    """Versión interna que reutiliza un browser ya abierto."""
    url = job.get("url", "")
    try:
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        print(f"  [Applicator-B] Redirigido a web empresa. Completa manualmente.")
        time.sleep(60)
    finally:
        if ctx:
            ctx.close()
    return {
        "enviado": False,
        "canal": "B",
        "url": url,
        "mensaje": f"Web empresa abierta para aplicación manual: {job.get('cargo')} @ {job.get('empresa')}",
    }


# ── Canal C: Email draft ───────────────────────────────────────────────────────

def _generate_email_body(job: dict, cv_text: str, job_description: str) -> str:
    """
    Genera un cuerpo de correo profesional usando Claude Haiku.

    Reglas de curación:
    - Detecta el idioma del job description y responde en ese mismo idioma.
    - Usa ÚNICAMENTE información del CV tailored — no inventa hechos.
    - Máx. 200 palabras. Menciona 2-3 keywords del JD que coinciden con el CV.
    - No incluye subject, saludo ni cierre — solo el cuerpo + firma.

    Si anthropic no está disponible, retorna body estático coherente.
    """
    if anthropic is None:
        cargo   = job.get("cargo", "")
        empresa = job.get("empresa", "")
        return (
            f"Me dirijo a ustedes para postularme al cargo de {cargo} en {empresa}.\n\n"
            f"Adjunto mi CV adaptado para esta posición y quedo atenta a cualquier "
            f"información adicional que requieran.\n\n"
            f"Lorena Ruiz\n"
            f"Bogotá D.C. | lilian@lorena-ruiz.com | +57 315 256 1884 | www.linkedin.com/in/lilianlorenarui"
        )

    cargo      = job.get("cargo", "")
    empresa    = job.get("empresa", "")
    jd_excerpt = (job_description or f"Position: {cargo} at {empresa}")[:2000]
    cv_excerpt = (cv_text or "")[:2500]

    prompt = (
        f"Write a job application email body. You are Lorena Ruiz writing in first person.\n\n"
        f"JOB DESCRIPTION:\n{jd_excerpt}\n\n"
        f"TAILORED CV (plain text):\n{cv_excerpt}\n\n"
        f"REFERENCE EXAMPLE — match this tone, structure, and level of specificity exactly:\n"
        f"---\n"
        f"Tengo 14 años en marketing digital con experiencia directa en gestión de campañas "
        f"de performance en Meta Ads, Google Ads, Amazon Ads y LinkedIn Ads. En los últimos "
        f"meses he optimizado portafolios superiores a USD 240,000 mensuales para cuentas B2B "
        f"en US Market, midiendo ROAS, CPC y CTR para maximizar rendimiento. Mi diferenciador "
        f"es que domino Amazon DSP a nivel operativo y estratégico, combinado con experiencia "
        f"comprobada en LinkedIn Ads.\n\n"
        f"Actualmente manejo 300 cuentas B2B enterprise en LinkedIn con presupuesto mensual de "
        f"USD 240,000, cumpliendo exactamente dos de sus requisitos críticos: manejo de "
        f"presupuestos superiores a USD 50K mensuales y optimización full-funnel en performance. "
        f"Mi certificación EF SET en inglés (C2) también cubre el requisito de nivel avanzado.\n\n"
        f"Coordinemos una entrevista y conversamos juntos sobre cómo puedo poner esta experiencia "
        f"al servicio de los resultados de sus clientes y del PyG de la empresa.\n"
        f"---\n\n"
        f"WHAT MAKES THIS EXAMPLE WORK — replicate these qualities:\n"
        f"- Opens with years + specific platforms relevant to THIS job. No generic opener.\n"
        f"- Includes a real budget figure from the CV as proof.\n"
        f"- Names one clear differentiator (what sets Lorena apart).\n"
        f"- P2 says explicitly which JD requirements she meets and names them.\n"
        f"- Closing starts with 'Coordinemos': collaborative, action-oriented, warm.\n"
        f"- Every sentence earns its place. No filler.\n\n"
        f"STRUCTURE — 3 short paragraphs:\n"
        f"  P1: Experience + specific platforms from THIS JD + one clear differentiator.\n"
        f"  P2: One concrete metric from the CV + name 2 specific JD requirements I meet exactly.\n"
        f"  P3: 'Coordinemos una entrevista y conversamos juntos sobre cómo puedo poner esta "
        f"experiencia al servicio de los resultados de sus clientes y del PyG de la empresa.' "
        f"If the JD is in English, adapt the spirit: "
        f"'Let's set up an interview and talk about how I can put this experience to work for your clients and your P&L.'\n\n"
        f"TONE:\n"
        f"- First person throughout (I, me, my). I am writing this email myself.\n"
        f"- Business casual. Direct. Human. Short sentences.\n"
        f"- Active voice. Show results, not duties.\n"
        f"- No metaphors, clichés, or generalizations.\n\n"
        f"FORMATTING RULES (strictly enforced):\n"
        f"- No em-dashes anywhere. Use commas, periods, or colons instead.\n"
        f"- No semicolons.\n"
        f"- No bullet points or lists.\n"
        f"- No markdown, no asterisks, no hashtags.\n"
        f"- No closing phrases like 'en conclusión', 'para cerrar', 'in summary', 'to conclude'.\n"
        f"- No unnecessary adjectives.\n"
        f"- No constructions like 'not only X but also Y'.\n\n"
        f"BANNED WORDS — do not use any of these:\n"
        f"poder, quizás, solo, realmente, literalmente, ciertamente, probablemente, básicamente, "
        f"significativamente, transformar, estimado, potenciar, desafío, desbloquear, descubrir, "
        f"revolucionar, disruptivo, pionero, innovador, revelar, vibrante, vital, crucial, además, "
        f"sin embargo, aprovechar, navegar, notable, en resumen, en conclusión, poderoso, "
        f"en constante evolución, llevar al siguiente nivel, leverage, synergy, passionate.\n\n"
        f"HARD RULES:\n"
        f"1. Detect the language of the job description (Spanish or English) and write "
        f"the ENTIRE body in that SAME language.\n"
        f"2. Write the body only. No subject line. No greeting. No sign-off.\n"
        f"3. Maximum 150 words (body only, not counting the signature).\n"
        f"4. Do NOT invent facts, metrics, or experience not present in the CV.\n"
        f"5. End with this exact signature block, unchanged:\n"
        f"Lorena Ruiz\n"
        f"Bogotá D.C. | lilian@lorena-ruiz.com | +57 315 256 1884 | www.linkedin.com/in/lilianlorenarui\n\n"
        f"Write the email body now:"
    )

    client   = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

def _apply_email(job: dict, pdf_path: str,
                 cv_text: str = "", job_description: str = "") -> dict:
    """
    Genera body de correo con Claude (coherente con CV + JD), abre el cliente
    de correo y notifica a Lorena por Telegram.

    Lorena debe adjuntar el PDF manualmente y enviar.
    """
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    url     = job.get("url", "")

    # 1. Generar body curado con Claude
    print(f"  [Applicator-C] Generando cuerpo de correo para: {cargo} @ {empresa}")
    try:
        body_text = _generate_email_body(job, cv_text, job_description)
    except Exception as e:
        print(f"  [Applicator-C] Error LLM — usando fallback: {e}")
        body_text = (
            f"Me dirijo a ustedes para postularme al cargo de {cargo} en {empresa}.\n\n"
            f"Adjunto mi CV adaptado para esta posición.\n\n"
            f"Referencia: {url}\n\n"
            f"Lorena Ruiz\n"
            f"Bogotá D.C. | lilian@lorena-ruiz.com | +57 315 256 1884 | www.linkedin.com/in/lilianlorenarui"
        )

    # 2. Guardar body en archivo de respaldo (siempre — independiente del cliente)
    safe_name  = f"{cargo} - {empresa}".replace("/", "-").replace("\\", "-")[:60]
    body_file  = os.path.join(config.OUTPUT_DIR, f"email_body_{safe_name}.txt")
    try:
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(f"Para: (pega el email de RRHH)\n")
            f.write(f"Asunto: Aplicación: {cargo} — Lorena Ruiz\n")
            f.write(f"Adjunto: {os.path.basename(pdf_path)}\n\n")
            f.write(body_text)
        print(f"  [Applicator-C] Body guardado: {body_file}")
    except Exception as e:
        print(f"  [Applicator-C] No se pudo guardar body: {e}")

    # 3. Enviar body completo + notificación por Telegram (canal principal)
    try:
        send_email_body(job, body_text)
        send_cv_ready_email([{**job, "score": job.get("score", "")}])
    except Exception as e:
        print(f"  [Applicator-C] Telegram no enviado: {e}")

    # 4. Intentar abrir Gmail compose en browser (bonus — puede fallar silenciosamente)
    subject_enc = urllib.parse.quote(f"Aplicación: {cargo} — Lorena Ruiz")
    body_enc    = urllib.parse.quote(body_text)
    email_acct  = config.EMAIL_ACCOUNT.lower()
    if "@gmail.com" in email_acct:
        compose_url = (
            f"https://mail.google.com/mail/?view=cm&fs=1"
            f"&su={subject_enc}&body={body_enc}"
        )
    else:
        compose_url = f"mailto:?subject={subject_enc}&body={body_enc}"

    print(f"  [Applicator-C] Intentando abrir Gmail en browser...")
    print(f"  CV a adjuntar: {pdf_path}")
    try:
        webbrowser.open(compose_url)
    except Exception as e:
        print(f"  [Applicator-C] Browser no abrió ({e}) — body disponible en Telegram y en: {body_file}")

    return {
        "enviado": False,
        "canal": "C",
        "url": url,
        "mensaje": (
            f"Borrador de email abierto. Adjunta el CV manualmente: "
            f"{os.path.basename(pdf_path)}"
        ),
    }


# ── API pública ────────────────────────────────────────────────────────────────

def apply(job: dict, pdf_path: str, dry_run: bool = False,
          cv_text: str = "", job_description: str = "") -> dict:
    """
    Aplica a un cargo por el canal apropiado.

    Args:
        job:             dict del scraper (cargo, empresa, url, modalidad, ubicacion, rama)
        pdf_path:        ruta al PDF del CV optimizado
        dry_run:         si True, simula sin abrir navegador ni llamar Claude
        cv_text:         CV tailored en texto plano (para smart fill y email body)
        job_description: descripción completa del cargo (para smart fill y email body)

    Returns:
        {"enviado": bool, "canal": str, "url": str, "mensaje": str}
    """
    url   = job.get("url", "")
    canal = _detect_channel(url)

    if dry_run:
        print(
            f"  [Applicator] dry_run — canal {canal} simulado "
            f"para {job.get('cargo')} @ {job.get('empresa')}"
        )
        return {
            "enviado": True,
            "canal":   canal,
            "url":     url,
            "mensaje": f"[dry_run] Aplicación simulada — canal {canal}",
        }

    if canal == "A":
        return _apply_linkedin(job, pdf_path, cv_text=cv_text, job_description=job_description)
    elif canal == "B":
        return _apply_web(job, pdf_path)
    else:
        return _apply_email(job, pdf_path,
                            cv_text=cv_text, job_description=job_description)


# ── CLI de prueba ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_job = {
        "cargo":   "Paid Media Manager",
        "empresa": "Test Co",
        "url":     "https://www.linkedin.com/jobs/view/1234567890",
        "modalidad": "Híbrido",
        "ubicacion": "Bogotá",
        "rama":    "C",
    }
    test_pdf = os.path.join(config.OUTPUT_DIR, "test_cv.pdf")

    result = apply(test_job, test_pdf, dry_run=True)
    print(f"\nResultado: {result}")
