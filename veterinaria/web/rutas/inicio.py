from flask import Blueprint, render_template

from veterinaria.servicios.tablero import TableroService

bp = Blueprint("inicio", __name__)


@bp.get("/")
def tablero():
    return render_template("inicio.html", r=TableroService().resumen())
