"""Utilidades de fechas. En la base todo se guarda como texto ISO ('AAAA-MM-DD HH:MM'),
que se ordena y compara correctamente como string."""
import calendar
from datetime import date, datetime, timedelta

from veterinaria.config import FORMATO_FECHA, FORMATO_FECHA_HORA
from veterinaria.excepciones import ValidacionError


def ahora() -> str:
    return datetime.now().strftime(FORMATO_FECHA_HORA)


def hoy() -> date:
    return date.today()


def parse_fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor).strip()[:10], FORMATO_FECHA).date()
    except (ValueError, TypeError):
        raise ValidacionError(f"Fecha inválida '{valor}'. Formato esperado: AAAA-MM-DD.")


def parse_fecha_hora(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor.replace(second=0, microsecond=0)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    texto = str(valor or "").strip().replace("T", " ")   # admite el formato de <input type="datetime-local">
    for formato in (FORMATO_FECHA_HORA, "%Y-%m-%d %H:%M:%S", FORMATO_FECHA):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    raise ValidacionError(f"Fecha/hora inválida '{valor}'. Formato esperado: AAAA-MM-DD HH:MM.")


def formatear(dt: datetime) -> str:
    return dt.strftime(FORMATO_FECHA_HORA)


def normalizar(valor) -> str:
    """Convierte cualquier fecha/hora aceptada al formato canónico de la base."""
    return formatear(parse_fecha_hora(valor))


def sumar_meses(d: date, meses: int) -> date:
    mes = d.month - 1 + meses
    anio = d.year + mes // 12
    mes = mes % 12 + 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def meses_entre(desde: date, hasta: date) -> int:
    meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month
    if hasta.day < desde.day:
        meses -= 1
    return meses


def horas_entre(desde, hasta) -> float:
    return (parse_fecha_hora(hasta) - parse_fecha_hora(desde)) / timedelta(hours=1)
