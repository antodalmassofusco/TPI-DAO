"""Parámetros generales de la aplicación."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_BD = RAIZ / "veterinaria.db"

FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M"

# Agenda médica
HORA_APERTURA = 8
HORA_CIERRE = 20
DURACION_TURNO_MIN = 30

ESPECIES = ("Perro", "Gato")
SEXOS = ("M", "H")
TIPOS_CONSULTA = ("CONSULTA", "CONTROL", "URGENCIA")
PRIORIDADES = ("NORMAL", "URGENTE")

# Precio de la atención clínica según tipo (en $)
PRECIOS_CONSULTA = {
    "CONSULTA": 18000.0,
    "CONTROL": 12000.0,
    "URGENCIA": 30000.0,
}
