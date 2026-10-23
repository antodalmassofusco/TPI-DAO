"""Utilidades compartidas por las vistas: manejo de errores de negocio y filtros de plantilla."""
import functools

from flask import flash, request

from veterinaria.excepciones import VeterinariaError
from veterinaria.utils import formato

# estado -> (texto, color de Bootstrap)
ESTADOS = {
    "EXTRAIDA": ("Extraída", "secondary"),
    "EMPAQUETADA": ("Empaquetada", "info"),
    "EN_TRANSITO": ("En tránsito", "primary"),
    "RECIBIDA": ("Recibida", "warning"),
    "ANALIZADA": ("Analizada", "success"),
    "RECHAZADA": ("Muestra Rechazada", "danger"),
    "EMITIDO": ("Emitido", "secondary"),
    "RECIBIDO": ("Recibido", "success"),
    "RECHAZADO": ("Rechazado", "danger"),
    "PENDIENTE": ("Pendiente", "warning"),
    "ATENDIDO": ("Atendido", "success"),
    "CANCELADO": ("Cancelado", "secondary"),
    "COLOCADO": ("Colocado", "secondary"),
    "INTACTO": ("Intacto", "success"),
    "ROTO": ("Roto", "danger"),
    "DISPONIBLE": ("Disponible", "success"),
    "EN_USO": ("En uso", "primary"),
    "URGENTE": ("Urgente", "danger"),
    "NORMAL": ("Normal", "light"),
    "Al día": ("Al día", "success"),
    "Pendiente": ("Pendiente", "warning"),
    "Vencida": ("Vencida", "danger"),
    "Aún no corresponde": ("Aún no corresponde", "light"),
}


def validar(al_fallar):
    """Decorador para vistas POST: si el servicio lanza un error de negocio, se muestra como
    alerta y se vuelve a dibujar el formulario con lo que había cargado el usuario."""
    def decorador(vista):
        @functools.wraps(vista)
        def envoltura(*args, **kwargs):
            try:
                return vista(*args, **kwargs)
            except VeterinariaError as e:
                flash(str(e), "warning")
                return al_fallar(*args, datos=request.form, **kwargs)
        return envoltura
    return decorador


def registrar_filtros(app):
    @app.template_filter("num")
    def num(valor, decimales=None):
        if valor is None or valor == "":
            return ""
        if decimales is None:
            decimales = 0 if float(valor).is_integer() else 1
        return formato.numero(float(valor), decimales)

    @app.template_filter("moneda")
    def moneda(valor):
        return formato.moneda(valor or 0)

    @app.template_filter("fh")
    def fecha_hora(valor):
        """'2026-10-23 14:30' -> '23/10/2026 14:30'."""
        if not valor:
            return ""
        texto = str(valor)
        fecha = "/".join(reversed(texto[:10].split("-")))
        return f"{fecha} {texto[11:16]}".strip()

    @app.template_filter("input_fh")
    def input_fecha_hora(valor):
        """Valor para <input type="datetime-local">."""
        return str(valor or "")[:16].replace(" ", "T")

    # global (no context_processor) para que también lo vean las macros importadas
    app.jinja_env.globals["ESTADOS"] = ESTADOS
