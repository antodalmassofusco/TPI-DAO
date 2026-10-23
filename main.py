"""Punto de entrada: levanta el servidor web local y abre el navegador.

    python main.py                 inicia la aplicación (si la base no existe, la crea con datos de prueba)
    python main.py --datos-prueba  regenera la base con datos de prueba e inicia la aplicación
"""
import os
import sys
import threading
import webbrowser
from pathlib import Path

from veterinaria.config import RUTA_BD

DIRECCION = "http://127.0.0.1:5000"
RUTAS_CHROME = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


def abrir_navegador():
    """Abre la app en Google Chrome si está instalado; si no, en el navegador predeterminado."""
    chrome = next((ruta for ruta in RUTAS_CHROME if ruta.is_file()), None)
    if chrome:
        webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(str(chrome)))
        webbrowser.get("chrome").open(DIRECCION)
    else:
        webbrowser.open(DIRECCION)


def main():
    if "--datos-prueba" in sys.argv or not RUTA_BD.exists():
        from datos_prueba import cargar_datos_prueba
        print("Generando base de datos de prueba...")
        cargar_datos_prueba()

    from veterinaria.web import crear_app
    app = crear_app()
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, abrir_navegador).start()
    print(f"Huellitas funcionando en {DIRECCION}  (Ctrl+C para detener)")
    # Un único hilo: la conexión a SQLite (Singleton) nunca se usa en simultáneo
    app.run(host="127.0.0.1", port=5000, threaded=False, debug=False)


if __name__ == "__main__":
    main()
