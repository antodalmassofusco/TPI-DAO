"""Exportación de un reporte a PDF como informe de gestión: conclusiones, resumen, gráfico y tabla.

Recibe el mismo ResultadoReporte que muestran la pantalla y el CSV, así que sirve para todos los
reportes sin tocar ninguno: dibuja cada gráfico según su tipo (barras, columnas, líneas o torta).
"""
import io
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from veterinaria.reportes.base import formato_valor
from veterinaria.utils.formato import moneda, numero

COLOR = colors.HexColor("#1f4e79")
COLOR_ACENTO = colors.HexColor("#2a78d6")
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


def _formato_eje(valor, unidad):
    """Marcas del eje; los pesos se abrevian en millones para que no se amontonen."""
    if unidad == "$" and abs(valor) >= 1_000_000:
        return f"$ {numero(valor / 1_000_000, 0 if float(valor / 1_000_000).is_integer() else 1)} M"
    return formato_valor(valor, unidad)


TEXTO_GRAFICO = colors.HexColor("#52514e")
GRILLA = colors.HexColor("#e3e8ef")


def _leyenda(dibujo, x, y, pares, columnas=True):
    ley = Legend()
    ley.x, ley.y = x, y
    ley.alignment = "right"
    if columnas:
        ley.columnMaximum, ley.deltax = 1, 110
    else:
        ley.columnMaximum, ley.deltay = len(pares), 14
    ley.fontName, ley.fontSize = "Helvetica", 7.5
    ley.boxAnchor = "nw"
    ley.dx = ley.dy = 7
    ley.colorNamePairs = pares
    dibujo.add(ley)


def _torta(g, ancho):
    """Torta con la leyenda al costado: nombre de cada porción, valor y porcentaje."""
    alto, diametro = 150, 120
    dibujo = Drawing(ancho, alto)
    torta = Pie()
    torta.x, torta.y, torta.width, torta.height = 10, 15, diametro, diametro
    torta.data = [float(v) for v in g["totales"]]
    torta.labels = None
    torta.startAngle, torta.direction = 90, "clockwise"
    for i, color in enumerate(g["colores"]):
        torta.slices[i].fillColor = colors.HexColor(color)
        torta.slices[i].strokeColor = colors.white
        torta.slices[i].strokeWidth = 1.2
    dibujo.add(torta)
    _leyenda(dibujo, diametro + 35, 15 + diametro / 2 + 7 * len(g["etiquetas"]),
             [(colors.HexColor(c), f"{e}: {p}") for c, e, p in zip(g["colores"], g["etiquetas"], g["puntas"])],
             columnas=False)
    return dibujo


def _lineas(g, ancho):
    """Una curva por serie, en orden cronológico, con un punto en cada período."""
    alto = 210
    dibujo = Drawing(ancho, alto)
    grafico = HorizontalLineChart()
    grafico.x, grafico.y = 60, 25
    grafico.width, grafico.height = ancho - 80, alto - 60
    grafico.data = [[float(v) for v in s["valores"]] for s in g["series"]]
    grafico.categoryAxis.categoryNames = g["etiquetas"]
    grafico.categoryAxis.labels.boxAnchor = "n"
    grafico.categoryAxis.strokeColor = colors.HexColor("#c8d0da")
    for eje in (grafico.categoryAxis.labels, grafico.valueAxis.labels):
        eje.fontName, eje.fontSize = "Helvetica", 7
    grafico.valueAxis.valueMin = 0
    grafico.valueAxis.labelTextFormat = lambda v: _formato_eje(v, g["unidad"])
    grafico.valueAxis.strokeColor = None
    grafico.valueAxis.visibleGrid = True
    grafico.valueAxis.gridStrokeColor = GRILLA
    grafico.valueAxis.gridStrokeWidth = 0.5
    for i, serie in enumerate(g["series"]):
        grafico.lines[i].strokeColor = colors.HexColor(serie["color"])
        grafico.lines[i].strokeWidth = 1.6
        grafico.lines[i].symbol = makeMarker("FilledCircle", size=3.5, fillColor=colors.HexColor(serie["color"]),
                                             strokeColor=colors.white, strokeWidth=0.8)
    dibujo.add(grafico)
    if g["leyenda"]:
        _leyenda(dibujo, grafico.x, alto - 6, [(colors.HexColor(s["color"]), s["titulo"]) for s in g["series"]])
    return dibujo


def _grafico(g, ancho):
    """Mismo gráfico que la pantalla, según su tipo."""
    if g["tipo"] == "torta":
        return _torta(g, ancho)
    if g["tipo"] == "lineas":
        return _lineas(g, ancho)
    horizontal = g["tipo"] == "barras"
    etiquetas, series = list(g["etiquetas"]), [list(s["valores"]) for s in g["series"]]
    if horizontal:
        # en reportlab la primera categoría queda abajo: se invierte para que la mayor quede arriba
        etiquetas.reverse()
        for valores in series:
            valores.reverse()
    leyenda = 22 if g["leyenda"] else 0
    puntas_texto = g["puntas"]
    alto = (30 + 18 * len(etiquetas) if horizontal else 200) + leyenda
    dibujo = Drawing(ancho, alto)
    if horizontal:
        barras = HorizontalBarChart()
        barras.x, barras.y = 170, 15
        # el ancho deja lugar al texto más largo de las puntas
        margen = max([stringWidth(t, "Helvetica-Bold", 6.5) for t in puntas_texto if t] + [20]) + 12
        barras.width, barras.height = ancho - 170 - margen, alto - 25 - leyenda
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
    barras.valueAxis.labelTextFormat = lambda v: _formato_eje(v, g["unidad"])
    barras.valueAxis.strokeColor = None
    barras.valueAxis.visibleGrid = True
    barras.valueAxis.gridStrokeColor = colors.HexColor("#e3e8ef")
    barras.valueAxis.gridStrokeWidth = 0.5
    barras.categoryAxis.strokeColor = colors.HexColor("#c8d0da")
    for i, serie in enumerate(g["series"]):
        barras.bars[i].fillColor = colors.HexColor(serie["color"])
        barras.bars[i].strokeColor = colors.white
        barras.bars[i].strokeWidth = 0.75 if len(series) > 1 else 0
    dibujo.add(barras)

    # Texto en la punta de cada barra o columna (total, % o lo que defina el reporte)
    totales, puntas = list(g["totales"]), list(g["puntas"])
    if horizontal:
        totales.reverse()
        puntas.reverse()
    # Se configura la escala igual que reportlab al dibujar (con las series acumuladas si están apiladas)
    # para poder ubicar los totales en la punta de cada barra
    barras.valueAxis.setPosition(barras.x, barras.y, barras.width if horizontal else barras.height)
    barras._getConfigureData()
    barras.valueAxis.configure(barras._configureData)
    for i, (total, texto) in enumerate(zip(totales, puntas)):
        if not texto:
            continue
        x, y = _punta(barras, i, total, horizontal)
        dibujo.add(String(x, y, texto, fontName="Helvetica-Bold", fontSize=6.5,
                          fillColor=colors.HexColor("#52514e"), textAnchor="start" if horizontal else "middle"))

    if g["leyenda"]:
        _leyenda(dibujo, barras.x, alto - 6, [(colors.HexColor(s["color"]), s["titulo"]) for s in g["series"]])
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


def _conclusiones(resultado, ancho, normal):
    """Recuadro con las conclusiones: lo primero que lee el dueño, con qué conviene hacer."""
    titulo = ParagraphStyle("conclusion_titulo", parent=normal, fontName="Helvetica-Bold", fontSize=10.5,
                            textColor=COLOR, spaceAfter=4)
    vineta = ParagraphStyle("conclusion", parent=normal, fontSize=9.5, leading=13, leftIndent=10, bulletIndent=0,
                            spaceAfter=3)
    contenido = [Paragraph("Conclusiones para la toma de decisiones", titulo)]
    contenido += [Paragraph(escape(linea), vineta, bulletText="•") for linea in resultado.conclusiones]
    recuadro = Table([[contenido]], colWidths=[ancho])
    recuadro.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef5fd")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, COLOR_ACENTO),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return recuadro


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

    antetitulo = ParagraphStyle("antetitulo", parent=normal, fontSize=8, textColor=colors.HexColor("#52514e"),
                                fontName="Helvetica-Bold", spaceAfter=2)
    elementos = [Paragraph("HUELLITAS · INFORME DE GESTIÓN", antetitulo),
                 Paragraph(escape(resultado.titulo), titulo)]
    if subtitulo:
        elementos.append(Paragraph(escape(subtitulo), normal))
    elementos.append(Spacer(1, 10))
    if resultado.conclusiones:
        elementos += [_conclusiones(resultado, ancho, normal), Spacer(1, 4)]

    if resultado.resumen:
        elementos.append(Paragraph("Resumen", seccion))
        for linea in resultado.resumen:
            sangria = 12 if linea.startswith("  ") else 0
            estilo = ParagraphStyle("linea", parent=normal, leftIndent=sangria)
            elementos.append(Paragraph(escape(linea.strip()), estilo))

    nota_estilo = ParagraphStyle("nota", parent=normal, fontSize=8, textColor=TEXTO_GRAFICO)
    graficos = resultado.graficos_preparados(MAX_BARRAS)
    k = 0
    while k < len(graficos):
        g = graficos[k]
        # dos tortas seguidas van una al lado de la otra
        if g["tipo"] == "torta" and k + 1 < len(graficos) and graficos[k + 1]["tipo"] == "torta":
            par = [g, graficos[k + 1]]
            celdas = [[Paragraph(escape(x["titulo"]), seccion) for x in par], [_torta(x, ancho / 2) for x in par]]
            tabla = Table(celdas, colWidths=[ancho / 2, ancho / 2])
            tabla.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            elementos.append(tabla)
            k += 2
            continue
        bloque = [Paragraph(escape(g["titulo"]), seccion), _grafico(g, ancho)]
        if g["nota"]:
            bloque.append(Paragraph(escape(g["nota"]), nota_estilo))
        elementos.append(KeepTogether(bloque))   # el título nunca queda separado de su gráfico
        k += 1

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
        lienzo.drawString(1.5 * cm, 0.8 * cm, f"Huellitas · Informe: {resultado.titulo}")
        lienzo.drawRightString(pagina[0] - 1.5 * cm, 0.8 * cm, f"Página {documento.page}")
        lienzo.restoreState()

    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
