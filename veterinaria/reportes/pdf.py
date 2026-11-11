"""Exportación de un reporte a PDF (título, resumen, gráfico y tabla).

Recibe el mismo ResultadoReporte que muestran la pantalla y el CSV, así que sirve para los
6 reportes sin tocar ninguno.
"""
import io
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from veterinaria.utils.formato import moneda, numero

COLOR = colors.HexColor("#1f4e79")
# Misma paleta categórica que el gráfico de la pantalla
PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MAX_BARRAS = 15


def _texto(valor, titulo_columna) -> str:
    """Mismo formato que la tabla de la pantalla: moneda en las columnas con '$'."""
    if valor is None:
        return ""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return str(valor)
    if "$" in titulo_columna:
        return moneda(valor)
    return numero(valor, 0 if float(valor).is_integer() else 1)


def _formato(valor, unidad):
    if unidad == "$":
        return f"$ {numero(valor, 0)}"
    texto = numero(valor, 0 if float(valor).is_integer() else 1)
    return f"{texto} h" if unidad == "h" else texto


def _grafico(resultado, ancho):
    """Mismo gráfico que la pantalla: barras horizontales (apiladas si hay varias series) o columnas."""
    g = resultado.grafico_preparado(MAX_BARRAS)
    if not g:
        return None
    horizontal = g["tipo"] == "barras"
    etiquetas, series = list(g["etiquetas"]), [list(s["valores"]) for s in g["series"]]
    if horizontal:
        # en reportlab la primera categoría queda abajo: se invierte para que la mayor quede arriba
        etiquetas.reverse()
        for valores in series:
            valores.reverse()
    leyenda = 22 if len(series) > 1 else 0
    alto = (30 + 18 * len(etiquetas) if horizontal else 200) + leyenda
    dibujo = Drawing(ancho, alto)
    if horizontal:
        barras = HorizontalBarChart()
        barras.x, barras.y = 170, 15
        barras.width, barras.height = ancho - 250, alto - 25 - leyenda
        barras.categoryAxis.labels.boxAnchor = "e"
        barras.categoryAxis.categoryNames = [e[:32] for e in etiquetas]
    else:
        barras = VerticalBarChart()
        barras.x, barras.y = 50, 25
        barras.width, barras.height = ancho - 70, alto - 45 - leyenda
        barras.categoryAxis.categoryNames = etiquetas
        barras.categoryAxis.labels.boxAnchor = "n"
    barras.data = [[float(v) for v in valores] for valores in series]
    if len(series) > 1:
        barras.categoryAxis.style = "stacked"
    for eje in (barras.categoryAxis.labels, barras.valueAxis.labels):
        eje.fontName, eje.fontSize = "Helvetica", 7
    barras.valueAxis.valueMin = 0
    barras.valueAxis.labelTextFormat = lambda v: _formato(v, g["unidad"])
    barras.valueAxis.strokeColor = None
    barras.valueAxis.visibleGrid = True
    barras.valueAxis.gridStrokeColor = colors.HexColor("#e3e8ef")
    barras.valueAxis.gridStrokeWidth = 0.5
    barras.categoryAxis.strokeColor = colors.HexColor("#c8d0da")
    for i, serie in enumerate(g["series"]):
        barras.bars[i].fillColor = colors.HexColor(PALETA[serie["color"]])
        barras.bars[i].strokeColor = colors.white
        barras.bars[i].strokeWidth = 0.75 if len(series) > 1 else 0
    dibujo.add(barras)

    # Total escrito en la punta de cada barra o columna
    totales = list(g["totales"])
    if horizontal:
        totales.reverse()
    # Se configura la escala igual que reportlab al dibujar (con las series acumuladas si están apiladas)
    # para poder ubicar los totales en la punta de cada barra
    barras.valueAxis.setPosition(barras.x, barras.y, barras.width if horizontal else barras.height)
    barras._getConfigureData()
    barras.valueAxis.configure(barras._configureData)
    for i, total in enumerate(totales):
        if not total:
            continue
        x, y = _punta(barras, i, total, horizontal)
        dibujo.add(String(x, y, _formato(total, g["unidad"]), fontName="Helvetica-Bold", fontSize=6.5,
                          fillColor=colors.HexColor("#52514e"), textAnchor="start" if horizontal else "middle"))

    if len(series) > 1:
        ley = Legend()
        ley.x, ley.y = barras.x, alto - 6
        ley.alignment = "right"
        ley.columnMaximum = 1
        ley.deltax = 110
        ley.fontName, ley.fontSize = "Helvetica", 7
        ley.boxAnchor = "nw"
        ley.dx = ley.dy = 7
        ley.colorNamePairs = [(colors.HexColor(PALETA[s["color"]]), s["titulo"]) for s in g["series"]]
        dibujo.add(ley)
    return dibujo


def _punta(barras, i, total, horizontal):
    """Posición en el dibujo del extremo de la barra i, según la escala del eje de valores."""
    eje = barras.valueAxis
    n = len(barras.categoryAxis.categoryNames)
    if horizontal:
        paso = barras.height / n
        return eje.scale(total) + 4, barras.y + paso * (i + 0.5) - 2.5
    paso = barras.width / n
    return barras.x + paso * (i + 0.5), eje.scale(total) + 3


def generar_pdf(resultado, subtitulo: str = "") -> bytes:
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], textColor=COLOR, alignment=0, fontSize=18)
    normal = ParagraphStyle("normal", parent=estilos["Normal"], fontSize=9, leading=12)
    seccion = ParagraphStyle("seccion", parent=estilos["Heading3"], textColor=COLOR, spaceBefore=10)
    celda = ParagraphStyle("celda", parent=normal, fontSize=7, leading=9)
    encabezado = ParagraphStyle("encabezado", parent=celda, textColor=colors.white, fontName="Helvetica-Bold")

    salida = io.BytesIO()
    pagina = landscape(A4)
    doc = SimpleDocTemplate(salida, pagesize=pagina, title=resultado.titulo, author="Huellitas",
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    ancho = pagina[0] - 3 * cm

    elementos = [Paragraph(escape(resultado.titulo), titulo)]
    if subtitulo:
        elementos.append(Paragraph(escape(subtitulo), normal))
    elementos.append(Spacer(1, 8))

    if resultado.resumen:
        elementos.append(Paragraph("Resumen", seccion))
        for linea in resultado.resumen:
            sangria = 12 if linea.startswith("  ") else 0
            estilo = ParagraphStyle("linea", parent=normal, leftIndent=sangria)
            elementos.append(Paragraph(escape(linea.strip()), estilo))

    grafico = _grafico(resultado, ancho)
    if grafico:
        elementos += [Paragraph(escape(resultado.grafico.titulo), seccion), grafico]

    elementos.append(Paragraph(f"Detalle ({len(resultado.filas)} filas)", seccion))
    titulos = [t for _, t in resultado.columnas]
    filas = [[Paragraph(escape(t), encabezado) for t in titulos]]
    for fila in resultado.filas:
        filas.append([Paragraph(escape(_texto(fila.get(clave), t)), celda) for clave, t in resultado.columnas])
    if not resultado.filas:
        filas.append([Paragraph("No hay datos para el período elegido.", celda)] + [""] * (len(titulos) - 1))
    tabla = Table(filas, colWidths=[ancho / len(titulos)] * len(titulos), repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d0da")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elementos.append(tabla)

    def pie(lienzo, documento):
        lienzo.saveState()
        lienzo.setFont("Helvetica", 7)
        lienzo.setFillColor(colors.grey)
        lienzo.drawString(1.5 * cm, 0.8 * cm, f"Huellitas · {resultado.titulo}")
        lienzo.drawRightString(pagina[0] - 1.5 * cm, 0.8 * cm, f"Página {documento.page}")
        lienzo.restoreState()

    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
