"""
Reporter — Agente 6
Registra aplicaciones en SQLite y envía resumen diario por Telegram.

Funciones públicas:
  register(job, match_result, pdf_path, resultado)  → guarda en tabla aplicaciones
  send_daily_report(resultados_del_dia)              → envía mensaje Telegram
  send_alert(texto)                                  → mensaje puntual de alerta
"""
import asyncio
import os
import sqlite3
import sys
from datetime import date

import telegram

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── BD ─────────────────────────────────────────────────────────────────────────

_MODALIDAD_MAP = {
    "hibrido": "Híbrido", "hibrida": "Híbrido", "hybrid": "Híbrido",
    "remoto": "Remoto", "remote": "Remoto",
    "presencial": "Presencial", "on-site": "Presencial", "onsite": "Presencial",
}


def _norm_modalidad(raw: str) -> str:
    return _MODALIDAD_MAP.get(raw.lower().strip(), "Presencial")


def register(
    job: dict,
    match_result: dict,
    pdf_path: str,
    resultado: str = "Enviado",
    status_aplicacion: str = "A",
) -> int:
    """
    Inserta una aplicación en la tabla `aplicaciones`.

    Args:
        job:               dict del scraper (cargo, empresa, url, modalidad, ubicacion, rama)
        match_result:      dict del skill_matcher (score, passed, ...)
        pdf_path:          ruta del PDF generado
        resultado:         "Enviado" | "Pendiente" | "Fallido"
        status_aplicacion: "A" (LinkedIn) | "B" (Web) | "C" (Email)

    Returns:
        id de la fila insertada
    """
    conn = sqlite3.connect(config.DB_PATH)
    cur  = conn.execute(
        """
        INSERT INTO aplicaciones
          (fecha, rama, cargo, empresa, url, modalidad, ubicacion,
           match_score, status_aplicacion, resultado, cv_generado)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            date.today().isoformat(),
            job.get("rama", "A"),
            job.get("cargo", ""),
            job.get("empresa", ""),
            job.get("url", ""),
            _norm_modalidad(job.get("modalidad", "")),
            job.get("ubicacion", ""),
            match_result.get("score", 0),
            status_aplicacion,
            resultado,
            pdf_path,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()

    # Marcar como aplicado en memoria_cargos
    if job.get("id_cargo_externo"):
        _mark_applied(job["id_cargo_externo"])

    return row_id


def _mark_applied(id_cargo_externo: str) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE memoria_cargos SET aplicado=1 WHERE id_cargo_externo=?",
        (id_cargo_externo,),
    )
    conn.commit()
    conn.close()


def get_daily_stats() -> dict:
    """Retorna estadísticas del día actual desde la BD."""
    today = date.today().isoformat()
    conn  = sqlite3.connect(config.DB_PATH)
    rows  = conn.execute(
        "SELECT cargo, empresa, resultado, match_score, rama "
        "FROM aplicaciones WHERE fecha=? ORDER BY id DESC",
        (today,),
    ).fetchall()
    total_acum = conn.execute("SELECT COUNT(*) FROM aplicaciones").fetchone()[0]
    conn.close()

    exitosas  = [r for r in rows if r[2] == "Enviado"]
    fallidas  = [r for r in rows if r[2] == "Fallido"]
    pendientes = [r for r in rows if r[2] == "Pendiente"]

    return {
        "fecha":       today,
        "total_hoy":   len(rows),
        "exitosas":    exitosas,
        "fallidas":    fallidas,
        "pendientes":  pendientes,
        "total_acum":  total_acum,
        "rows":        rows,
    }


# ── Telegram ───────────────────────────────────────────────────────────────────

def _require_telegram() -> tuple[str, str]:
    token   = config.TELEGRAM_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or token.startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram token no configurado en config/telegram_token.txt")
    if not chat_id or chat_id.startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram chat_id no configurado en config/telegram_chat_id.txt")
    return token, chat_id


async def _send_async(token: str, chat_id: str, text: str) -> None:
    bot = telegram.Bot(token=token)
    async with bot:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
        )


def _send(text: str) -> None:
    token, chat_id = _require_telegram()
    asyncio.run(_send_async(token, chat_id, text))


def _rama_label(rama: str) -> str:
    return {"A": "Consultoria", "B": "Retail", "C": "Paid Media"}.get(rama, rama)


def _resultado_icon(resultado: str) -> str:
    return {"Enviado": "OK", "Fallido": "X", "Pendiente": "..."}.get(resultado, resultado)


def build_daily_report(stats: dict) -> str:
    n_pass    = len(stats["pendientes"]) + len(stats["exitosas"])
    n_skip    = len(stats["fallidas"])
    n_total   = n_pass + n_skip

    lines = [
        f"<b>JobAppAgent — {stats['fecha']}</b>",
        "",
        f"Evaluados hoy: {n_total}",
        f"Descartados (score bajo o ATS): {n_skip}",
        f"CVs generados listos para aplicar: {n_pass}",
    ]

    candidatos = stats["pendientes"] + stats["exitosas"]
    if candidatos:
        lines += ["", "<b>CVs listos:</b>"]
        for row in candidatos:
            cargo, empresa, resultado, score, rama = row
            lines.append(f"  • [{_rama_label(rama)}] {cargo} @ {empresa} ({score}%)")
    else:
        lines += ["", "Sin cargos que pasen los filtros hoy."]

    lines += ["", f"Acumulado total: {stats['total_acum']} aplicaciones"]
    return "\n".join(lines)


def send_daily_report(stats: dict | None = None) -> None:
    """Envía el resumen diario a Telegram. Si stats es None, lo calcula desde BD."""
    if stats is None:
        stats = get_daily_stats()
    text = build_daily_report(stats)
    _send(text)
    print(f"[Reporter] Reporte diario enviado ({stats['total_hoy']} apps hoy)")


def send_alert(texto: str) -> None:
    """Envía un mensaje puntual de alerta/notificación."""
    _send(texto)
    print(f"[Reporter] Alerta enviada: {texto[:60]}...")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    # 1. Insertar una aplicación de prueba en BD
    test_job = {
        "id_cargo_externo": "test-reporter-001",
        "cargo":     "Brand Strategist Sr.",
        "empresa":   "Grupo Exito",
        "url":       "https://linkedin.com/jobs/test",
        "modalidad": "Hibrido",
        "ubicacion": "Bogota",
        "rama":      "A",
    }
    test_match = {"score": 92, "passed": True}
    test_pdf   = os.path.join(config.OUTPUT_DIR, "Lorena Ruiz - Brand Strategist Sr. - Grupo Exito.pdf")

    row_id = register(test_job, test_match, test_pdf, resultado="Enviado", status_aplicacion="A")
    print(f"[Reporter] Aplicacion registrada con id={row_id}")

    # 2. Mostrar reporte del dia
    stats = get_daily_stats()
    report_text = build_daily_report(stats)
    print("\n--- REPORTE ---")
    print(report_text)

    # 3. Intentar enviar por Telegram (falla si token no configurado)
    try:
        send_daily_report(stats)
    except RuntimeError as e:
        print(f"\n[Reporter] Telegram no configurado aun: {e}")
