"""
Parser del CV de Lorena Ruiz.
Usa pdfplumber con crop por columnas para evitar el interleaving del layout de 2 columnas.
Retorna un dict con: nombre, experiencia[], educacion[], skills[], idiomas[].
"""
import pdfplumber
import re
import json
import os

CV_DEFAULT = r"C:\Users\lilia\CV\Lorena_Ruiz_CV.pdf"

MONTHS = (
    r"(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)"
)
DATE_RE = re.compile(
    rf"{MONTHS}\s+\d{{4}}\s*[-–]\s*"
    rf"(?:{MONTHS}\s+\d{{4}}|current\s+working|present|Current)",
    re.IGNORECASE,
)
DEGREE_KW = ("DIPLOMA", "CERTIFICATE", "MASTER", "BACHELOR")
SECTION_HEADERS = {
    "WORKEXPERIENCE", "EDUCATION", "SKILLS", "IDIOMAS",
    "STRENGTHS", "CONTACT", "INTERESTS", "PROFESSIONALPROFILE",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _collapse_spaced_caps(text: str) -> str:
    """'W O R K E X P E R I E N C E' → 'WORKEXPERIENCE'"""
    return re.sub(r"\b([A-Z] ){2,}[A-Z]\b", lambda m: m.group(0).replace(" ", ""), text)


def _extract_columns(pdf_path: str) -> tuple[str, str]:
    """Crop each page at 40% width to isolate left sidebar from main content."""
    left_pages, right_pages = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            x0, y0, x1, y1 = page.bbox
            mid = x0 + (x1 - x0) * 0.40
            left_pages.append(page.crop((x0, y0, mid, y1)).extract_text() or "")
            right_pages.append(page.crop((mid, y0, x1, y1)).extract_text() or "")
    left = _collapse_spaced_caps("\n".join(left_pages))
    right = _collapse_spaced_caps("\n".join(right_pages))
    return left, right


def _clean_lines(text: str) -> list[str]:
    return [l.strip() for l in text.split("\n") if l.strip()]


def _is_section_header(line: str) -> bool:
    return line in SECTION_HEADERS


# ── Section parsers ─────────────────────────────────────────────────────────────

def _parse_experiencia(right_text: str) -> list[dict]:
    lines = _clean_lines(right_text)
    results = []
    i = 0
    while i < len(lines):
        if DATE_RE.search(lines[i]):
            fecha = lines[i]
            empresa = lines[i - 1] if i >= 1 else ""
            prev2 = lines[i - 2] if i >= 2 else ""

            # prev2 is a job title if it's ALL CAPS and not a known header
            if (
                prev2
                and re.match(r"^[A-Z][A-Z\s,\.\-]+$", prev2)
                and not _is_section_header(prev2)
            ):
                cargo = prev2
            else:
                # title and company collapsed on one line
                cargo = empresa
                empresa = ""

            # Collect description lines until next date or section header
            desc, j = [], i + 1
            while j < len(lines):
                if DATE_RE.search(lines[j]) or _is_section_header(lines[j]):
                    break
                desc.append(lines[j])
                j += 1

            if cargo:
                results.append({
                    "cargo": cargo,
                    "empresa": empresa,
                    "fecha": fecha,
                    "descripcion": " ".join(desc[:8]),
                })
            i = j
        else:
            i += 1
    return results


def _parse_educacion(left_text: str) -> list[dict]:
    lines = _clean_lines(left_text)
    results = []
    i = 0
    while i < len(lines):
        if any(kw in lines[i].upper() for kw in DEGREE_KW):
            titulo = lines[i]
            j = i + 1
            # Absorb continuation lines for multi-line degree titles
            while j < len(lines):
                nxt = lines[j]
                if any(kw in nxt.upper() for kw in DEGREE_KW):
                    break
                if _is_section_header(nxt):
                    break
                if re.match(r"^[A-Z][a-z]", nxt):   # institution starts here
                    break
                if re.search(r"\d{4}", nxt):
                    break
                titulo += " " + nxt
                j += 1
            inst = lines[j] if j < len(lines) else ""
            lugar = lines[j + 1] if j + 1 < len(lines) else ""
            results.append({
                "titulo": titulo.strip(),
                "institucion": inst,
                "lugar": lugar,
            })
            i = j + 2
        else:
            i += 1
    return results


def _parse_list_section(text: str, header: str) -> list[str]:
    m = re.search(rf"{header}\s*\n(.*?)(?:\n[A-Z]{{4,}}|\Z)", text, re.DOTALL)
    if not m:
        return []
    return [
        l.strip()
        for l in m.group(1).split("\n")
        if l.strip() and not re.match(r"^[A-Z]{4,}$", l.strip())
    ]


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_cv(pdf_path: str | None = None) -> dict:
    """
    Lee el CV en PDF y retorna un dict estructurado.

    Returns:
        {
            "nombre": str,
            "experiencia": [{"cargo", "empresa", "fecha", "descripcion"}, ...],
            "educacion":   [{"titulo", "institucion", "lugar"}, ...],
            "skills":      [str, ...],
            "idiomas":     [str, ...],
        }
    """
    path = pdf_path or CV_DEFAULT
    if not os.path.exists(path):
        raise FileNotFoundError(f"CV no encontrado en: {path}")

    left, right = _extract_columns(path)

    return {
        "nombre": "Lorena Ruiz",
        "experiencia": _parse_experiencia(right),
        "educacion": _parse_educacion(left),
        "skills": _parse_list_section(left, "SKILLS"),
        "idiomas": _parse_list_section(left, "IDIOMAS"),
    }


if __name__ == "__main__":
    resultado = parse_cv()
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
