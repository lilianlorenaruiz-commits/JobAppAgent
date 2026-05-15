"""
Registra JobAppAgent como tarea diaria en Windows Task Scheduler.

Ejecutar UNA SOLA VEZ (con permisos de administrador si es necesario):
    python _schedule_task.py

La tarea ejecutará:
    python main.py --once
...diariamente a las 08:00, usando el Python del entorno virtual activo.

Para eliminar la tarea:
    python _schedule_task.py --delete
"""
import os
import sys
import subprocess
import argparse

TASK_NAME = "JobAppAgent_LorenaRuiz"
HORA      = "08:00"


def _python_exe() -> str:
    """Retorna la ruta absoluta del intérprete Python actual."""
    return sys.executable


def _project_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _main_script() -> str:
    return os.path.join(_project_dir(), "main.py")


def create_task() -> None:
    python  = _python_exe()
    script  = _main_script()
    workdir = _project_dir()

    # schtasks /Create con TR que llama Python directamente
    cmd = [
        "schtasks", "/Create", "/F",
        "/TN",  TASK_NAME,
        "/SC",  "DAILY",
        "/ST",  HORA,
        "/TR",  f'"{python}" "{script}" --once',
        "/SD",  "01/01/2026",
        "/RL",  "HIGHEST",
    ]

    print(f"Registrando tarea '{TASK_NAME}' en Windows Task Scheduler...")
    print(f"  Hora: {HORA} diario")
    print(f"  Python: {python}")
    print(f"  Script: {script}")
    print()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Tarea registrada correctamente.")
        print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"ERROR al crear tarea: {e.stderr.strip()}")
        print("Intenta ejecutar como Administrador.")
        sys.exit(1)

    print()
    print("Para verificar la tarea:")
    print(f"  schtasks /Query /TN {TASK_NAME}")
    print()
    print("Para ejecutar manualmente ahora:")
    print(f"  schtasks /Run /TN {TASK_NAME}")


def delete_task() -> None:
    cmd = ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]
    print(f"Eliminando tarea '{TASK_NAME}'...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Tarea eliminada.")
        print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {e.stderr.strip()}")
        sys.exit(1)


def query_task() -> None:
    cmd = ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout.strip())
    else:
        print(f"Tarea '{TASK_NAME}' no encontrada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestiona la tarea diaria de JobAppAgent")
    parser.add_argument("--delete", action="store_true", help="Elimina la tarea programada")
    parser.add_argument("--status", action="store_true", help="Muestra el estado de la tarea")
    args = parser.parse_args()

    if args.delete:
        delete_task()
    elif args.status:
        query_task()
    else:
        create_task()
