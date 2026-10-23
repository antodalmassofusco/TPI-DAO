"""Proceso 7 (resultados de análisis) y consulta de trazabilidad."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from veterinaria.excepciones import VeterinariaError
from veterinaria.servicios.laboratorio import LaboratorioService
from veterinaria.utils.fechas import ahora
from veterinaria.web.util import validar

bp = Blueprint("laboratorio", __name__, url_prefix="/laboratorio")
FILTROS = {
    "pendientes": ("Por analizar", ["RECIBIDA"]),
    "circuito": ("En circuito", ["EXTRAIDA", "EMPAQUETADA", "EN_TRANSITO"]),
    "rechazadas": ("Rechazadas", ["RECHAZADA"]),
    "analizadas": ("Analizadas", ["ANALIZADA"]),
}


@bp.get("/resultados")
def resultados():
    filtro = request.args.get("filtro", "pendientes")
    servicio = LaboratorioService()
    conteo = {clave: len(servicio.muestras(estados)) for clave, (_, estados) in FILTROS.items()}
    return render_template("resultados.html", muestras=servicio.muestras(FILTROS[filtro][1]), filtro=filtro,
                           filtros=FILTROS, conteo=conteo)


@bp.get("/muestras/<int:muestra_id>")
def muestra(muestra_id, datos=None):
    servicio = LaboratorioService()
    codigo = servicio.bd.escalar("SELECT codigo FROM muestra WHERE id = ?", (muestra_id,))
    if codigo is None:
        abort(404)
    return render_template("muestra.html", t=servicio.trazabilidad(codigo),
                           datos=datos or {"fecha_hora": ahora()})


@bp.post("/muestras/<int:muestra_id>")
@validar(muestra)
def registrar_resultado(muestra_id):
    f = request.form
    LaboratorioService().registrar_resultado(muestra_id, f.get("profesional", ""), f.get("valores", ""),
                                             f.get("conclusion", ""), f.get("observaciones", ""), f.get("fecha_hora"))
    flash("Resultado registrado. Se generó un aviso al responsable de la mascota.", "success")
    return redirect(url_for(".resultados"))


@bp.get("/trazabilidad")
def trazabilidad():
    codigo = request.args.get("codigo", "").strip()
    traza = None
    if codigo:
        try:
            traza = LaboratorioService().trazabilidad(codigo)
        except VeterinariaError as e:
            flash(str(e), "warning")
    return render_template("trazabilidad.html", codigo=codigo, t=traza)
