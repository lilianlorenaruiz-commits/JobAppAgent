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
import re
import sys
import time
import random
import json
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


def _load_candidate_profile() -> dict:
    """
    Carga config/candidate_profile.json con las respuestas estables de Lorena.
    Retorna dict vacío si el archivo no existe o está malformado.
    """
    try:
        profile_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "candidate_profile.json"
        )
        with open(profile_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# Reglas keyword → clave de perfil (orden: más específico primero)
# IMPORTANTE: reglas más específicas deben ir antes que las generales.
# Ej: reubicación antes que ciudad, para evitar falso match en "reubicarte a otra ciudad".
_PROFILE_KEYWORD_RULES = [
    # Salario / pretensión → número COP puro (campo numérico LinkedIn espera decimal)
    (["salarial", "salario", "pretensión", "pretension", "remuneraci", "compensation",
      "salary", "wage", "económi"],                                    "salary_cop_monthly"),
    # Reubicación (antes que ciudad — "reubicarte a otra ciudad" debe caer aquí)
    (["reubicar", "reubicaci", "relocat", "traslad"],                 "willing_to_relocate"),
    # Ciudad / ubicación
    (["ciudad", "city", "ubicaci", "location", "resid", "vives"],     "city"),
    # Disponibilidad para viajar
    (["viajar", "travel", "desplazarte", "viaje"],                    "willing_to_travel"),
    # Disponibilidad de inicio
    (["cuándo", "cuando", "comenzar", "iniciar", "disponibil",
      "start", "availability", "incorporar"],                         "availability"),
    # Verificación de antecedentes
    (["antecedente", "background check", "verificaci", "security check"],
                                                                       "background_check"),
    # Inglés / idioma
    (["inglés", "ingles", "english", "idioma", "language", "nivel de ingl"],
                                                                       "english_level"),
    # Vehículo — evitar "car" corto (falso match en "cargo", "caract", etc.)
    (["vehículo", "vehiculo", "carro", "coche", "moto", "vehicle"],   "has_vehicle"),
    # Turnos nocturnos
    (["nocturno", "nocturn", "night shift", "turno de noche"],        "night_shifts"),
    # Modalidad híbrida
    (["híbrid", "hibrid"],                                             "hybrid_available"),
    # Visa / patrocinio
    (["visa", "sponsor", "patrocin"],                                  "requires_visa_sponsorship"),
    # Autorización de trabajo
    (["autorización", "autorizacion", "work authorization", "permiso de trabajo",
      "work permit"],                                                   "work_authorization"),
    # Años de experiencia
    (["años de experiencia", "years of experience", "experiencia profesional"],
                                                                       "years_experience"),
    # Empleo actual
    (["actualmente empleado", "currently employed", "trabajando actualmente"],
                                                                       "currently_employed"),
]


def _match_profile_question(question: str, profile: dict) -> str:
    """
    Intenta hacer match de la pregunta contra las reglas keyword del perfil.
    Retorna el valor del perfil si hay match, '' si no coincide ninguna regla
    o si el perfil no tiene la clave correspondiente.
    La comparación es case-insensitive.
    """
    if not profile:
        return ""
    q_lower = question.lower()
    for keywords, profile_key in _PROFILE_KEYWORD_RULES:
        if any(kw in q_lower for kw in keywords):
            return str(profile.get(profile_key, ""))
    return ""


def _generate_field_answer(question: str, cv_text: str, job_description: str) -> str:
    """
    Genera una respuesta para un campo de texto libre.
    Prioridad: perfil candidata → Claude.
    Máximo 150 caracteres.
    Retorna cadena vacía si no hay respuesta disponible.
    """
    # 1. Consultar perfil candidata (rápido, sin API)
    profile = _load_candidate_profile()
    profile_answer = _match_profile_question(question, profile)
    if profile_answer:
        return profile_answer[:150]

    # 2. Fallback: Claude (solo si anthropic disponible)
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
        # Excluir: teléfono, email, nombre, campos numéricos (salario, años, etc.)
        # No incluir <select> (dropdowns) — requieren lógica separada
        selector = (
            "textarea, "
            "input[type='text']"
            ":not([name*='phone']):not([id*='phone'])"
            ":not([name*='email']):not([id*='email'])"
            ":not([name*='name']):not([id*='first']):not([id*='last'])"
            ":not([type='number']):not([inputmode='numeric']):not([inputmode='decimal'])"
        )
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


def _best_matching_option(answer: str, options: list) -> str:
    """
    Encuentra la opción de un dropdown que mejor coincide con `answer`.
    Estrategia:
      1. Exact match (case-insensitive)
      2. Partial match
      3. Sí/No/Yes mapping
      4. Primera opción no vacía como fallback
    """
    answer_lower = answer.lower().strip()
    # 1. Exact
    for opt in options:
        if opt.lower().strip() == answer_lower:
            return opt
    # 2. Partial
    for opt in options:
        if answer_lower in opt.lower() or opt.lower() in answer_lower:
            return opt
    # 3. Affirmative / negative
    affirmatives = {"sí", "si", "yes", "1", "true", "c1", "c2", "b2", "b1"}
    if any(a in answer_lower for a in affirmatives):
        for opt in options:
            if opt.lower().strip() in ("yes", "sí", "si"):
                return opt
    if answer_lower in ("no", "0", "false"):
        for opt in options:
            if opt.lower().strip() == "no":
                return opt
    # 4. Primer opción disponible
    return options[0] if options else ""


def _fill_select_fields(page, cv_text: str, job_description: str) -> int:
    """
    Detecta y rellena campos <select> (dropdown) en LinkedIn Easy Apply.

    LinkedIn usa <select> OCULTOS con UI custom encima (display:none).
    → NO usar is_visible() — usar evaluate() para acceder al DOM directo.
    → Intentar select_option() y como fallback manipulación JS directa.

    Estrategia: profile match → Claude con opciones → primera opción.
    Nunca lanza excepción.
    """
    _PLACEHOLDER_LABELS = {
        "selecciona una opción", "select an option",
        "seleccionar", "select", "--", "",
    }
    filled = 0
    try:
        selects = page.locator("select").all()
        for sel_el in selects:
            try:
                # Obtener opciones via JS (funciona aunque el select esté oculto)
                options = sel_el.evaluate("""
                    el => Array.from(el.options)
                        .map(o => o.text.trim())
                        .filter(t => t.length > 0)
                """)
                if not options:
                    continue

                real_options = [o for o in options if o.lower() not in _PLACEHOLDER_LABELS]
                if not real_options:
                    continue

                # Skip si ya hay una opción real seleccionada
                current_label = sel_el.evaluate(
                    "el => el.options[el.selectedIndex]?.text?.trim() || ''"
                )
                if current_label.lower() not in _PLACEHOLDER_LABELS and current_label:
                    continue

                # Obtener la pregunta del label asociado
                question = _get_field_question(page, sel_el)

                # 1. Match con perfil candidata
                profile = _load_candidate_profile()
                profile_answer = _match_profile_question(question or "", profile)

                # 2. Claude si no hay match de perfil
                if not profile_answer and anthropic is not None:
                    opts_str = " / ".join(real_options[:6])
                    prompt = (
                        f"You are Lorena Ruiz filling a job application form. "
                        f"Choose EXACTLY ONE of the OPTIONS for the QUESTION.\n\n"
                        f"QUESTION: {question or '(not visible)'}\n"
                        f"OPTIONS: {opts_str}\n\n"
                        f"CV context:\n{cv_text[:800]}\n\n"
                        f"Respond ONLY with the exact option text, nothing else."
                    )
                    try:
                        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                        resp = client.messages.create(
                            model=config.MODEL_FAST,
                            max_tokens=30,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        profile_answer = resp.content[0].text.strip()
                    except Exception:
                        profile_answer = ""

                # 2. Si no hay match de perfil, usar Claude con las opciones disponibles
                if not profile_answer and anthropic is not None:
                    opts_str = " / ".join(options)
                    prompt = (
                        f"You are Lorena Ruiz filling a job application form. "
                        f"Choose EXACTLY ONE of these options for the question below.\n\n"
                        f"QUESTION: {question or '(sin texto)'}\n"
                        f"OPTIONS: {opts_str}\n\n"
                        f"CV context:\n{cv_text[:1000]}\n\n"
                        f"Respond with ONLY the exact option text, nothing else."
                    )
                    try:
                        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                        resp = client.messages.create(
                            model=config.MODEL_FAST,
                            max_tokens=30,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        profile_answer = resp.content[0].text.strip()
                    except Exception:
                        profile_answer = ""

                # 3. Encontrar la opción más cercana
                best = _best_matching_option(
                    profile_answer or real_options[0], real_options
                )
                if not best:
                    continue

                # Intento A: select_option() de Playwright
                selected = False
                try:
                    sel_el.select_option(label=best)
                    selected = True
                except Exception:
                    pass

                # Intento B: manipulación JS directa (funciona en selects ocultos)
                if not selected:
                    try:
                        sel_el.evaluate(f"""
                            el => {{
                                const opts = Array.from(el.options);
                                const target = {repr(best)};
                                const o = opts.find(o => o.text.trim() === target);
                                if (o) {{
                                    o.selected = true;
                                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                                    el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                                }}
                            }}
                        """)
                        selected = True
                    except Exception:
                        pass

                if selected:
                    _human_pause(0.3, 0.6)
                    print(f"  [Applicator-A] Dropdown llenado: {question[:50]!r} → {best!r}")
                    filled += 1

            except Exception:
                continue
    except Exception:
        pass
    return filled


# Valores de cargo/empresa que indican que no se extrajo info real del JD
_PLACEHOLDER_VALUES = {"cargo linkedin", "empresa linkedin", ""}


def _parse_title_for_job_info(title: str) -> dict:
    """
    Extrae cargo y empresa del título del tab de LinkedIn.
    Formatos soportados:
      "Product Manager | Falabella | LinkedIn"          ← formato real (pipe)
      "Product Manager at Falabella | LinkedIn"         ← inglés (at)
      "(3) Gerente de Marketing en Falabella | LinkedIn" ← español (en)
    Retorna {"cargo": "", "empresa": ""} si el formato no coincide.
    """
    if not title:
        return {"cargo": "", "empresa": ""}
    # Remover prefijo de notificación "(N) "
    title = re.sub(r"^\(\d+\)\s*", "", title)
    # Remover sufijo " | LinkedIn" — lo que queda es "Cargo | Empresa"
    # o "Cargo at Empresa" / "Cargo en Empresa"
    if " | LinkedIn" in title:
        title = title[: title.index(" | LinkedIn")]
    # 1. Pipe: "Product Manager | Falabella"  ← formato real de LinkedIn
    if " | " in title:
        parts = title.split(" | ", 1)
        return {"cargo": parts[0].strip(), "empresa": parts[1].strip()}
    # 2. " at " (inglés) o " en " (español) como fallback
    for sep in [" at ", " en "]:
        if sep in title:
            parts = title.split(sep, 1)
            return {"cargo": parts[0].strip(), "empresa": parts[1].strip()}
    return {"cargo": "", "empresa": ""}


def _extract_linkedin_job_info(page) -> dict:
    """
    Lee cargo, empresa y descripción de la página LinkedIn actual.
    Estrategia: page.title() primero (estable) → selectores DOM como fallback.
    Nunca lanza excepción. Retorna dict con cadenas vacías si falla.
    """
    info = {"cargo": "", "empresa": "", "descripcion": ""}
    try:
        # 0. Scroll para activar lazy-loading de la descripción
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            import time as _time
            _time.sleep(0.8)
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

        # 1. Título del tab — más estable que selectores CSS
        try:
            title_info = _parse_title_for_job_info(page.title() or "")
            if title_info["cargo"]:
                info["cargo"] = title_info["cargo"]
            if title_info["empresa"]:
                info["empresa"] = title_info["empresa"]
        except Exception:
            pass

        # 2. Fallback DOM para cargo (si title no lo dio)
        if not info["cargo"]:
            for sel in [
                "h1.t-24",
                "h1.jobs-unified-top-card__job-title",
                ".job-details-jobs-unified-top-card__job-title h1",
                "h1",
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2_000):
                        txt = (el.text_content(timeout=2_000) or "").strip()
                        if txt:
                            info["cargo"] = txt
                            break
                except Exception:
                    continue

        # 3. Fallback DOM para empresa (si title no lo dio)
        if not info["empresa"]:
            for sel in [
                ".job-details-jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name a",
                ".topcard__org-name-link",
                ".jobs-unified-top-card__company-name",
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2_000):
                        txt = (el.text_content(timeout=2_000) or "").strip()
                        if txt:
                            info["empresa"] = txt
                            break
                except Exception:
                    continue

        # 4. Descripción — estrategia multicapa (selectores CSS de LinkedIn cambian frecuentemente)
        # 4a. JavaScript evaluation — más robusto que selectores CSS
        if not info["descripcion"]:
            try:
                desc = page.evaluate("""
                    () => {
                        const candidates = [
                            document.querySelector('#job-details'),
                            document.querySelector('.jobs-description__content'),
                            document.querySelector('.jobs-box__html-content'),
                            document.querySelector('.jobs-description-content__text'),
                            document.querySelector('article.jobs-description__container'),
                            document.querySelector('.description__text'),
                            document.querySelector('[data-test-id="job-description"]'),
                            document.querySelector('.jobs-description'),
                        ];
                        for (const el of candidates) {
                            if (el && el.innerText && el.innerText.trim().length > 100) {
                                return el.innerText.trim();
                            }
                        }
                        return '';
                    }
                """)
                if desc and len(desc.strip()) > 100:
                    info["descripcion"] = desc.strip()[:3000]
            except Exception:
                pass

        # 4b. JSON-LD — LinkedIn incluye datos estructurados para SEO
        if not info["descripcion"]:
            try:
                ld_desc = page.evaluate("""
                    () => {
                        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                        for (const s of scripts) {
                            try {
                                const data = JSON.parse(s.textContent);
                                if (data.description) return data.description;
                                if (data['@graph']) {
                                    for (const item of data['@graph']) {
                                        if (item.description) return item.description;
                                    }
                                }
                            } catch(e) {}
                        }
                        return '';
                    }
                """)
                if ld_desc and len(ld_desc.strip()) > 100:
                    import html as _html
                    cleaned = _html.unescape(ld_desc).strip()
                    info["descripcion"] = cleaned[:3000]
            except Exception:
                pass

        # 4c. Selectores CSS extendidos como último fallback
        if not info["descripcion"]:
            for sel in [
                "#job-details",
                ".jobs-description__content .jobs-box__html-content",
                ".jobs-description-content__text--stretch",
                ".jobs-description__content",
                ".jobs-box__html-content",
                ".jobs-description",
                "article.jobs-description__container",
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2_000):
                        txt = (el.text_content(timeout=3_000) or "").strip()
                        if len(txt) > 100:
                            info["descripcion"] = txt[:3000]
                            break
                except Exception:
                    continue

    except Exception:
        pass

    return info


def _linkedin_playwright_loop(job: dict, pdf_path: str,
                              cv_text: str, job_description: str):
    """
    Corre la sesión Playwright de LinkedIn Easy Apply.

    Retorna:
      - dict  → resultado final (éxito, error, sesión expirada, etc.)
      - None  → no había Easy Apply — el caller debe delegar a _apply_web
                 IMPORTANTE: retornar None aquí permite que el `with sync_playwright()`
                 cierre su event loop antes de que _apply_web intente abrir el suyo.
    """
    from playwright.sync_api import TimeoutError as PwTimeout

    url     = job.get("url", "")
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")

    with sync_playwright() as p:
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
            # Esperar a que el JS de LinkedIn termine de renderizar el panel del cargo
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass  # timeout en networkidle no es fatal
            _human_pause(1.0, 2.0)

            # ── 1b. Extraer info del cargo de la página ──────────────────────
            # Lee cargo, empresa y descripción desde el HTML de LinkedIn.
            # Enriquece job_description si llegó vacío (ej: desde smoke test).
            _job_info = _extract_linkedin_job_info(page)
            if _job_info["cargo"] and cargo.lower() in _PLACEHOLDER_VALUES:
                cargo = _job_info["cargo"]
                print(f"  [Applicator-A] Cargo extraído: {cargo!r}")
            if _job_info["empresa"] and empresa.lower() in _PLACEHOLDER_VALUES:
                empresa = _job_info["empresa"]
                print(f"  [Applicator-A] Empresa extraída: {empresa!r}")
            if _job_info["descripcion"] and not job_description:
                job_description = _job_info["descripcion"]
                print(f"  [Applicator-A] JD extraída: {len(job_description)} chars")

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

            # ── 3. Verificar si ya fue aplicado ─────────────────────────────
            _already_applied = False
            for _at in ["Solicitud enviada", "Application submitted", "Ya aplicaste"]:
                try:
                    if page.locator(f"text={_at}").first.is_visible(timeout=1_500):
                        _already_applied = True
                        break
                except Exception:
                    continue
            if _already_applied:
                print("  [Applicator-A] Cargo ya aplicado anteriormente — saltando.")
                ctx.close()
                return {
                    "enviado": True,
                    "canal": "A",
                    "url": url,
                    "mensaje": "Solicitud ya enviada anteriormente en LinkedIn",
                }

            # ── 4. Easy Apply button ─────────────────────────────────────────
            # LinkedIn usa Shadow DOM para el botón "Solicitud sencilla / Easy Apply".
            # document.querySelectorAll NO penetra shadow DOM.
            # Playwright text locator y get_by_role SÍ penetran shadow DOM.
            #
            # Estrategia:
            #   1. Esperar render completo (3-5s adicionales para Ember late hydration)
            #   2. get_by_role("button") page-wide — penetra shadow DOM
            #   3. text= locator con timeout extendido — también penetra shadow DOM
            #      (verificando que el elemento sea un button para evitar badge misclick)
            #   4. CSS aria-label fallback
            easy_apply_btn = None

            _NAME_PATTERNS = [
                re.compile(r"solicitud sencilla", re.IGNORECASE),
                re.compile(r"easy apply", re.IGNORECASE),
                re.compile(r"postulaci", re.IGNORECASE),
            ]
            _EASY_APPLY_TEXTS = ("Solicitud sencilla", "Easy Apply", "Postulación sencilla")

            # Esperar render completo de componentes shadow DOM de LinkedIn
            _human_pause(3.0, 4.0)

            # Intento 1: get_by_role("button") — penetra shadow DOM, más estricto
            for _pat in _NAME_PATTERNS:
                try:
                    loc = page.get_by_role("button", name=_pat).first
                    if loc.is_visible(timeout=8_000):
                        easy_apply_btn = loc
                        print(f"  [Applicator-A] Botón Easy Apply (get_by_role, pat={_pat.pattern!r}).")
                        break
                except Exception:
                    continue

            # Intento 2: text locator — también penetra shadow DOM; verificar que
            # el elemento tenga un ancestor <button> para evitar badge misclick
            if easy_apply_btn is None:
                for _txt in _EASY_APPLY_TEXTS:
                    try:
                        loc = page.locator(f"text={_txt}").first
                        if loc.is_visible(timeout=8_000):
                            # Verificar que sea (o esté dentro de) un <button>
                            try:
                                btn = loc.locator("xpath=ancestor-or-self::button").first
                                if btn.is_visible(timeout=1_000):
                                    easy_apply_btn = btn
                                else:
                                    easy_apply_btn = loc  # fallback: click en el span
                            except Exception:
                                easy_apply_btn = loc
                            print(f"  [Applicator-A] Botón Easy Apply (text={_txt!r}).")
                            break
                    except Exception:
                        continue

            # Intento 3: aria-label y clases CSS de LinkedIn
            if easy_apply_btn is None:
                for _sel in [
                    "button[aria-label*='sencilla']",
                    "button[aria-label*='Easy Apply']",
                    "button.jobs-apply-button",
                    ".jobs-s-apply button",
                    ".jobs-apply-button--top-card",
                ]:
                    try:
                        loc = page.locator(_sel).first
                        if loc.is_visible(timeout=3_000):
                            easy_apply_btn = loc
                            print(f"  [Applicator-A] Botón Easy Apply (CSS {_sel!r}).")
                            break
                    except Exception:
                        continue

            if easy_apply_btn is None:
                # Tomar screenshot para diagnóstico antes de decidir fallback
                shot = _screenshot_on_error(page, "no_easy_apply_btn")
                if shot:
                    print(f"  [Applicator-A] Screenshot de diagnóstico: {shot}")
                print("  [Applicator-A] No hay Easy Apply — redirigiendo a canal B.")
                ctx.close()
                return None  # ← señal para fallback; NO llamar _apply_web aquí

            _human_pause()
            easy_apply_btn.click()
            print("  [Applicator-A] Click en Easy Apply ejecutado.")
            _human_pause(2.0, 3.0)  # LinkedIn anima el modal ~800-1500ms
            # Screenshot diagnóstico post-click
            shot_post = _screenshot_on_error(page, "post_click")
            if shot_post:
                print(f"  [Applicator-A] Screenshot post-click: {shot_post}")

            # ── 4. Esperar modal ─────────────────────────────────────────────
            modal = None
            # Intento primario: get_by_role (más robusto que CSS)
            try:
                modal = page.get_by_role("dialog").first
                modal.wait_for(state="visible", timeout=15_000)
                print("  [Applicator-A] Modal detectado via get_by_role('dialog').")
            except Exception:
                modal = None

            if modal is None:
                for sel in [
                    ".jobs-easy-apply-modal",
                    ".artdeco-modal",
                    "[data-test-modal]",
                    ".jobs-apply-form__container",
                    "[role='dialog']",
                ]:
                    try:
                        modal = page.locator(sel).first
                        modal.wait_for(state="visible", timeout=8_000)
                        print(f"  [Applicator-A] Modal detectado con: {sel!r}")
                        break
                    except Exception:
                        modal = None

            print("  [Applicator-A] Easy Apply abierto." if modal else "  [Applicator-A] Modal no detectado.")

            if modal is None:
                _screenshot_on_error(page, "no_modal")
                ctx.close()
                return {
                    "enviado": False, "canal": "A", "url": url,
                    "mensaje": "Modal Easy Apply no apareció",
                }

            # ── 5. Navegar pasos del formulario ──────────────────────────────
            max_steps = 20
            for step in range(max_steps):
                _human_pause(0.8, 1.5)
                print(f"  [Applicator-A] Paso {step + 1}")

                # a) Subir CV si hay campo de archivo
                _maybe_upload_cv(page, pdf_path)

                # b) Rellenar campos simples (teléfono, email)
                _fill_simple_fields(page)

                # c) Smart fill: campos de texto libre con Claude
                _fill_free_text_fields(page, cv_text, job_description)

                # c2) Smart fill: dropdowns / <select> con perfil + Claude
                _fill_select_fields(page, cv_text, job_description)

                # d) Detectar si hay el botón Submit FINAL (último paso)
                # "Submit application" / "Enviar solicitud" aparece en la pantalla de confirmación.
                # "Review" es un paso INTERMEDIO — _find_submit_button NO lo incluye.
                # El agente hace click en "Review" automáticamente (como Next) y espera
                # la pantalla de confirmación para disparar HITL.
                submit_btn = _find_submit_button(page)
                if submit_btn is not None and submit_btn.is_visible(timeout=500):
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
                    print("  [Applicator-A] Sin botón siguiente — notificando por Telegram para completar manualmente.")
                    shot_path = _screenshot_on_error(page, "stuck_form")
                    if config.HITL_ENABLED:
                        # Notificar a Lorena con screenshot para que complete manualmente
                        _job_stuck = dict(job)
                        _job_stuck["cargo"] = cargo
                        _job_stuck["empresa"] = empresa
                        send_screenshot_for_approval_sync(
                            shot_path or "",
                            _job_stuck,
                            extra_msg="⚠️ El formulario tiene preguntas que el agente no pudo responder. Por favor completa y envía manualmente en el browser que está abierto.",
                        )
                    try:
                        page.wait_for_event("close", timeout=config.HITL_TIMEOUT_S * 1_000)
                    except Exception:
                        pass
                    ctx.close()
                    return {
                        "enviado": False, "canal": "A", "url": url,
                        "mensaje": "Formulario con preguntas adicionales — completar manualmente",
                    }

                next_btn.click()

            # Agotamos los pasos sin llegar a Submit
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


def _apply_linkedin(job: dict, pdf_path: str,
                    cv_text: str = "", job_description: str = "") -> dict:
    """
    Intenta LinkedIn Easy Apply con Playwright headful.

    Delega la sesión Playwright a _linkedin_playwright_loop. Si ese helper
    devuelve None (no hay Easy Apply), llama a _apply_web DESPUÉS de que el
    contexto Playwright haya cerrado — evitando el conflicto asyncio que ocurre
    cuando asyncio.run() se llama desde dentro del event loop de Playwright sync.
    """
    print(f"  [Applicator-A] Abriendo LinkedIn: {job.get('cargo')} @ {job.get('empresa')}")
    result = _linkedin_playwright_loop(job, pdf_path, cv_text, job_description)
    if result is None:
        # Easy Apply no disponible → Canal B (llamado FUERA del contexto Playwright)
        return _apply_web(job, pdf_path)
    return result


def _maybe_upload_cv(page, pdf_path: str) -> None:
    """Sube el PDF al campo de archivo de LinkedIn Easy Apply.

    LinkedIn oculta el input[type='file'] con display:none por diseño.
    is_visible() siempre retorna False → NO verificar visibilidad.
    Llamar set_input_files() directamente; capturar excepciones por selector.
    """
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


# Selectores del botón de SUBMIT FINAL — NO incluir "Review" ni "Revisar"
# (esos son botones de navegación intermedia hacia la pantalla de confirmación)
_SUBMIT_SELECTORS = [
    "button[aria-label='Submit application']",
    "button[aria-label='Enviar solicitud']",
    "button:has-text('Submit application')",
    "button:has-text('Enviar solicitud')",
    "button:has-text('Enviar')",
]


def _find_submit_button(page):
    """
    Retorna el botón de submit FINAL (Submit application / Enviar solicitud).
    NO incluye 'Review' ni 'Review your application' — esos son pasos intermedios
    que navegan a la pantalla de confirmación, no el submit real.
    Retorna None si no hay botón de submit visible.
    """
    for sel in _SUBMIT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1_500):
                return btn
        except Exception:
            continue
    return None


def _find_next_button(page):
    """Retorna el botón Next / Siguiente / Review / Continue si está visible.
    'Review' y 'Revisar' son navegación intermedia hacia la pantalla de confirmación,
    NO el submit final — se tratan como Next."""
    labels = [
        "Continue to next step",
        "Review your application",   # navega a pantalla de confirmación
        "Revisar tu solicitud",
        "Review",                    # paso intermedio — no submit
        "Revisar",                   # igual en español
        "Next",
        "Siguiente",
        "Continue",
        "Continuar",
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
