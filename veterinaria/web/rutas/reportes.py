"""Reportes: tabla, resumen, gráfico (Chart.js) y descarga en CSV y PDF."""
from datetime import datetime, timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from veterinaria.excepciones import VeterinariaError
from veterinaria.reportes.reportes import CATEGORIAS, REPORTES
from veterinaria.utils.fechas import hoy, parse_fecha

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
    grafico = resultado.grafico_preparado() if resultado else None
    categoria = next(c for c in CATEGORIAS if clase in c[-1])
    return render_template("reportes.html", categorias=CATEGORIAS, categoria=categoria, clase=clase,
                           desde=desde, hasta=hasta, resultado=resultado, grafico=grafico)


@bp.get("/reportes/csv")
def descargar_csv():
    try:
        clase, _, _, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        return redirect(url_for(".reportes"))
    # el BOM inicial hace que Excel reconozca el archivo como UTF-8 (acentos)
    return Response("﻿" + resultado.a_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={clase.__name__}.csv"})


@bp.get("/reportes/pdf")
def descargar_pdf():
    try:
        clase, desde, hasta, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        return redirect(url_for(".reportes"))
    formato = "%d/%m/%Y"
    if clase.usa_rango_fechas:
        periodo = f"Período: {parse_fecha(desde).strftime(formato)} al {parse_fecha(hasta).strftime(formato)}"
    else:
        periodo = f"Calculado al {hoy().strftime(formato)}"
    try:
        contenido = resultado.a_pdf(f"{periodo} · Emitido el {datetime.now().strftime(formato + ' %H:%M')}")
    except ImportError:
        flash("Para exportar a PDF hay que instalar las dependencias: pip install -r requirements.txt", "warning")
        return redirect(url_for(".reportes", **request.args))
    return Response(contenido, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={clase.__name__}.pdf"})
