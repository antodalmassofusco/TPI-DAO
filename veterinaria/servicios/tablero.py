"""Indicadores del panel de inicio."""
from datetime import timedelta

from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.reportes.base import porcentaje
from veterinaria.servicios.notificaciones import NotificacionService
from veterinaria.servicios.turnos import TurnoService
from veterinaria.utils.fechas import hoy


class TableroService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    def resumen(self) -> dict:
        dia = hoy()
        hace_30 = (dia - timedelta(days=30)).isoformat()
        por_estado = {f["estado"]: f["n"] for f in self.bd.consultar(
            "SELECT estado, COUNT(*) AS n FROM muestra GROUP BY estado")}
        # tasa de rechazo en recepción de los últimos 30 días (según la bitácora de estados)
        llegadas = self.bd.consultar_uno("""
            SELECT SUM(h.estado_nuevo = 'RECHAZADA') AS rechazadas, COUNT(*) AS total
            FROM historial_estado_muestra h JOIN muestra mu ON mu.id = h.muestra_id
            WHERE h.estado_anterior = 'EN_TRANSITO' AND h.fecha_hora >= ?""", (hace_30,))
        return {
            "atenciones_30": self.bd.escalar("SELECT COUNT(*) FROM consulta WHERE fecha_hora >= ?", (hace_30,)),
            "atenciones_hoy": self.bd.escalar("SELECT COUNT(*) FROM consulta WHERE substr(fecha_hora, 1, 10) = ?",
                                              (dia.isoformat(),)),
            "en_circuito": sum(por_estado.get(e, 0) for e in ("EXTRAIDA", "EMPAQUETADA", "EN_TRANSITO", "RECIBIDA")),
            "tasa_rechazo": porcentaje(llegadas["rechazadas"] or 0, llegadas["total"] or 0),
            "rechazadas_30": llegadas["rechazadas"] or 0,
            "facturacion_mes": self.bd.escalar("SELECT COALESCE(SUM(total), 0) FROM comprobante WHERE fecha_hora >= ?",
                                               (dia.replace(day=1).isoformat(),)),
            "por_estado": por_estado,
            "turnos_hoy": TurnoService(self.bd).listar(fecha=dia.isoformat()),
            "avisos": NotificacionService(self.bd).listar(solo_pendientes=True)[:6],
        }
