"""Resumen diario de un veterinario: turnos, atenciones, derivaciones y resultados que llegaron."""
from veterinaria.dominio.muestra import ETIQUETAS_ESTADO
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.servicios.turnos import TurnoService
from veterinaria.utils.fechas import parse_fecha


class MiDiaService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    def resumen(self, veterinario_id: int, fecha) -> dict:
        dia = parse_fecha(fecha).isoformat()
        turnos = TurnoService(self.bd).listar(dia, veterinario_id)
        atenciones = self.bd.consultar("""
            SELECT co.id, substr(co.fecha_hora, 12, 5) AS hora, co.tipo, co.motivo, co.diagnostico,
                   m.id AS mascota_id, m.nombre AS mascota, m.especie,
                   (SELECT COUNT(*) FROM muestra mu JOIN orden_derivacion o ON o.id = mu.orden_id
                    WHERE o.consulta_id = co.id) AS muestras
            FROM consulta co JOIN mascota m ON m.id = co.mascota_id
            WHERE co.veterinario_id = ? AND substr(co.fecha_hora, 1, 10) = ?
            ORDER BY co.fecha_hora""", (veterinario_id, dia))
        derivadas = self.bd.consultar("""
            SELECT mu.codigo, mu.estado, ta.nombre AS analisis, m.nombre AS mascota, o.prioridad
            FROM muestra mu
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            WHERE co.veterinario_id = ? AND substr(co.fecha_hora, 1, 10) = ?
            ORDER BY mu.codigo""", (veterinario_id, dia))
        # Resultados de sus pacientes que se cerraron ese día (analizados o rechazados), según la bitácora
        resultados = self.bd.consultar("""
            SELECT mu.codigo, mu.estado, mu.motivo_rechazo, ta.nombre AS analisis, m.nombre AS mascota,
                   substr(h.fecha_hora, 12, 5) AS hora, re.conclusion
            FROM historial_estado_muestra h
            JOIN muestra mu ON mu.id = h.muestra_id
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            LEFT JOIN resultado re ON re.muestra_id = mu.id
            WHERE co.veterinario_id = ? AND substr(h.fecha_hora, 1, 10) = ?
              AND h.estado_nuevo IN ('ANALIZADA', 'RECHAZADA')
            ORDER BY h.fecha_hora""", (veterinario_id, dia))
        for fila in derivadas + resultados:
            fila["estado_etiqueta"] = ETIQUETAS_ESTADO[fila["estado"]]
        return {
            "turnos": turnos, "atenciones": atenciones, "derivadas": derivadas, "resultados": resultados,
            "indicadores": {
                "turnos": len(turnos),
                "atendidos": sum(t["estado"] == "ATENDIDO" for t in turnos),
                "pendientes": sum(t["estado"] == "PENDIENTE" for t in turnos),
                "atenciones": len(atenciones),
                "derivadas": len(derivadas),
                "resultados": len(resultados),
                "rechazadas": sum(r["estado"] == "RECHAZADA" for r in resultados),
            },
        }
