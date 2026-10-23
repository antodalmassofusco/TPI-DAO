"""Reportes: tabla, resumen, gráfico (Chart.js) y descarga en CSV."""
from datetime import timedelta

from flask import Blueprint, Response, flash, render_template, request

from veterinaria.excepciones import VeterinariaError
from veterinaria.reportes.reportes import REPORTES
from veterinaria.utils.fechas import hoy

bp = Blueprint("reportes", __name__)
CLAVES = {clase.__name__: clase for clase in REPORTES}


def _generar():
    clave = request.args.get("reporte", REPORTES[0].__name__)
    clase = CLAVES.get(clave, REPORTES[0])
    desde = request.args.get("desde") or (hoy() - timedelta(days=90)).isoformat()
    hasta = request.args.get("hasta") or hoy().isoformat()
    return clase, desde, hasta, clase().generar(desde=desde, hasta=hasta)


@bp.get("/reportes")
def reportes():
    try:
        clase, desde, hasta, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        clase, desde, hasta, resultado = REPORTES[0], "", "", None
    grafico = None
    if resultado and resultado.grafico and resultado.datos_grafico:
        etiqueta, valor = resultado.grafico
        datos = sorted((d for d in resultado.datos_grafico if d.get(valor)), key=lambda d: d[valor], reverse=True)[:15]
        grafico = {"etiquetas": [str(d[etiqueta]) for d in datos], "valores": [d[valor] for d in datos],
                   "titulo": dict(resultado.columnas).get(valor, valor.capitalize())}
    return render_template("reportes.html", reportes=REPORTES, clase=clase, desde=desde, hasta=hasta,
                           resultado=resultado, grafico=grafico)


@bp.get("/reportes/csv")
def descargar_csv():
    clase, _, _, resultado = _generar()
    # el BOM inicial hace que Excel reconozca el archivo como UTF-8 (acentos)
    return Response("﻿" + resultado.a_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={clase.__name__}.csv"})
