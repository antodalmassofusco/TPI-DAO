"""Patrón Template Method para reportes.

`Reporte.generar()` define el algoritmo fijo (validar filtros → obtener datos → procesar →
resumir → datos del gráfico → concluir) y cada reporte concreto redefine sólo los pasos que le
son propios.
"""
import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.utils.fechas import parse_fecha
from veterinaria.utils.formato import numero


# Colores de los gráficos (paleta validada para daltonismo; se comparten entre la pantalla y el PDF)
CATEGORICA = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SECUENCIAL = ("#86b6ef", "#2a78d6", "#104281")   # un solo tono, de claro a oscuro: categorías ordenadas
CONTEXTO = "#c3c2b7"                            # gris para lo que es contexto y no protagonista


@dataclass(frozen=True)
class Grafico:
    """Qué gráfico acompaña a un reporte, elegido según la pregunta que tiene que responder.

    tipo
      - "barras": barras horizontales para comparar categorías (clínicas, vacunas, etc.); con más de
        una serie se apilan, así se ve el total y cómo se compone.
      - "columnas": columnas verticales en orden cronológico, para la evolución en el tiempo; se
        rotulan sólo el pico y el último período.
      - "lineas": una curva por serie en orden cronológico, para comparar cómo evolucionan varias series.
      - "torta": cómo se reparte un total entre pocas partes (hasta 6; el resto se agrupa en "Otros").
        Cada fila es una porción y la única serie es su valor.
    paleta
      - "categorica": series distintas entre sí (servicios, causas, etapas).
      - "enfasis": la primera serie es la protagonista (color) y el resto es contexto (gris).
      - "secuencial": series ordenadas de menor a mayor (por ejemplo, rangos de atraso).
    punta: clave de la fila con el texto a escribir en la punta de cada barra (por defecto, el total).
    """
    etiqueta: str           # clave de la categoría (eje)
    series: tuple           # ((clave, título), ...) en orden fijo: el color sigue a la serie, no a su posición
    titulo: str
    tipo: str = "barras"
    unidad: str = ""        # "$", "h", "%" o "" (cantidades)
    paleta: str = "categorica"
    punta: str = None
    omitir_vacias: bool = True   # en barras, ocultar las categorías sin valores

    MAX_PORCIONES = 6

    @property
    def apilado(self):
        return self.tipo in ("barras", "columnas") and len(self.series) > 1

    def colores(self):
        if self.paleta == "enfasis":
            return [CATEGORICA[0]] + [CONTEXTO] * (len(self.series) - 1)
        if self.paleta == "secuencial":
            return list(SECUENCIAL[-len(self.series):]) if len(self.series) < len(SECUENCIAL) else list(SECUENCIAL)
        return list(CATEGORICA[:len(self.series)])


def formato_valor(valor, unidad=""):
    """Número con formato argentino y su unidad: $ 1.234, 4,5 h, 12,3 %, 18."""
    if unidad == "$":
        return f"$ {numero(valor, 0)}"
    texto = numero(valor, 0 if float(valor).is_integer() else 1)
    return {"h": f"{texto} h", "%": f"{texto} %"}.get(unidad, texto)


@dataclass
class ResultadoReporte:
    titulo: str
    columnas: list          # [(clave, título)]
    filas: list             # [dict]
    resumen: list = field(default_factory=list)          # líneas de texto
    graficos: tuple = ()                                 # (Grafico, ...) que acompañan al reporte
    datos_graficos: list = field(default_factory=list)   # las filas de cada gráfico, en el mismo orden
    conclusiones: list = field(default_factory=list)     # lecturas de los datos para decidir

    def a_csv(self) -> str:
        """Contenido CSV (separado por ';' para que Excel en español lo abra en columnas)."""
        salida = io.StringIO()
        escritor = csv.writer(salida, delimiter=";")
        escritor.writerow([titulo for _, titulo in self.columnas])
        for fila in self.filas:
            escritor.writerow([fila.get(clave, "") for clave, _ in self.columnas])
        if self.resumen:
            escritor.writerow([])
            for linea in self.resumen:
                escritor.writerow([linea])
        return salida.getvalue()

    def graficos_preparados(self, max_categorias: int = 15) -> list:
        """Los gráficos listos para dibujar (Chart.js en pantalla, reportlab en el PDF); se omiten los vacíos."""
        preparados = (_preparar(g, datos, max_categorias) for g, datos in zip(self.graficos, self.datos_graficos))
        return [p for p in preparados if p]

    def grafico_preparado(self, max_categorias: int = 15):
        """El primer gráfico del reporte (o None si no tiene datos para graficar)."""
        preparados = self.graficos_preparados(max_categorias)
        return preparados[0] if preparados else None

    def a_pdf(self, subtitulo: str = "") -> bytes:
        """Contenido PDF con el resumen, el gráfico y la tabla del reporte."""
        from veterinaria.reportes.pdf import generar_pdf   # import diferido: reportlab sólo hace falta acá
        return generar_pdf(self, subtitulo)


def _preparar(g: Grafico, datos: list, max_categorias: int):
    """Arma los datos de un gráfico: orden, colores, textos de las puntas y notas.

    Las barras se ordenan de mayor a menor total y se limitan a `max_categorias`; las columnas y las
    líneas (series de tiempo) mantienen el orden cronológico. Cada serie conserva su color aunque otras
    queden vacías. En la torta, el color sigue a cada porción según el orden en que llegan los datos.
    """
    if not datos:
        return None
    if g.tipo == "torta":
        return _preparar_torta(g, datos)
    filas = [{**d, "_total": sum(d.get(clave) or 0 for clave, _ in g.series)} for d in datos]
    omitidas = 0
    if g.tipo == "barras":
        filas = sorted((d for d in filas if d["_total"] or not g.omitir_vacias),
                       key=lambda d: d["_total"], reverse=True)
        omitidas = max(0, len(filas) - max_categorias)
        filas = filas[:max_categorias]
    if not any(d["_total"] for d in filas):
        return None

    def punta(i, d):
        if g.tipo == "lineas":
            return None   # las curvas se leen con la leyenda y el detalle al pasar el mouse
        if g.tipo == "columnas":
            # serie de tiempo: sólo el pico y el último período con datos, para no llenar el gráfico de números
            con_datos = [k for k in range(len(filas)) if filas[k]["_total"]]
            pico = max(con_datos, key=lambda k: filas[k]["_total"])
            if i not in (pico, con_datos[-1]):
                return None
        if g.punta:
            return d.get(g.punta)
        return formato_valor(round(d["_total"], 1), g.unidad)

    colores = g.colores()
    series = [{"titulo": titulo, "color": colores[i], "valores": [d.get(clave) or 0 for d in filas]}
              for i, (clave, titulo) in enumerate(g.series)]
    return {"titulo": g.titulo, "tipo": g.tipo, "unidad": g.unidad,
            "etiquetas": [str(d[g.etiqueta]) for d in filas],
            "totales": [round(d["_total"], 2) for d in filas],
            "puntas": [punta(i, d) for i, d in enumerate(filas)],
            "series": [s for s in series if any(s["valores"])],
            "leyenda": len(g.series) > 1,   # con varias series declaradas, siempre (aunque haya datos de una sola)
            "nota": (f"Se muestran las {len(filas)} de mayor valor; las otras {omitidas} están en la tabla."
                     if omitidas else "")}


def _preparar_torta(g: Grafico, datos: list):
    clave = g.series[0][0]
    porciones = [(str(d[g.etiqueta]), d.get(clave) or 0, CATEGORICA[i % len(CATEGORICA)])
                 for i, d in enumerate(datos)]
    porciones = [p for p in porciones if p[1]]
    if not porciones:
        return None
    if len(porciones) > g.MAX_PORCIONES:
        principales = sorted(porciones, key=lambda p: -p[1])[:g.MAX_PORCIONES - 1]
        resto = sum(p[1] for p in porciones if p not in principales)
        porciones = [p for p in porciones if p in principales] + [("Otros", resto, CONTEXTO)]
    total = sum(p[1] for p in porciones)
    valores = [round(p[1], 2) for p in porciones]
    return {"titulo": g.titulo, "tipo": "torta", "unidad": g.unidad,
            "etiquetas": [p[0] for p in porciones], "totales": valores,
            "colores": [p[2] for p in porciones],
            "puntas": [f"{formato_valor(v, g.unidad)} ({numero(porcentaje(v, total), 0)} %)" for v in valores],
            "series": [{"titulo": g.series[0][1], "color": None, "valores": valores}],
            "leyenda": True, "nota": ""}


class Reporte(ABC):
    titulo: str = ""
    descripcion: str = ""
    columnas: list = []
    grafico: Grafico = None   # un solo gráfico...
    graficos: tuple = ()      # ...o varios; en ese caso datos_grafico() devuelve una lista de filas por gráfico
    usa_rango_fechas: bool = True

    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    # ---- Método plantilla ---------------------------------------------------
    def generar(self, **filtros) -> ResultadoReporte:
        filtros = self.validar_filtros(filtros)
        filas = self.obtener_datos(filtros)
        filas = self.procesar(filas, filtros)
        graficos = self.graficos or ((self.grafico,) if self.grafico else ())
        datos = self.datos_grafico(filas, filtros) if graficos else []
        datos_graficos = list(datos) if self.graficos else [datos]
        return ResultadoReporte(self.titulo, self.columnas, filas, self.resumir(filas, filtros),
                                graficos, datos_graficos[:len(graficos)],
                                self.concluir(filas, filtros) if filas else [])

    # ---- Pasos con comportamiento por defecto (hooks) -------------------------
    def validar_filtros(self, filtros: dict) -> dict:
        if self.usa_rango_fechas:
            desde = parse_fecha(filtros.get("desde"))
            hasta = parse_fecha(filtros.get("hasta"))
            if desde > hasta:
                raise ValidacionError("La fecha 'desde' no puede ser posterior a 'hasta'.")
            filtros["desde"] = desde.isoformat()
            filtros["hasta_incl"] = f"{hasta.isoformat()} 23:59"
            filtros["hasta"] = hasta.isoformat()
        return filtros

    def procesar(self, filas: list, filtros: dict) -> list:
        return filas

    def resumir(self, filas: list, filtros: dict) -> list:
        return [f"Registros: {len(filas)}"]

    def datos_grafico(self, filas: list, filtros: dict) -> list:
        return filas

    def concluir(self, filas: list, filtros: dict) -> list:
        """Conclusiones para los dueños: qué muestran los datos y qué conviene hacer."""
        return []

    # ---- Paso obligatorio ---------------------------------------------------
    @abstractmethod
    def obtener_datos(self, filtros: dict) -> list:
        ...


def porcentaje(parte, total):
    return round(100.0 * parte / total, 1) if total else 0.0
