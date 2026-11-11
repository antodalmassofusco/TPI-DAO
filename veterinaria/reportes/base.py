"""Patrón Template Method para reportes.

`Reporte.generar()` define el algoritmo fijo (validar filtros → obtener datos → procesar →
resumir) y cada reporte concreto redefine sólo los pasos que le son propios.
"""
import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.utils.fechas import parse_fecha


@dataclass(frozen=True)
class Grafico:
    """Qué gráfico acompaña a un reporte, elegido según lo que muestran los datos.

    - "barras": barras horizontales para comparar categorías (clínicas, vacunas, etc.); con más de
      una serie se apilan, así se ve el total y cómo se compone.
    - "columnas": columnas verticales en orden cronológico, para la evolución en el tiempo.
    """
    etiqueta: str           # clave de la categoría (eje)
    series: tuple           # ((clave, título), ...) en orden fijo: el color sigue a la serie, no a su posición
    titulo: str
    tipo: str = "barras"
    unidad: str = ""        # "$", "h" o "" (cantidades)

    @property
    def apilado(self):
        return len(self.series) > 1


@dataclass
class ResultadoReporte:
    titulo: str
    columnas: list          # [(clave, título)]
    filas: list             # [dict]
    resumen: list = field(default_factory=list)   # líneas de texto
    grafico: Grafico = None
    datos_grafico: list = None

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

    def grafico_preparado(self, max_categorias: int = 15):
        """Datos del gráfico listos para dibujar (Chart.js en pantalla, reportlab en el PDF).

        Las barras se ordenan de mayor a menor total; las columnas (series de tiempo) mantienen el orden
        cronológico. Cada serie conserva su número de color aunque otras queden vacías.
        """
        g = self.grafico
        if not g or not self.datos_grafico:
            return None
        filas = [{**d, "_total": sum(d.get(clave) or 0 for clave, _ in g.series)} for d in self.datos_grafico]
        if g.tipo == "barras":
            filas = sorted((d for d in filas if d["_total"]), key=lambda d: d["_total"], reverse=True)[:max_categorias]
        if not any(d["_total"] for d in filas):
            return None
        series = [{"titulo": titulo, "color": i, "valores": [d.get(clave) or 0 for d in filas]}
                  for i, (clave, titulo) in enumerate(g.series)]
        return {"titulo": g.titulo, "tipo": g.tipo, "unidad": g.unidad,
                "etiquetas": [str(d[g.etiqueta]) for d in filas],
                "totales": [round(d["_total"], 2) for d in filas],
                "series": [s for s in series if any(s["valores"])]}

    def a_pdf(self, subtitulo: str = "") -> bytes:
        """Contenido PDF con el resumen, el gráfico y la tabla del reporte."""
        from veterinaria.reportes.pdf import generar_pdf   # import diferido: reportlab sólo hace falta acá
        return generar_pdf(self, subtitulo)


class Reporte(ABC):
    titulo: str = ""
    descripcion: str = ""
    columnas: list = []
    grafico: Grafico = None
    usa_rango_fechas: bool = True

    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    # ---- Método plantilla ---------------------------------------------------
    def generar(self, **filtros) -> ResultadoReporte:
        filtros = self.validar_filtros(filtros)
        filas = self.obtener_datos(filtros)
        filas = self.procesar(filas, filtros)
        return ResultadoReporte(self.titulo, self.columnas, filas, self.resumir(filas, filtros),
                                self.grafico, self.datos_grafico(filas, filtros))

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

    # ---- Paso obligatorio ---------------------------------------------------
    @abstractmethod
    def obtener_datos(self, filtros: dict) -> list:
        ...


def porcentaje(parte, total):
    return round(100.0 * parte / total, 1) if total else 0.0
