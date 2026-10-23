"""Reportes concretos."""
from collections import defaultdict

from veterinaria.persistencia import repositorios as r
from veterinaria.reportes.base import Reporte, porcentaje
from veterinaria.servicios.vacunas import VacunaService
from veterinaria.utils.fechas import hoy
from veterinaria.utils.formato import moneda, numero


class ReporteAtencionesDerivaciones(Reporte):
    titulo = "Atenciones clínicas y derivaciones"
    descripcion = ("Cantidad de atenciones por clínica y tipo, cuántas derivaron análisis al laboratorio "
                   "y el porcentaje de derivación.")
    columnas = [("clinica", "Clínica"), ("tipo", "Tipo de atención"), ("atenciones", "Atenciones"),
                ("con_derivacion", "Con derivación"), ("pct_derivacion", "% derivación"),
                ("muestras", "Muestras derivadas"), ("urgentes", "Órdenes urgentes")]
    grafico = ("etiqueta", "atenciones")

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT cl.nombre AS clinica, co.tipo,
                   COUNT(*) AS atenciones,
                   SUM(EXISTS (SELECT 1 FROM orden_derivacion o WHERE o.consulta_id = co.id)) AS con_derivacion,
                   SUM((SELECT COUNT(*) FROM muestra mu JOIN orden_derivacion o ON o.id = mu.orden_id
                        WHERE o.consulta_id = co.id)) AS muestras,
                   SUM((SELECT COUNT(*) FROM orden_derivacion o
                        WHERE o.consulta_id = co.id AND o.prioridad = 'URGENTE')) AS urgentes
            FROM consulta co JOIN clinica cl ON cl.id = co.clinica_id
            WHERE co.fecha_hora BETWEEN ? AND ?
            GROUP BY cl.nombre, co.tipo ORDER BY cl.nombre, co.tipo""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        for fila in filas:
            fila["pct_derivacion"] = porcentaje(fila["con_derivacion"], fila["atenciones"])
            fila["etiqueta"] = f"{fila['clinica'].replace('Clínica ', '')} · {fila['tipo'].title()}"
        return filas

    def resumir(self, filas, f):
        total = sum(x["atenciones"] for x in filas)
        derivadas = sum(x["con_derivacion"] for x in filas)
        muestras = sum(x["muestras"] for x in filas)
        por_clinica = defaultdict(int)
        for x in filas:
            por_clinica[x["clinica"]] += x["atenciones"]
        lider = max(por_clinica, key=por_clinica.get) if por_clinica else "-"
        return [f"Total de atenciones: {total} — derivaron a laboratorio: {derivadas} "
                f"({numero(porcentaje(derivadas, total), 1)} %) — muestras enviadas: {muestras}",
                f"Clínica con más atenciones: {lider}"]


class ReporteMuestrasRechazadas(Reporte):
    titulo = "Muestras rechazadas por fallas en el transporte"
    descripcion = ("Detalle de muestras rechazadas en la recepción, causa (precinto roto, cadena de frío, "
                   "viabilidad) y tasa de rechazo por transportista.")
    columnas = [("codigo", "Muestra"), ("fecha_rechazo", "Fecha rechazo"), ("clinica", "Clínica"),
                ("analisis", "Análisis"), ("remito", "Remito"), ("transportista", "Transportista"),
                ("causa", "Causa"), ("motivo_rechazo", "Detalle")]
    grafico = ("causa", "cantidad")

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT mu.codigo, h.fecha_hora AS fecha_rechazo, cl.nombre AS clinica, ta.nombre AS analisis,
                   re.numero AS remito, e.transportista, mu.motivo_rechazo
            FROM muestra mu
            JOIN historial_estado_muestra h ON h.muestra_id = mu.id AND h.estado_nuevo = 'RECHAZADA'
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN remito re ON re.id = mu.remito_id
            JOIN clinica cl ON cl.id = re.clinica_id
            JOIN envio e ON e.remito_id = re.id
            WHERE h.fecha_hora BETWEEN ? AND ?
            ORDER BY h.fecha_hora DESC""", (f["desde"], f["hasta_incl"]))

    @staticmethod
    def _causa(motivo):
        motivo = (motivo or "").lower()
        if "precinto" in motivo:
            return "Precinto roto"
        if "frío" in motivo or "frio" in motivo:
            return "Cadena de frío"
        if "viable" in motivo:
            return "Tiempo de viabilidad"
        return "Otra"

    def procesar(self, filas, f):
        for fila in filas:
            fila["causa"] = self._causa(fila["motivo_rechazo"])
        return filas

    def resumir(self, filas, f):
        totales = self.bd.consultar("""
            SELECT e.transportista, COUNT(mu.id) AS enviadas,
                   SUM(mu.estado = 'RECHAZADA') AS rechazadas
            FROM envio e JOIN muestra mu ON mu.remito_id = e.remito_id
            WHERE e.fecha_llegada BETWEEN ? AND ?
            GROUP BY e.transportista ORDER BY rechazadas DESC""", (f["desde"], f["hasta_incl"]))
        por_causa = defaultdict(int)
        for fila in filas:
            por_causa[fila["causa"]] += 1
        enviadas = sum(t["enviadas"] for t in totales)
        lineas = [f"Muestras rechazadas: {len(filas)} de {enviadas} recibidas "
                  f"({numero(porcentaje(len(filas), enviadas), 1)} %)",
                  "Por causa: " + (", ".join(f"{c}: {n}" for c, n in por_causa.items()) or "-")]
        lineas += [f"  {t['transportista']}: {t['rechazadas']}/{t['enviadas']} rechazadas "
                   f"({numero(porcentaje(t['rechazadas'], t['enviadas']), 1)} %)" for t in totales]
        return lineas

    def datos_grafico(self, filas):
        # El gráfico muestra la cantidad por causa en lugar del detalle
        por_causa = defaultdict(int)
        for fila in filas:
            por_causa[fila["causa"]] += 1
        return [{"causa": c, "cantidad": n} for c, n in por_causa.items()]


class ReporteTratamientos(Reporte):
    titulo = "Tratamientos aplicados"
    descripcion = "Atenciones con diagnóstico, tratamiento indicado y vacunas aplicadas en el período."
    columnas = [("fecha_hora", "Fecha"), ("clinica", "Clínica"), ("mascota", "Paciente"), ("especie", "Especie"),
                ("tipo", "Tipo"), ("diagnostico", "Diagnóstico"), ("tratamiento", "Tratamiento"),
                ("vacunas", "Vacunas aplicadas")]

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT co.fecha_hora, cl.nombre AS clinica, m.nombre AS mascota, m.especie, co.tipo,
                   co.diagnostico, co.tratamiento,
                   COALESCE((SELECT GROUP_CONCAT(tv.nombre, ', ') FROM vacuna_aplicada va
                             JOIN tipo_vacuna tv ON tv.id = va.tipo_vacuna_id
                             WHERE va.consulta_id = co.id), '') AS vacunas
            FROM consulta co
            JOIN clinica cl ON cl.id = co.clinica_id
            JOIN mascota m ON m.id = co.mascota_id
            WHERE co.fecha_hora BETWEEN ? AND ?
              AND (COALESCE(co.tratamiento, '') <> ''
                   OR EXISTS (SELECT 1 FROM vacuna_aplicada va WHERE va.consulta_id = co.id))
            ORDER BY co.fecha_hora DESC""", (f["desde"], f["hasta_incl"]))

    def resumir(self, filas, f):
        dosis = self.bd.consultar("""
            SELECT tv.nombre || ' (' || tv.especie || ')' AS vacuna, COUNT(*) AS dosis
            FROM vacuna_aplicada va JOIN tipo_vacuna tv ON tv.id = va.tipo_vacuna_id
            WHERE va.fecha BETWEEN ? AND ? GROUP BY vacuna ORDER BY dosis DESC""", (f["desde"], f["hasta_incl"]))
        return [f"Atenciones con tratamiento o vacunación: {len(filas)}",
                "Dosis aplicadas: " + (", ".join(f"{d['vacuna']}: {d['dosis']}" for d in dosis) or "ninguna")]


class ReporteVacunasPendientes(Reporte):
    titulo = "Vacunas obligatorias pendientes"
    descripcion = ("Mascotas activas con vacunas obligatorias nunca aplicadas o con el refuerzo vencido "
                   "a la fecha de referencia, con días de atraso.")
    columnas = [("mascota", "Paciente"), ("especie", "Especie"), ("edad", "Edad (meses)"),
                ("responsable", "Responsable"), ("contacto", "Contacto"), ("vacuna", "Vacuna"),
                ("estado", "Situación"), ("ultima", "Última dosis"), ("desde", "Correspondía desde"),
                ("dias_atraso", "Días de atraso")]
    grafico = ("vacuna", "cantidad")
    usa_rango_fechas = False

    def obtener_datos(self, f):
        referencia = hoy()
        vacunas = VacunaService(self.bd)
        clientes = {c.id: c for c in r.RepoCliente(self.bd).listar()}
        filas = []
        for mascota in r.RepoMascota(self.bd).listar("activo = 1", orden="nombre"):
            for p in vacunas.pendientes(mascota, referencia):
                cliente = clientes[mascota.cliente_id]
                filas.append({
                    "mascota": mascota.nombre, "especie": mascota.especie,
                    "edad": mascota.edad_meses(referencia), "responsable": cliente.nombre_completo,
                    "contacto": cliente.telefono or cliente.email, "vacuna": p["tipo"].nombre,
                    "estado": p["estado"], "ultima": p["ultima"].isoformat() if p["ultima"] else "—",
                    "desde": p["proxima"].isoformat(), "dias_atraso": (referencia - p["proxima"]).days,
                })
        return filas

    def procesar(self, filas, f):
        return sorted(filas, key=lambda x: -x["dias_atraso"])

    def resumir(self, filas, f):
        mascotas = len({(x["mascota"], x["responsable"]) for x in filas})
        por_vacuna = defaultdict(int)
        for x in filas:
            por_vacuna[x["vacuna"]] += 1
        return [f"Mascotas con esquema incompleto: {mascotas} — dosis pendientes: {len(filas)}",
                "Por vacuna: " + (", ".join(f"{v}: {n}" for v, n in por_vacuna.items()) or "-")]

    def datos_grafico(self, filas):
        por_vacuna = defaultdict(int)
        for x in filas:
            por_vacuna[x["vacuna"]] += 1
        return [{"vacuna": v, "cantidad": n} for v, n in por_vacuna.items()]


class ReporteFacturacion(Reporte):
    titulo = "Facturación por clínica y servicio"
    descripcion = "Importe facturado por clínica, desglosado en consultas, vacunas y servicios de laboratorio."
    columnas = [("clinica", "Clínica"), ("comprobantes", "Comprobantes"), ("consulta", "Consultas $"),
                ("vacuna", "Vacunas $"), ("laboratorio", "Laboratorio $"), ("total", "Total $"),
                ("pct", "% del total"), ("ticket_promedio", "Ticket promedio $")]
    grafico = ("clinica", "total")

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT cl.nombre AS clinica, COUNT(DISTINCT cp.id) AS comprobantes,
                   SUM(CASE WHEN it.tipo_servicio = 'CONSULTA' THEN it.subtotal ELSE 0 END) AS consulta,
                   SUM(CASE WHEN it.tipo_servicio = 'VACUNA' THEN it.subtotal ELSE 0 END) AS vacuna,
                   SUM(CASE WHEN it.tipo_servicio = 'LABORATORIO' THEN it.subtotal ELSE 0 END) AS laboratorio,
                   SUM(it.subtotal) AS total
            FROM comprobante cp
            JOIN clinica cl ON cl.id = cp.clinica_id
            JOIN item_comprobante it ON it.comprobante_id = cp.id
            WHERE cp.fecha_hora BETWEEN ? AND ?
            GROUP BY cl.nombre ORDER BY total DESC""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        total_general = sum(x["total"] for x in filas)
        for x in filas:
            x["pct"] = porcentaje(x["total"], total_general)
            x["ticket_promedio"] = round(x["total"] / x["comprobantes"], 2)
        return filas

    def resumir(self, filas, f):
        total = sum(x["total"] for x in filas)
        lab = sum(x["laboratorio"] for x in filas)
        return [f"Total facturado: {moneda(total)} en {sum(x['comprobantes'] for x in filas)} comprobantes",
                f"Participación de servicios de laboratorio: {numero(porcentaje(lab, total), 1)} %"]


class ReporteTiemposMuestras(Reporte):
    titulo = "Tiempos de tránsito y procesamiento de muestras"
    descripcion = ("Promedio de horas en tránsito (despacho → recepción), en procesamiento "
                   "(recepción → resultado) y total, por clínica y tipo de análisis.")
    columnas = [("clinica", "Clínica"), ("analisis", "Análisis"), ("muestras", "Muestras"),
                ("h_espera", "Espera en clínica (h)"), ("h_transito", "Tránsito (h)"),
                ("h_proceso", "Procesamiento (h)"), ("h_total", "Total extracción→resultado (h)")]
    grafico = ("etiqueta", "h_transito")

    def obtener_datos(self, f):
        # Se pivotea la bitácora de estados: un instante por cada hito del ciclo de vida
        return self.bd.consultar("""
            WITH hitos AS (
                SELECT h.muestra_id,
                       MAX(CASE WHEN h.estado_nuevo = 'EXTRAIDA'    THEN h.fecha_hora END) AS extraida,
                       MAX(CASE WHEN h.estado_nuevo = 'EN_TRANSITO' THEN h.fecha_hora END) AS despachada,
                       MAX(CASE WHEN h.estado_nuevo = 'RECIBIDA'    THEN h.fecha_hora END) AS recibida,
                       MAX(CASE WHEN h.estado_nuevo = 'ANALIZADA'   THEN h.fecha_hora END) AS analizada
                FROM historial_estado_muestra h GROUP BY h.muestra_id
            )
            SELECT cl.nombre AS clinica, ta.nombre AS analisis, COUNT(*) AS muestras,
                   ROUND(AVG((julianday(hi.despachada) - julianday(hi.extraida)) * 24), 1) AS h_espera,
                   ROUND(AVG((julianday(hi.recibida) - julianday(hi.despachada)) * 24), 1) AS h_transito,
                   ROUND(AVG((julianday(hi.analizada) - julianday(hi.recibida)) * 24), 1) AS h_proceso,
                   ROUND(AVG((julianday(hi.analizada) - julianday(hi.extraida)) * 24), 1) AS h_total
            FROM hitos hi
            JOIN muestra mu ON mu.id = hi.muestra_id
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE hi.analizada IS NOT NULL AND hi.analizada BETWEEN ? AND ?
            GROUP BY cl.nombre, ta.nombre ORDER BY cl.nombre, h_total DESC""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        for x in filas:
            x["etiqueta"] = f"{x['clinica'].replace('Clínica ', '')} · {x['analisis']}"
        return filas

    def resumir(self, filas, f):
        n = sum(x["muestras"] for x in filas)
        if not n:
            return ["No hay muestras analizadas en el período."]

        def ponderado(clave):
            return round(sum(x[clave] * x["muestras"] for x in filas) / n, 1)

        lenta = max(filas, key=lambda x: x["h_transito"])
        return [f"Muestras analizadas: {n} — tránsito promedio {numero(ponderado('h_transito'), 1)} h, "
                f"procesamiento promedio {numero(ponderado('h_proceso'), 1)} h, total {numero(ponderado('h_total'), 1)} h",
                f"Ruta con mayor tránsito: {lenta['clinica']} ({numero(lenta['h_transito'], 1)} h promedio)"]


REPORTES = [ReporteAtencionesDerivaciones, ReporteMuestrasRechazadas, ReporteTratamientos,
            ReporteVacunasPendientes, ReporteFacturacion, ReporteTiemposMuestras]
