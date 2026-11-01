"""Interfaz web: Flask + plantillas Jinja + Bootstrap 5."""
from flask import Flask, flash, redirect, url_for

from veterinaria.excepciones import VeterinariaError
from veterinaria.web import util


def crear_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "huellitas-tp-dao-2026"   # sólo firma los mensajes flash de la sesión
    util.registrar_filtros(app)

    from veterinaria.web.rutas import atencion, clientes, facturacion, inicio, laboratorio, logistica, reportes
    for modulo in (inicio, clientes, atencion, logistica, laboratorio, facturacion, reportes):
        app.register_blueprint(modulo.bp)

    @app.errorhandler(VeterinariaError)
    def error_de_negocio(e):
        # Red de seguridad para errores que no maneja la vista (p. ej. un id inexistente en la URL)
        flash(str(e), "warning")
        return redirect(url_for("inicio.tablero"))

    return app
