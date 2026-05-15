"""
Inicialización del perfil de navegador para LinkedIn Easy Apply.

Ejecutar UNA SOLA VEZ antes de usar el applicator en producción:
    python _setup_browser.py

Abre Chromium con un perfil persistente. Inicia sesión en LinkedIn manualmente,
cierra el navegador, y la sesión queda guardada para futuros runs.

Requisito previo:
    playwright install chromium
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PROFILE_DIR = config.PLAYWRIGHT_USER_DATA_DIR


def main() -> None:
    print("=" * 55)
    print("  JobAppAgent — Setup de sesión LinkedIn")
    print("=" * 55)
    print()
    print(f"Directorio del perfil: {PROFILE_DIR}")
    print()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright no instalado.")
        print("Ejecuta: pip install playwright && playwright install chromium")
        sys.exit(1)

    os.makedirs(PROFILE_DIR, exist_ok=True)

    print("Abriendo Chromium...")
    print()
    print("INSTRUCCIONES:")
    print("  1. En el navegador que se abre, ve a https://linkedin.com")
    print("  2. Inicia sesión con las credenciales de Lorena.")
    print("  3. Verifica que puedes ver el feed de LinkedIn.")
    print("  4. Cierra el navegador (o presiona Enter aquí).")
    print()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            slow_mo=100,
        )
        page = ctx.new_page()
        page.goto("https://www.linkedin.com/login", timeout=30_000)

        print("Navegador abierto en LinkedIn Login.")
        print("Inicia sesión y luego presiona Enter aquí para guardar y cerrar.")
        try:
            input()
        except EOFError:
            pass

        ctx.close()

    print()
    print("Sesión guardada correctamente.")
    print(f"Perfil en: {PROFILE_DIR}")
    print()
    print("Ahora puedes correr el pipeline en producción:")
    print("  python main.py --once --rama C")


if __name__ == "__main__":
    main()
