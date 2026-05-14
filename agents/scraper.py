"""
Scraper — Agente 2
Busca cargos en LinkedIn vía Apify (bebity/linkedin-jobs-scraper).
Filtra duplicados contra memoria_cargos (SQLite).
Retorna lista de job dicts nuevos listos para skill_matcher.analyze().

Uso en CLI:
    python scraper.py A           # busca cargos para Rama A en Apify
    python scraper.py A --dry-run # retorna datos de prueba sin llamar Apify
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

APIFY_BASE = "https://api.apify.com/v2"


# ── Helpers de Apify ───────────────────────────────────────────────────────────

def _require_apify_key() -> str:
    key = config.APIFY_API_KEY
    if not key or key.startswith("PEGA_AQUI"):
        raise RuntimeError(
            "Apify API key no configurada. "
            "Edita config/apify_key.txt o setea APIFY_API_KEY."
        )
    return key


def _build_linkedin_urls(queries: list[str], location: str, dias_max: int = 16) -> list[str]:
    """Convierte términos de búsqueda en URLs de LinkedIn Jobs (strings planos)."""
    import urllib.parse
    dias_segundos = min(dias_max, 30) * 86400
    urls = []
    for q in queries:
        params = urllib.parse.urlencode({
            "keywords": q,
            "location": location,
            "f_TPR":    f"r{dias_segundos}",
        })
        urls.append(f"https://www.linkedin.com/jobs/search/?{params}")
    return urls


def _start_run(queries: list[str], location: str, dias_max: int = 16) -> str:
    """Lanza el actor de Apify (curious_coder) y retorna el runId."""
    key = _require_apify_key()
    urls = _build_linkedin_urls(queries, location, dias_max)
    payload = {
        "urls":  urls,
        "limit": 25,
        "proxy": {"useApifyProxy": True},
    }
    r = httpx.post(
        f"{APIFY_BASE}/acts/{config.APIFY_ACTOR_ID}/runs",
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def _wait_for_run(run_id: str) -> str:
    """Espera hasta que el run termine y retorna el defaultDatasetId."""
    key = _require_apify_key()
    headers = {"Authorization": f"Bearer {key}"}
    deadline = time.time() + config.APIFY_MAX_WAIT_S
    while time.time() < deadline:
        r = httpx.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        data   = r.json()["data"]
        status = data["status"]
        if status == "SUCCEEDED":
            return data["defaultDatasetId"]
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run {run_id} terminó con status: {status}")
        print(f"[Scraper] Run {run_id} — status: {status}, esperando...")
        time.sleep(config.APIFY_POLL_S)
    raise TimeoutError(f"Apify run {run_id} no terminó en {config.APIFY_MAX_WAIT_S}s")


def _fetch_dataset(dataset_id: str) -> list[dict]:
    key = _require_apify_key()
    r = httpx.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {key}"},
        params={"format": "json"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


# ── Normalización ──────────────────────────────────────────────────────────────

def _parse_modalidad(item: dict) -> str:
    raw = " ".join([
        item.get("workType", ""),
        item.get("workplaceType", ""),
        item.get("jobType", ""),
    ]).lower()
    if "remote" in raw or "remoto" in raw:
        return "Remoto"
    if "hybrid" in raw or "híbrido" in raw or "hibrido" in raw:
        return "Híbrido"
    return "Presencial"


def _strip_html(html: str) -> str:
    """Elimina tags HTML y decodifica entidades básicas."""
    import re, html as html_module
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = html_module.unescape(text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _normalize(item: dict, rama: str) -> dict:
    """Mapea campos de Apify (curious_coder) al schema interno."""
    desc_raw = (
        item.get("description")
        or item.get("descriptionHtml")
        or item.get("jobDescription")
        or ""
    )
    descripcion = _strip_html(desc_raw) if "<" in desc_raw else desc_raw
    return {
        "id_cargo_externo":   str(item.get("id") or item.get("jobId") or ""),
        "cargo":              item.get("title") or item.get("position") or "",
        "empresa":            item.get("companyName") or item.get("company") or "",
        "url":                item.get("link") or item.get("url") or item.get("jobUrl") or "",
        "modalidad":          _parse_modalidad(item),
        "ubicacion":          item.get("location") or "",
        "descripcion":        descripcion,
        "fecha_publicacion":  item.get("postedAt") or item.get("publishedAt") or "",
        "rama":               rama,
    }


# ── Filtro de seniority ────────────────────────────────────────────────────────

import re as _re

_JUNIOR_PATTERN = _re.compile(
    r"\b("
    r"jr\.?|junior|entry[\s\-]?level|trainee"
    r"|practicante|pasante|aprendiz"
    r"|intern(?:ship)?"
    r"|auxiliar\s+de\s+marketing|asistente\s+de\s+marketing"
    r")\b",
    _re.IGNORECASE,
)


def _is_junior(job: dict) -> bool:
    return bool(_JUNIOR_PATTERN.search(job.get("cargo", "")))


# ── Base de datos ──────────────────────────────────────────────────────────────

def _filter_new(jobs: list[dict]) -> list[dict]:
    """Excluye cargos que ya están en memoria_cargos."""
    if not jobs:
        return []
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute("SELECT id_cargo_externo FROM memoria_cargos").fetchall()
    conn.close()
    known = {r[0] for r in rows}
    return [j for j in jobs if j["id_cargo_externo"] not in known]


def _save_to_memory(jobs: list[dict]) -> None:
    """Registra cargos nuevos en memoria_cargos (aplicado=0)."""
    if not jobs:
        return
    today = date.today().isoformat()
    conn = sqlite3.connect(config.DB_PATH)
    conn.executemany(
        "INSERT OR IGNORE INTO memoria_cargos "
        "(id_cargo_externo, cargo, empresa, fecha_visto, aplicado) VALUES (?,?,?,?,0)",
        [(j["id_cargo_externo"], j["cargo"], j["empresa"], today) for j in jobs],
    )
    conn.commit()
    conn.close()


# ── Datos de prueba (dry-run) ──────────────────────────────────────────────────

_DRY_RUN_JOBS: dict[str, list[dict]] = {
    "A": [
        {
            "id_cargo_externo": "dry-A-001",
            "cargo":     "Brand Strategist Sr.",
            "empresa":   "Grupo Éxito",
            "url":       "https://linkedin.com/jobs/dry-A-001",
            "modalidad": "Híbrido",
            "ubicacion": "Bogotá",
            "descripcion": (
                "Buscamos Brand Strategist Senior con mínimo 10 años de experiencia en brand strategy, "
                "gestión de marca y posicionamiento en mercados B2B y B2C. El candidato debe demostrar "
                "sólido conocimiento en digital transformation, liderazgo de equipos multidisciplinarios "
                "y data analysis aplicado a decisiones de marca. Inglés C1 Advanced indispensable para "
                "interacción con equipos regionales. Responsabilidades: diseñar e implementar la "
                "estrategia de marca para el portafolio de retail, liderar campañas de brand strategy "
                "360°, gestionar presupuesto B2C y P&L de la unidad, analizar datos de performance "
                "y consumer insights para optimizar inversión, coordinar con agencias y equipos de "
                "digital marketing, trade marketing y comunicaciones. Se valora experiencia en "
                "transformación digital de canales comerciales, manejo de Amazon Ads y plataformas "
                "de performance marketing. Modalidad híbrida, Bogotá."
            ),
            "fecha_publicacion": date.today().isoformat(),
            "rama": "A",
        },
        {
            "id_cargo_externo": "dry-A-002",
            "cargo":     "Marketing Consultant",
            "empresa":   "McKinsey & Company",
            "url":       "https://linkedin.com/jobs/dry-A-002",
            "modalidad": "Presencial",
            "ubicacion": "Bogotá",
            "descripcion": (
                "Consultor de Marketing Senior para práctica de Consumer & Retail en Bogotá. "
                "El rol requiere experiencia en brand strategy, digital transformation y gestión "
                "de clientes B2B en sector consumo masivo. Imprescindible: inglés C1, data analysis "
                "avanzado, capacidad de presentar estrategias a nivel C-suite. Experiencia previa en "
                "consultoría de marketing o roles de Brand Strategist en empresas de consumo masivo. "
                "Liderazgo de proyectos de transformación digital, diseño de planes de marketing "
                "integrado, análisis de mercado y posicionamiento de marca."
            ),
            "fecha_publicacion": date.today().isoformat(),
            "rama": "A",
        },
    ],
    "B": [
        {
            "id_cargo_externo": "dry-B-001",
            "cargo":     "Trade Marketing Manager",
            "empresa":   "Nestlé Colombia",
            "url":       "https://linkedin.com/jobs/dry-B-001",
            "modalidad": "Presencial",
            "ubicacion": "Bogotá",
            "descripcion": (
                "Buscamos Trade Marketing Manager con mínimo 8 años de experiencia en trade marketing, "
                "category management y shopper marketing en empresas de consumo masivo. "
                "Responsabilidades: gestión de P&L de la unidad de trade, desarrollo de planes "
                "de shopper insights y activaciones en punto de venta, negociación con cadenas "
                "de retail (Éxito, Jumbo, D1, Ara), category management para portafolio de productos, "
                "liderazgo de equipo de trade marketing regional, análisis de datos de ventas y "
                "participación de mercado. Requisitos: inglés C1, experiencia en planificación "
                "estratégica de marketing, manejo de presupuesto y P&L, conocimiento en shopper "
                "insights y comportamiento del consumidor en retail. Posgrado en Marketing o afines."
            ),
            "fecha_publicacion": date.today().isoformat(),
            "rama": "B",
        },
    ],
    "C": [
        {
            "id_cargo_externo": "dry-C-001",
            "cargo":     "Paid Media Manager",
            "empresa":   "Rappi",
            "url":       "https://linkedin.com/jobs/dry-C-001",
            "modalidad": "Híbrido",
            "ubicacion": "Bogotá",
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
            "fecha_publicacion": date.today().isoformat(),
            "rama": "C",
        },
    ],
}


# ── API pública ────────────────────────────────────────────────────────────────

def search_jobs(rama: str, dry_run: bool = False, limit: int | None = None) -> list[dict]:
    """
    Busca cargos en LinkedIn para una rama (A/B/C).
    Filtra duplicados contra memoria_cargos y guarda los nuevos.

    Args:
        rama:    "A" | "B" | "C"
        dry_run: Si True, retorna datos mock sin llamar Apify.
        limit:   Si se indica, recorta la lista final a N cargos.

    Returns:
        Lista de job dicts nuevos listos para skill_matcher.analyze().
    """
    rama = rama.upper()
    profile_names = {
        "A": "perfil_a_consultoria.json",
        "B": "perfil_b_retail.json",
        "C": "perfil_c_paidmedia.json",
    }
    with open(os.path.join(config.PROFILES_DIR, profile_names[rama]), encoding="utf-8") as f:
        perfil = json.load(f)

    if dry_run:
        print(f"[Scraper] Rama {rama}: modo dry-run — datos de prueba")
        raw_jobs = _DRY_RUN_JOBS.get(rama, [])
    else:
        queries  = perfil["terminos_busqueda"]
        location = perfil["ubicacion"][0]
        dias_max = perfil.get("dias_publicacion_max", 16)
        print(f"[Scraper] Rama {rama}: {len(queries)} terminos -> Apify")
        run_id     = _start_run(queries, location, dias_max)
        dataset_id = _wait_for_run(run_id)
        raw_items  = _fetch_dataset(dataset_id)
        print(f"[Scraper] {len(raw_items)} resultados de Apify")
        raw_jobs = [_normalize(item, rama) for item in raw_items]
        raw_jobs = [j for j in raw_jobs if j["id_cargo_externo"]]

    # Filtro seniority — descartar cargos Jr / entry-level antes de procesar
    junior_dropped = [j for j in raw_jobs if _is_junior(j)]
    raw_jobs = [j for j in raw_jobs if not _is_junior(j)]
    if junior_dropped:
        titles = ", ".join(j["cargo"] for j in junior_dropped[:5])
        extra = f" (y {len(junior_dropped)-5} más)" if len(junior_dropped) > 5 else ""
        print(f"[Scraper] {len(junior_dropped)} cargos junior descartados: {titles}{extra}")

    new_jobs = _filter_new(raw_jobs)
    if limit:
        new_jobs = new_jobs[:limit]
    print(f"[Scraper] {len(new_jobs)} cargos nuevos (no vistos antes)")
    _save_to_memory(new_jobs)
    return new_jobs


if __name__ == "__main__":
    rama_arg    = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    dry_arg     = "--dry-run" in sys.argv
    jobs = search_jobs(rama_arg, dry_run=dry_arg)
    print(json.dumps(jobs, indent=2, ensure_ascii=False))
