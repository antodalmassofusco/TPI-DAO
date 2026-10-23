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


@dataclass
class ResultadoReporte:
    titulo: str
    columnas: list          # [(clave, título)]
    filas: list             # [dict]
    resumen: list = field(default_factory=list)   # líneas de texto
    grafico: tuple = None   # (clave_etiqueta, clave_valor) para un gráfico de barras
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


class Reporte(ABC):
    titulo: str = ""
    descripcion: str = ""
    columnas: list = []
    grafico: tuple = None
    usa_rango_fechas: bool = True

    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    # ---- Método plantilla ---------------------------------------------------
    def generar(self, **filtros) -> ResultadoReporte:
        filtros = self.validar_filtros(filtros)
        filas = self.obtener_datos(filtros)
        filas = self.procesar(filas, filtros)
        return ResultadoReporte(self.titulo, self.columnas, filas, self.resumir(filas, filtros),
                                self.grafico, self.datos_grafico(filas))

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

    def datos_grafico(self, filas: list) -> list:
        return filas

    # ---- Paso obligatorio ---------------------------------------------------
    @abstractmethod
    def obtener_datos(self, filtros: dict) -> list:
        ...


def porcentaje(parte, total):
    return round(100.0 * parte / total, 1) if total else 0.0
