"""Informes: tabla, resumen, conclusiones, gráficos (Chart.js) y descarga en CSV y PDF."""
from datetime import datetime, timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from veterinaria.excepciones import VeterinariaError
from veterinaria.reportes.reportes import CATEGORIAS, REPORTES
from veterinaria.utils.fechas import hoy, parse_fecha

bp = Blueprint("reportes", __name__)
CLAVES = {clase.__name__: clase for clase in REPORTES}
# Períodos predefinidos: desde el primer día del mes, del trimestre o del año hasta hoy
PERIODOS = [("mes", "Este mes"), ("trimestre", "Este trimestre"), ("anio", "Este año")]


def rango_periodo(periodo, dia=None):
    """(desde, hasta) del período predefinido, o None si no es uno de ellos."""
    dia = dia or hoy()
    if periodo == "mes":
        return dia.replace(day=1), dia
    if periodo == "trimestre":
        return dia.replace(month=(dia.month - 1) // 3 * 3 + 1, day=1), dia
    if periodo == "anio":
        return dia.replace(month=1, day=1), dia
    return None


def _generar():
    clave = request.args.get("reporte", REPORTES[0].__name__)
    clase = CLAVES.get(clave, REPORTES[0])
    periodo = request.args.get("periodo", "")
    rango = rango_periodo(periodo)
    if rango:
        desde, hasta = (d.isoformat() for d in rango)
    else:
        periodo = ""
        desde = request.args.get("desde") or (hoy() - timedelta(days=90)).isoformat()
        hasta = request.args.get("hasta") or hoy().isoformat()
    return clase, desde, hasta, periodo, clase().generar(desde=desde, hasta=hasta)


@bp.get("/reportes")
def reportes():
    try:
        clase, desde, hasta, periodo, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        clase, desde, hasta, periodo, resultado = REPORTES[0], "", "", "", None
    graficos = resultado.graficos_preparados() if resultado else []
    categoria = next(c for c in CATEGORIAS if clase in c[-1])
    return render_template("reportes.html", categorias=CATEGORIAS, categoria=categoria, clase=clase,
                           desde=desde, hasta=hasta, periodo=periodo, periodos=PERIODOS,
                           resultado=resultado, graficos=graficos)


@bp.get("/reportes/csv")
def descargar_csv():
    try:
        clase, _, _, _, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        return redirect(url_for(".reportes"))
    # el BOM inicial hace que Excel reconozca el archivo como UTF-8 (acentos)
    return Response("﻿" + resultado.a_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={clase.__name__.replace('Reporte', 'Informe')}.csv"})


@bp.get("/reportes/pdf")
def descargar_pdf():
    try:
        clase, desde, hasta, periodo, resultado = _generar()
    except VeterinariaError as e:
        flash(str(e), "warning")
        return redirect(url_for(".reportes"))
    categoria = next(c[0] for c in CATEGORIAS if clase in c[-1])
    formato = "%d/%m/%Y"
    if clase.usa_rango_fechas:
        nombre_periodo = dict(PERIODOS).get(periodo)
        rango = f"{parse_fecha(desde).strftime(formato)} al {parse_fecha(hasta).strftime(formato)}"
        texto_periodo = f"Período: {nombre_periodo.lower()} ({rango})" if nombre_periodo else f"Período: {rango}"
    else:
        texto_periodo = f"Calculado al {hoy().strftime(formato)}"
    try:
        contenido = resultado.a_pdf(f"{categoria} · {texto_periodo} · Emitido el {datetime.now().strftime(formato + ' %H:%M')}")
    except ImportError:
        flash("Para exportar a PDF hay que instalar las dependencias: pip install -r requirements.txt", "warning")
        return redirect(url_for(".reportes", **request.args))
    nombre = clase.__name__.replace("Reporte", "Informe")
    return Response(contenido, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={nombre}.pdf"})
