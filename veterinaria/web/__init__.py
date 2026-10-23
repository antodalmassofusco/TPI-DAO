"""Interfaz web: Flask + plantillas Jinja + Bootstrap 5."""
from flask import Flask

from veterinaria.web import util


def crear_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "vetred-tp-dao-2026"   # sólo firma los mensajes flash de la sesión
    util.registrar_filtros(app)

    from veterinaria.web.rutas import atencion, clientes, facturacion, inicio, laboratorio, logistica, reportes
    for modulo in (inicio, clientes, atencion, logistica, laboratorio, facturacion, reportes):
        app.register_blueprint(modulo.bp)
    return app
