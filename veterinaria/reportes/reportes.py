"""Reportes concretos."""
from collections import defaultdict
from datetime import timedelta

from veterinaria.config import ESPECIES, TIPOS_CONSULTA
from veterinaria.persistencia import repositorios as r
from veterinaria.reportes.base import Grafico, Reporte, formato_valor, porcentaje
from veterinaria.servicios.vacunas import VacunaService
from veterinaria.utils.fechas import hoy, parse_fecha
from veterinaria.utils.formato import moneda, numero


def _corto(clinica):
    return clinica.replace("Clínica ", "")


class ReporteAtencionesDerivaciones(Reporte):
    titulo = "Atenciones clínicas y derivaciones"
    descripcion = ("Cantidad de atenciones por clínica y tipo, cuántas derivaron análisis al laboratorio "
                   "y el porcentaje de derivación.")
    columnas = [("clinica", "Clínica"), ("tipo", "Tipo de atención"), ("atenciones", "Atenciones"),
                ("con_derivacion", "Con derivación"), ("pct_derivacion", "% derivación"),
                ("muestras", "Muestras derivadas"), ("urgentes", "Órdenes urgentes")]
    # La pregunta es cuánto deriva cada clínica: lo derivado en color, el resto en gris de contexto
    grafico = Grafico("clinica", (("con_derivacion", "Derivaron al laboratorio"), ("sin_derivacion", "Sin derivación")),
                      "Atenciones por clínica y cuántas derivaron", paleta="enfasis", punta="punta")

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
        return filas

    def datos_grafico(self, filas, f):
        # Por clínica, cuántas atenciones derivaron al laboratorio y cuántas no
        por_clinica = {}
        for x in filas:
            g = por_clinica.setdefault(x["clinica"], {"clinica": _corto(x["clinica"]),
                                                      "con_derivacion": 0, "sin_derivacion": 0})
            g["con_derivacion"] += x["con_derivacion"]
            g["sin_derivacion"] += x["atenciones"] - x["con_derivacion"]
        for g in por_clinica.values():
            total = g["con_derivacion"] + g["sin_derivacion"]
            g["punta"] = f"{total} · {numero(porcentaje(g['con_derivacion'], total), 0)} % derivó"
        return list(por_clinica.values())

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

    def concluir(self, filas, f):
        clinicas = defaultdict(lambda: {"atenciones": 0, "derivadas": 0, "urgentes": 0})
        for x in filas:
            c = clinicas[x["clinica"]]
            c["atenciones"] += x["atenciones"]
            c["derivadas"] += x["con_derivacion"]
            c["urgentes"] += x["urgentes"]
        total = sum(c["atenciones"] for c in clinicas.values())
        lineas = []
        mayor = max(clinicas, key=lambda k: clinicas[k]["atenciones"])
        lineas.append(f"{mayor} concentra el {numero(porcentaje(clinicas[mayor]['atenciones'], total), 0)} % de las "
                      "atenciones de la red: si hace falta ampliar la capacidad, es la primera candidata para "
                      "sumar turnos o profesionales.")
        tasas = {k: porcentaje(c["derivadas"], c["atenciones"]) for k, c in clinicas.items()}
        alta, baja = max(tasas, key=tasas.get), min(tasas, key=tasas.get)
        if tasas[alta] - tasas[baja] >= 10:
            lineas.append(f"{alta} deriva al laboratorio el {numero(tasas[alta], 0)} % de sus atenciones y {baja} "
                          f"el {numero(tasas[baja], 0)} %: conviene revisar que los criterios para pedir análisis "
                          "sean los mismos en toda la red.")
        elif len(tasas) > 1:
            lineas.append("Las clínicas derivan al laboratorio en proporciones parecidas: los criterios para "
                          "pedir análisis son homogéneos.")
        urgentes = sum(c["urgentes"] for c in clinicas.values())
        if urgentes:
            foco = max(clinicas, key=lambda k: clinicas[k]["urgentes"])
            lineas.append(f"{foco} generó {clinicas[foco]['urgentes']} de las {urgentes} órdenes urgentes: priorizar "
                          "el retiro de sus muestras acorta el diagnóstico de los casos más graves.")
        return lineas


class ReporteMuestrasRechazadas(Reporte):
    titulo = "Muestras rechazadas por fallas en el transporte"
    descripcion = ("Detalle de muestras rechazadas al llegar al laboratorio, causa (precinto roto, cadena de frío, "
                   "viabilidad) y tasa de rechazo por transportista.")
    columnas = [("codigo", "Muestra"), ("fecha_rechazo", "Fecha rechazo"), ("clinica", "Clínica"),
                ("analisis", "Análisis"), ("remito", "Remito"), ("transportista", "Transportista"),
                ("causa", "Causa"), ("motivo_rechazo", "Detalle")]
    CAUSAS = ("Precinto roto", "Cadena de frío", "Tiempo de viabilidad", "Otra")
    # Tasa y no cantidad: un transportista que lleva más muestras no debe parecer peor por eso
    grafico = Grafico("transportista", tuple((c, c) for c in CAUSAS),
                      "Tasa de rechazo por transportista (% de las muestras que llevó), según causa",
                      unidad="%", punta="punta", omitir_vacias=False)

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT mu.codigo, h.fecha_hora AS fecha_rechazo, cl.nombre AS clinica, ta.nombre AS analisis,
                   re.numero AS remito, e.transportista, mu.motivo_rechazo
            FROM muestra mu
            JOIN historial_estado_muestra h ON h.muestra_id = mu.id AND h.estado_nuevo = 'RECHAZADA'
                 AND h.estado_anterior = 'EN_TRANSITO'
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

    def _por_transportista(self, f):
        return self.bd.consultar("""
            SELECT e.transportista, COUNT(mu.id) AS enviadas,
                   SUM(EXISTS (SELECT 1 FROM historial_estado_muestra h
                               WHERE h.muestra_id = mu.id AND h.estado_nuevo = 'RECHAZADA'
                                 AND h.estado_anterior = 'EN_TRANSITO')) AS rechazadas
            FROM envio e JOIN muestra mu ON mu.remito_id = e.remito_id
            WHERE e.fecha_llegada BETWEEN ? AND ?
            GROUP BY e.transportista ORDER BY rechazadas DESC""", (f["desde"], f["hasta_incl"]))

    def resumir(self, filas, f):
        totales = self._por_transportista(f)
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

    def datos_grafico(self, filas, f):
        # Una barra por transportista con su tasa de rechazo, dividida según la causa
        causas = defaultdict(lambda: defaultdict(int))
        for x in filas:
            causas[x["transportista"]][x["causa"]] += 1
        datos = []
        for t in self._por_transportista(f):
            fila = {"transportista": t["transportista"],
                    **{c: porcentaje(causas[t["transportista"]][c], t["enviadas"]) for c in self.CAUSAS}}
            rechazadas = sum(causas[t["transportista"]].values())
            fila["punta"] = (f"{formato_valor(porcentaje(rechazadas, t['enviadas']), '%')} "
                             f"({rechazadas} de {t['enviadas']})")
            datos.append(fila)
        return datos

    MINIMO_REPRESENTATIVO = 10   # con menos muestras llevadas, la tasa de un transportista no es comparable

    def concluir(self, filas, f):
        totales = [t for t in self._por_transportista(f) if t["enviadas"]]
        enviadas = sum(t["enviadas"] for t in totales)
        lineas = [f"Se rechazó el {numero(porcentaje(len(filas), enviadas), 1)} % de las muestras recibidas: cada "
                  "rechazo obliga a repetir la extracción, demora el diagnóstico y es un análisis que no se cobra."]
        comparables = [t for t in totales if t["enviadas"] >= self.MINIMO_REPRESENTATIVO]
        if len(comparables) >= 2:
            tasa = {t["transportista"]: porcentaje(t["rechazadas"], t["enviadas"]) for t in comparables}
            peor, mejor = max(tasa, key=tasa.get), min(tasa, key=tasa.get)
            if tasa[peor] > tasa[mejor]:
                lineas.append(f"{peor} pierde el {numero(tasa[peor], 1)} % de lo que lleva, contra el "
                              f"{numero(tasa[mejor], 1)} % de {mejor}: conviene revisar sus condiciones o derivar "
                              "más envíos al segundo.")
        pocos = [t["transportista"] for t in totales if t["enviadas"] < self.MINIMO_REPRESENTATIVO]
        if pocos:
            lineas.append(f"{', '.join(pocos)}: llevó menos de {self.MINIMO_REPRESENTATIVO} muestras, todavía no "
                          "alcanza para sacar conclusiones sobre su tasa.")
        por_causa = defaultdict(int)
        for x in filas:
            por_causa[x["causa"]] += 1
        principal = max(por_causa, key=por_causa.get)
        accion = {
            "Precinto roto": "revisar la manipulación durante el traslado y el cierre de las conservadoras",
            "Cadena de frío": "controlar conservadoras y refrigerantes y exigir el registro de temperatura en cada "
                              "punto de control",
            "Tiempo de viabilidad": "despachar más seguido desde las clínicas para que las muestras lleguen a tiempo",
        }.get(principal, "analizar los casos uno por uno")
        lineas.append(f"La causa principal es «{principal.lower()}» ({por_causa[principal]} de {len(filas)}): "
                      f"{accion}.")
        return lineas


class ReporteTratamientos(Reporte):
    titulo = "Tratamientos aplicados"
    descripcion = "Atenciones con diagnóstico, tratamiento indicado y vacunas aplicadas en el período."
    columnas = [("fecha_hora", "Fecha"), ("clinica", "Clínica"), ("mascota", "Paciente"), ("especie", "Especie"),
                ("tipo", "Tipo"), ("diagnostico", "Diagnóstico"), ("tratamiento", "Tratamiento"),
                ("vacunas", "Vacunas aplicadas")]
    grafico = Grafico("semana", (("con_tratamiento", "Con tratamiento"), ("solo_vacunas", "Sólo vacunación")),
                      "Atenciones por semana", tipo="columnas")

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

    def datos_grafico(self, filas, f):
        # Evolución semanal: se incluyen las semanas sin atenciones para no ocultar huecos
        def lunes(fecha):
            return fecha - timedelta(days=fecha.weekday())
        semanas = {}
        semana, ultima = lunes(parse_fecha(f["desde"])), lunes(parse_fecha(f["hasta"]))
        while semana <= ultima:
            semanas[semana] = {"semana": semana.strftime("%d/%m"), "con_tratamiento": 0, "solo_vacunas": 0}
            semana += timedelta(days=7)
        for x in filas:
            g = semanas.get(lunes(parse_fecha(x["fecha_hora"][:10])))
            if g:
                g["con_tratamiento" if (x["tratamiento"] or "").strip() else "solo_vacunas"] += 1
        return list(semanas.values())

    def concluir(self, filas, f):
        semanas = [s for s in self.datos_grafico(filas, f) if s["con_tratamiento"] + s["solo_vacunas"]]
        lineas = []
        if len(semanas) >= 8:
            reciente = sum(s["con_tratamiento"] + s["solo_vacunas"] for s in semanas[-4:])
            anterior = sum(s["con_tratamiento"] + s["solo_vacunas"] for s in semanas[-8:-4])
            cambio = porcentaje(reciente - anterior, anterior)
            if cambio <= -10:
                lineas.append(f"En las últimas 4 semanas con actividad hubo {reciente} atenciones, un "
                              f"{numero(-cambio, 0)} % menos que en las 4 anteriores: recordatorios de controles o "
                              "una campaña pueden recuperar la demanda.")
            elif cambio >= 10:
                lineas.append(f"En las últimas 4 semanas con actividad hubo {reciente} atenciones, un "
                              f"{numero(cambio, 0)} % más que en las 4 anteriores: prever más turnos, medicamentos "
                              "e insumos.")
            else:
                lineas.append(f"La actividad se mantiene estable ({reciente} atenciones en las últimas 4 semanas "
                              f"con actividad, contra {anterior} en las 4 anteriores).")
        con_vacuna = sum(1 for x in filas if x["vacunas"])
        pct_vacuna = porcentaje(con_vacuna, len(filas))
        lineas.append(f"{'Sólo el' if pct_vacuna < 30 else 'El'} {numero(pct_vacuna, 0)} % de estas atenciones "
                      "incluyó una vacuna: aprovechar cada consulta para revisar y completar el esquema suma ingresos y previene "
                      "enfermedades (ver el informe de vacunas pendientes).")
        return lineas


class ReporteVacunasPendientes(Reporte):
    titulo = "Vacunas obligatorias pendientes"
    descripcion = ("Mascotas activas con vacunas obligatorias nunca aplicadas o con el refuerzo vencido "
                   "a la fecha de referencia, con días de atraso.")
    columnas = [("mascota", "Paciente"), ("especie", "Especie"), ("edad", "Edad (meses)"),
                ("responsable", "Responsable"), ("contacto", "Contacto"), ("vacuna", "Vacuna"),
                ("estado", "Situación"), ("ultima", "Última dosis"), ("desde", "Correspondía desde"),
                ("dias_atraso", "Días de atraso")]
    # La urgencia la da el atraso: tramos ordenados, de azul claro (reciente) a oscuro (más atrasado)
    # (los refuerzos son anuales: el atraso se mide en meses y años, no en días)
    TRAMOS = (("hasta_6m", "Hasta 6 meses"), ("de_6m_a_1a", "6 meses a 1 año"), ("mas_de_1a", "Más de 1 año"))
    grafico = Grafico("vacuna", TRAMOS, "Dosis pendientes por vacuna, según el atraso", paleta="secuencial")
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

    def datos_grafico(self, filas, f):
        por_vacuna = {}
        for x in filas:
            g = por_vacuna.setdefault(x["vacuna"], {"vacuna": x["vacuna"], **{c: 0 for c, _ in self.TRAMOS}})
            dias = x["dias_atraso"]
            g["hasta_6m" if dias <= 182 else ("de_6m_a_1a" if dias <= 365 else "mas_de_1a")] += 1
        return list(por_vacuna.values())

    def concluir(self, filas, f):
        mascotas = {(x["mascota"], x["responsable"]) for x in filas}
        mas_de_un_anio = sum(1 for x in filas if x["dias_atraso"] > 365)
        lineas = [f"{len(mascotas)} mascotas tienen vacunas obligatorias pendientes ({len(filas)} dosis); "
                  f"{mas_de_un_anio} de esas dosis llevan más de un año de atraso."]
        por_vacuna = defaultdict(int)
        for x in filas:
            por_vacuna[x["vacuna"]] += 1
        vacuna = max(por_vacuna, key=por_vacuna.get)
        lineas.append(f"La que más falta es {vacuna} ({por_vacuna[vacuna]} dosis): conviene un recordatorio o una "
                      "jornada de vacunación enfocada en ella.")
        por_responsable = defaultdict(int)
        for x in filas:
            por_responsable[(x["responsable"], x["contacto"])] += 1
        primeros = sorted(por_responsable, key=lambda k: -por_responsable[k])[:3]
        lineas.append("Contactar primero a: " + "; ".join(f"{r} ({c})" for r, c in primeros)
                      + ". Completar estas dosis es un ingreso seguro y evita riesgos sanitarios.")
        return lineas


class ReporteFacturacion(Reporte):
    titulo = "Facturación por clínica y servicio"
    descripcion = "Importe facturado por clínica, desglosado en consultas, vacunas y servicios de laboratorio."
    columnas = [("clinica", "Clínica"), ("comprobantes", "Comprobantes"), ("consulta", "Consultas $"),
                ("vacuna", "Vacunas $"), ("laboratorio", "Laboratorio $"), ("total", "Total $"),
                ("pct", "% del total"), ("ticket_promedio", "Ticket promedio $")]
    grafico = Grafico("etiqueta", (("consulta", "Consultas"), ("vacuna", "Vacunas"), ("laboratorio", "Laboratorio")),
                      "Facturación por clínica y servicio", unidad="$", punta="punta")

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
            x["etiqueta"] = _corto(x["clinica"])
            x["punta"] = f"{formato_valor(x['total'], '$')} · {numero(x['pct'], 0)} %"
        return filas

    def resumir(self, filas, f):
        total = sum(x["total"] for x in filas)
        lab = sum(x["laboratorio"] for x in filas)
        return [f"Total facturado: {moneda(total)} en {sum(x['comprobantes'] for x in filas)} comprobantes",
                f"Participación de servicios de laboratorio: {numero(porcentaje(lab, total), 1)} %"]

    def concluir(self, filas, f):
        total = sum(x["total"] for x in filas)
        lider = max(filas, key=lambda x: x["total"])
        lineas = [f"{lider['clinica']} aporta el {numero(lider['pct'], 0)} % de la facturación "
                  f"({formato_valor(lider['total'], '$')})."]
        if len(filas) > 1:
            baja = min(filas, key=lambda x: x["ticket_promedio"])
            alta = max(filas, key=lambda x: x["ticket_promedio"])
            if baja is not alta:
                lineas.append(f"El ticket promedio más bajo es el de {baja['clinica']} "
                              f"({formato_valor(baja['ticket_promedio'], '$')} contra "
                              f"{formato_valor(alta['ticket_promedio'], '$')} de {alta['clinica']}): revisar que se "
                              "cobren todas las vacunas y análisis que se hacen.")
        lab = porcentaje(sum(x["laboratorio"] for x in filas), total)
        vacunas = porcentaje(sum(x["vacuna"] for x in filas), total)
        lineas.append(f"El laboratorio aporta el {numero(lab, 0)} % de los ingresos: cuidar el envío de muestras "
                      "(cada rechazo es un análisis que no se cobra) protege una parte importante de la facturación.")
        if vacunas < 10:
            lineas.append(f"Las vacunas son sólo el {numero(vacunas, 1)} % de lo facturado: hay margen para crecer "
                          "con campañas de vacunación.")
        return lineas


class ReporteTiemposMuestras(Reporte):
    titulo = "Tiempos de tránsito y procesamiento de muestras"
    descripcion = ("Promedio de horas en tránsito (despacho → llegada, incluye las rechazadas al llegar), "
                   "en procesamiento (recepción → resultado) y total, por clínica y tipo de análisis.")
    columnas = [("clinica", "Clínica"), ("analisis", "Análisis"), ("muestras", "Llegadas"),
                ("analizadas", "Analizadas"),
                ("h_espera", "Espera en clínica (h)"), ("h_transito", "Tránsito (h)"),
                ("h_proceso", "Procesamiento (h)"), ("h_total", "Total extracción→resultado (h)")]
    grafico = Grafico("etiqueta", (("h_espera", "Espera en clínica"), ("h_transito", "Tránsito"),
                                   ("h_proceso", "Procesamiento")),
                      "Horas promedio por etapa, de la extracción al resultado", unidad="h")

    def obtener_datos(self, f):
        # Se pivotea la bitácora de estados: un instante por cada hito del ciclo de vida
        return self.bd.consultar("""
            WITH hitos AS (
                SELECT h.muestra_id,
                       MAX(CASE WHEN h.estado_nuevo = 'EXTRAIDA'    THEN h.fecha_hora END) AS extraida,
                       MAX(CASE WHEN h.estado_nuevo = 'EN_TRANSITO' THEN h.fecha_hora END) AS despachada,
                       MAX(CASE WHEN h.estado_nuevo = 'RECIBIDA'    THEN h.fecha_hora END) AS recibida,
                       MAX(CASE WHEN h.estado_nuevo = 'RECIBIDA' OR (h.estado_nuevo = 'RECHAZADA'
                                     AND h.estado_anterior = 'EN_TRANSITO')
                                THEN h.fecha_hora END) AS llegada,
                       MAX(CASE WHEN h.estado_nuevo = 'ANALIZADA'   THEN h.fecha_hora END) AS analizada
                FROM historial_estado_muestra h GROUP BY h.muestra_id
            )
            SELECT cl.nombre AS clinica, ta.nombre AS analisis, COUNT(*) AS muestras,
                   COUNT(hi.analizada) AS analizadas,
                   ROUND(AVG((julianday(hi.despachada) - julianday(hi.extraida)) * 24), 1) AS h_espera,
                   ROUND(AVG((julianday(hi.llegada) - julianday(hi.despachada)) * 24), 1) AS h_transito,
                   ROUND(AVG((julianday(hi.analizada) - julianday(hi.recibida)) * 24), 1) AS h_proceso,
                   ROUND(AVG((julianday(hi.analizada) - julianday(hi.extraida)) * 24), 1) AS h_total
            FROM hitos hi
            JOIN muestra mu ON mu.id = hi.muestra_id
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE hi.llegada BETWEEN ? AND ?
            GROUP BY cl.nombre, ta.nombre ORDER BY cl.nombre, h_total DESC""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        for x in filas:
            x["etiqueta"] = f"{_corto(x['clinica'])} · {x['analisis']}"
        return filas

    def resumir(self, filas, f):
        n = sum(x["muestras"] for x in filas)
        if not n:
            return ["No hay muestras llegadas al laboratorio en el período."]
        analizadas = sum(x["analizadas"] for x in filas)

        def ponderado(clave, peso, total):
            # Un grupo sin analizadas no tiene horas de procesamiento (queda en None)
            if not total:
                return 0
            return round(sum(x[clave] * x[peso] for x in filas if x[clave] is not None) / total, 1)

        lenta = max(filas, key=lambda x: x["h_transito"])
        return [f"Muestras llegadas: {n} — tránsito promedio {numero(ponderado('h_transito', 'muestras', n), 1)} h",
                f"Muestras analizadas: {analizadas} — "
                f"procesamiento promedio {numero(ponderado('h_proceso', 'analizadas', analizadas), 1)} h, "
                f"total {numero(ponderado('h_total', 'analizadas', analizadas), 1)} h",
                f"Ruta con mayor tránsito: {lenta['clinica']} ({numero(lenta['h_transito'], 1)} h promedio)"]

    def concluir(self, filas, f):
        n = sum(x["muestras"] for x in filas)
        analizadas = sum(x["analizadas"] for x in filas)

        def ponderado(clave, peso, total):
            if not total:
                return 0
            return round(sum(x[clave] * x[peso] for x in filas if x[clave] is not None) / total, 1)

        etapas = {"la espera en la clínica antes del despacho": ponderado("h_espera", "analizadas", analizadas),
                  "el tránsito hacia el laboratorio": ponderado("h_transito", "muestras", n),
                  "el procesamiento en el laboratorio": ponderado("h_proceso", "analizadas", analizadas)}
        total = sum(etapas.values())
        if not total:
            return []
        lenta = max(etapas, key=etapas.get)
        accion = {
            "la espera en la clínica antes del despacho": "despachar más seguido desde las clínicas",
            "el tránsito hacia el laboratorio": "revisar rutas, horarios de retiro o transportistas",
            "el procesamiento en el laboratorio": "reforzar personal o turnos en el laboratorio",
        }[lenta]
        lineas = [f"De la extracción al resultado pasan en promedio "
                  f"{numero(ponderado('h_total', 'analizadas', analizadas), 1)} h; la etapa más larga es "
                  f"{lenta} ({numero(etapas[lenta], 1)} h, {numero(porcentaje(etapas[lenta], total), 0)} %): "
                  f"{accion} es lo que más acortaría la entrega de resultados."]
        por_clinica = defaultdict(lambda: [0.0, 0])
        for x in filas:
            if x["h_transito"] is not None:
                por_clinica[x["clinica"]][0] += x["h_transito"] * x["muestras"]
                por_clinica[x["clinica"]][1] += x["muestras"]
        transito = {c: suma / k for c, (suma, k) in por_clinica.items() if k}
        promedio = etapas["el tránsito hacia el laboratorio"]
        if transito:
            lejana = max(transito, key=transito.get)
            if transito[lejana] > promedio * 1.2:
                lineas.append(f"Las muestras de {lejana} tardan {numero(transito[lejana], 1)} h en llegar, contra "
                              f"{numero(promedio, 1)} h de promedio: es la primera ruta a mejorar.")
        con_total = [x for x in filas if x["h_total"] is not None]
        if con_total:
            demorado = max(con_total, key=lambda x: x["h_total"])
            lineas.append(f"El análisis que más tarda es {demorado['analisis']} en {demorado['clinica']} "
                          f"({numero(demorado['h_total'], 1)} h): avisar al dueño de la mascota del plazo esperado "
                          "mejora su experiencia.")
        return lineas


NOMBRE_TIPO = {"CONSULTA": "Consulta", "CONTROL": "Control de seguimiento", "URGENCIA": "Urgencia"}


def _periodos(f):
    """Períodos del gráfico de evolución: semanas si el rango es corto, meses si supera los cuatro meses."""
    desde, hasta = parse_fecha(f["desde"]), parse_fecha(f["hasta"])
    if (hasta - desde).days > 120:
        periodos, actual = [], desde.replace(day=1)
        while actual <= hasta:
            periodos.append((actual.strftime("%Y-%m"), actual.strftime("%m/%Y")))
            actual = (actual.replace(day=28) + timedelta(days=4)).replace(day=1)
        return periodos, lambda fecha: fecha[:7]
    periodos, actual = [], desde - timedelta(days=desde.weekday())
    while actual <= hasta:
        periodos.append((actual.isoformat(), actual.strftime("%d/%m")))
        actual += timedelta(days=7)

    def semana(fecha):
        dia = parse_fecha(fecha[:10])
        return (dia - timedelta(days=dia.weekday())).isoformat()
    return periodos, semana


class ReporteIngresosPorTipo(Reporte):
    titulo = "Ingresos por tipo de atención"
    descripcion = ("Cuántas consultas, controles de seguimiento y urgencias se facturaron, cuánto ingresó por cada "
                   "tipo (incluye las vacunas y los análisis de esa atención) y cómo evolucionó en el período.")
    columnas = [("nombre", "Tipo de atención"), ("atenciones", "Atenciones facturadas"),
                ("honorarios", "Honorarios $"), ("extras", "Vacunas y análisis $"), ("ingresos", "Ingresos $"),
                ("pct", "% de los ingresos"), ("ticket", "Ticket promedio $")]
    # La curva muestra la evolución de cada tipo; las barras, cuál es el más frecuente
    graficos = (
        Grafico("periodo", (("CONSULTA", "Consultas"), ("CONTROL", "Controles de seguimiento"),
                            ("URGENCIA", "Urgencias")),
                "Ingresos por tipo de atención a lo largo del período", tipo="lineas", unidad="$"),
        Grafico("nombre", (("atenciones", "Atenciones"),), "Atenciones facturadas por tipo"),
    )

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT co.tipo, COUNT(DISTINCT cp.id) AS atenciones,
                   SUM(CASE WHEN it.tipo_servicio = 'CONSULTA' THEN it.subtotal ELSE 0 END) AS honorarios,
                   SUM(CASE WHEN it.tipo_servicio <> 'CONSULTA' THEN it.subtotal ELSE 0 END) AS extras,
                   SUM(it.subtotal) AS ingresos
            FROM comprobante cp
            JOIN consulta co ON co.id = cp.consulta_id
            JOIN item_comprobante it ON it.comprobante_id = cp.id
            WHERE cp.fecha_hora BETWEEN ? AND ?
            GROUP BY co.tipo""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        total = sum(x["ingresos"] for x in filas)
        for x in filas:
            x["nombre"] = NOMBRE_TIPO[x["tipo"]]
            x["pct"] = porcentaje(x["ingresos"], total)
            x["ticket"] = round(x["ingresos"] / x["atenciones"], 2)
        return sorted(filas, key=lambda x: TIPOS_CONSULTA.index(x["tipo"]))

    def resumir(self, filas, f):
        total = sum(x["ingresos"] for x in filas)
        frecuente = max(filas, key=lambda x: x["atenciones"]) if filas else None
        return [f"Ingresos: {moneda(total)} en {sum(x['atenciones'] for x in filas)} atenciones facturadas",
                "Tipo más frecuente: " + (f"{frecuente['nombre']} ({frecuente['atenciones']} atenciones)"
                                          if frecuente else "-")]

    def datos_grafico(self, filas, f):
        periodos, clave_de = _periodos(f)
        evolucion = {clave: {"periodo": etiqueta, **{t: 0 for t in TIPOS_CONSULTA}} for clave, etiqueta in periodos}
        for x in self.bd.consultar("""
                SELECT cp.fecha_hora, co.tipo, cp.total FROM comprobante cp
                JOIN consulta co ON co.id = cp.consulta_id
                WHERE cp.fecha_hora BETWEEN ? AND ?""", (f["desde"], f["hasta_incl"])):
            periodo = evolucion.get(clave_de(x["fecha_hora"]))
            if periodo:
                periodo[x["tipo"]] += x["total"]
        return [list(evolucion.values()), filas]

    def concluir(self, filas, f):
        por_tipo = {x["tipo"]: x for x in filas}
        total = sum(x["atenciones"] for x in filas)
        frecuente = max(filas, key=lambda x: x["atenciones"])
        rentable = max(filas, key=lambda x: x["ingresos"])
        lineas = [f"El tipo de atención que más hubo fue {frecuente['nombre'].lower()} "
                  f"({frecuente['atenciones']} de {total}, {numero(porcentaje(frecuente['atenciones'], total), 0)} %)"
                  + (", y también es el que más ingresos deja." if rentable is frecuente else
                     f"; pero el que más ingresos deja es {rentable['nombre'].lower()}.")]
        if "URGENCIA" in por_tipo and "CONSULTA" in por_tipo:
            u, c = por_tipo["URGENCIA"], por_tipo["CONSULTA"]
            lineas.append(f"Cada urgencia deja en promedio {formato_valor(u['ticket'], '$')}, "
                          f"{numero(u['ticket'] / c['ticket'], 1)} veces una consulta: tener guardia disponible "
                          "es rentable además de necesario.")
        controles = por_tipo.get("CONTROL", {"atenciones": 0})["atenciones"]
        if porcentaje(controles, total) < 15:
            cuantos = (f"Los controles de seguimiento son sólo el {numero(porcentaje(controles, total), 0)} % de "
                       "las atenciones" if controles else "No se facturaron controles de seguimiento")
            lineas.append(f"{cuantos}: dar el turno de control al terminar cada consulta fideliza al cliente y "
                          "suma ingresos.")
        return lineas


class ReportePacientes(Reporte):
    titulo = "Pacientes atendidos por especie y tipo de atención"
    descripcion = ("Qué animales se atienden más y cuántas consultas, controles de seguimiento y urgencias hubo "
                   "en el período.")
    columnas = [("especie", "Especie"), ("pacientes", "Pacientes distintos"), ("atenciones", "Atenciones"),
                ("pct", "% de las atenciones"), ("consultas", "Consultas"), ("controles", "Controles de seguimiento"),
                ("urgencias", "Urgencias"), ("pct_urgencias", "% urgencias")]
    graficos = (
        Grafico("especie", (("atenciones", "Atenciones"),), "Qué animal se atiende más", tipo="torta"),
        Grafico("tipo", (("cantidad", "Atenciones"),), "Consultas, controles y urgencias", tipo="torta"),
    )

    def obtener_datos(self, f):
        return self.bd.consultar("""
            SELECT m.especie, COUNT(DISTINCT m.id) AS pacientes, COUNT(*) AS atenciones,
                   SUM(co.tipo = 'CONSULTA') AS consultas, SUM(co.tipo = 'CONTROL') AS controles,
                   SUM(co.tipo = 'URGENCIA') AS urgencias
            FROM consulta co JOIN mascota m ON m.id = co.mascota_id
            WHERE co.fecha_hora BETWEEN ? AND ?
            GROUP BY m.especie""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        total = sum(x["atenciones"] for x in filas)
        for x in filas:
            x["pct"] = porcentaje(x["atenciones"], total)
            x["pct_urgencias"] = porcentaje(x["urgencias"], x["atenciones"])
        # orden fijo de especies: así cada una conserva su color en la torta
        orden = {e: i for i, e in enumerate(ESPECIES)}
        return sorted(filas, key=lambda x: (orden.get(x["especie"], len(orden)), x["especie"]))

    def _por_tipo(self, filas):
        return [{"tipo": "Consultas", "cantidad": sum(x["consultas"] for x in filas)},
                {"tipo": "Controles de seguimiento", "cantidad": sum(x["controles"] for x in filas)},
                {"tipo": "Urgencias", "cantidad": sum(x["urgencias"] for x in filas)}]

    def resumir(self, filas, f):
        tipos = self._por_tipo(filas)
        return [f"Atenciones: {sum(x['atenciones'] for x in filas)} a {sum(x['pacientes'] for x in filas)} pacientes",
                " · ".join(f"{t['tipo']}: {t['cantidad']}" for t in tipos)]

    def datos_grafico(self, filas, f):
        return [filas, self._por_tipo(filas)]

    def concluir(self, filas, f):
        total = sum(x["atenciones"] for x in filas)
        principal = max(filas, key=lambda x: x["atenciones"])
        lineas = [f"El animal que más se atiende es el {principal['especie'].lower()} "
                  f"({numero(principal['pct'], 0)} % de las atenciones): orientar el stock de medicamentos, vacunas "
                  "y la capacitación del equipo a esa especie."]
        tipos = {t["tipo"]: t["cantidad"] for t in self._por_tipo(filas)}
        urgencias = porcentaje(tipos["Urgencias"], total)
        mas_urgente = max(filas, key=lambda x: x["pct_urgencias"])
        lineas.append(f"Las urgencias son el {numero(urgencias, 0)} % de las atenciones; en {mas_urgente['especie'].lower()}s "
                      f"llegan al {numero(mas_urgente['pct_urgencias'], 0)} %: vale la pena reforzar los controles "
                      "preventivos en esa especie.")
        controles = porcentaje(tipos["Controles de seguimiento"], total)
        if controles < 15:
            cuantos = (f"Sólo el {numero(controles, 0)} % fueron controles de seguimiento" if controles
                       else "No hubo controles de seguimiento en el período")
            lineas.append(f"{cuantos}: recordar el control a los dueños después de cada tratamiento mejora la "
                          "recuperación y la fidelidad.")
        pacientes = sum(x["pacientes"] for x in filas)
        lineas.append(f"Cada paciente vino en promedio {numero(total / pacientes, 1)} veces en el período.")
        return lineas


class ReporteMuestrasIngresadas(Reporte):
    titulo = "Muestras ingresadas al laboratorio"
    descripcion = ("Muestras que llegaron al laboratorio por tipo de análisis: aceptadas, rechazadas, horas siendo "
                   "analizadas (del despacho a la llegada) y en el laboratorio hasta el resultado, y de qué clínica "
                   "vienen.")
    columnas = [("analisis", "Análisis"), ("ingresadas", "Ingresadas"), ("aceptadas", "Aceptadas"),
                ("rechazadas", "Rechazadas"), ("pct_rechazo", "% rechazo"),
                ("h_siendo", "Siendo analizada (h)"), ("h_laboratorio", "En laboratorio hasta el resultado (h)")]
    graficos = (
        Grafico("analisis", (("aceptadas", "Aceptadas"), ("rechazadas", "Rechazadas")),
                "Muestras ingresadas por tipo de análisis", punta="punta"),
        Grafico("clinica", (("ingresadas", "Muestras"),), "De qué clínica vienen", tipo="torta"),
    )
    HITOS = """
        WITH hitos AS (
            SELECT h.muestra_id,
                   MAX(CASE WHEN h.estado_nuevo = 'EN_TRANSITO' THEN h.fecha_hora END) AS despachada,
                   MAX(CASE WHEN h.estado_nuevo = 'RECIBIDA' THEN h.fecha_hora END) AS recibida,
                   MAX(CASE WHEN h.estado_nuevo = 'RECIBIDA' OR (h.estado_nuevo = 'RECHAZADA'
                                 AND h.estado_anterior = 'EN_TRANSITO') THEN h.fecha_hora END) AS llegada,
                   MAX(CASE WHEN h.estado_nuevo = 'RECHAZADA' THEN 1 ELSE 0 END) AS rechazada,
                   MAX(CASE WHEN h.estado_nuevo = 'ANALIZADA' THEN h.fecha_hora END) AS analizada
            FROM historial_estado_muestra h GROUP BY h.muestra_id
        )"""

    def obtener_datos(self, f):
        return self.bd.consultar(self.HITOS + """
            SELECT ta.nombre AS analisis, COUNT(*) AS ingresadas, SUM(hi.rechazada) AS rechazadas,
                   ROUND(AVG((julianday(hi.llegada) - julianday(hi.despachada)) * 24), 1) AS h_siendo,
                   ROUND(AVG((julianday(hi.analizada) - julianday(hi.recibida)) * 24), 1) AS h_laboratorio
            FROM hitos hi
            JOIN muestra mu ON mu.id = hi.muestra_id
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            WHERE hi.llegada BETWEEN ? AND ?
            GROUP BY ta.nombre ORDER BY ingresadas DESC""", (f["desde"], f["hasta_incl"]))

    def procesar(self, filas, f):
        for x in filas:
            x["aceptadas"] = x["ingresadas"] - x["rechazadas"]
            x["pct_rechazo"] = porcentaje(x["rechazadas"], x["ingresadas"])
            x["punta"] = f"{x['ingresadas']} · {numero(x['pct_rechazo'], 0)} % rechazo"
        return filas

    def _por_clinica(self, f):
        return self.bd.consultar(self.HITOS + """
            SELECT cl.nombre AS clinica, COUNT(*) AS ingresadas
            FROM hitos hi
            JOIN muestra mu ON mu.id = hi.muestra_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE hi.llegada BETWEEN ? AND ?
            GROUP BY cl.nombre ORDER BY cl.nombre""", (f["desde"], f["hasta_incl"]))

    def resumir(self, filas, f):
        ingresadas = sum(x["ingresadas"] for x in filas)
        rechazadas = sum(x["rechazadas"] for x in filas)
        lineas = [f"Muestras ingresadas: {ingresadas} — rechazadas: {rechazadas} "
                  f"({numero(porcentaje(rechazadas, ingresadas), 1)} %)"]
        lineas += [f"  {c['clinica']}: {c['ingresadas']} muestras" for c in self._por_clinica(f)]
        return lineas

    def datos_grafico(self, filas, f):
        return [filas, self._por_clinica(f)]

    def concluir(self, filas, f):
        ingresadas = sum(x["ingresadas"] for x in filas)
        principal = max(filas, key=lambda x: x["ingresadas"])
        lineas = [f"El análisis más pedido es {principal['analisis']} ({principal['ingresadas']} muestras, "
                  f"{numero(porcentaje(principal['ingresadas'], ingresadas), 0)} %): asegurar reactivos y personal "
                  "para ese análisis evita demoras."]
        comparables = [x for x in filas if x["ingresadas"] >= 10]
        if comparables:
            peor = max(comparables, key=lambda x: x["pct_rechazo"])
            if peor["pct_rechazo"] > 0:
                lineas.append(f"{peor['analisis']} es el que más se rechaza ({numero(peor['pct_rechazo'], 1)} %): "
                              "revisar cómo se toma, se conserva y se empaqueta ese tipo de muestra.")
        con_tiempo = [x for x in filas if x["h_siendo"] is not None]
        if con_tiempo:
            lento = max(con_tiempo, key=lambda x: x["h_siendo"])
            lineas.append(f"Las muestras de {lento['analisis']} son las que más tiempo pasan siendo analizadas antes "
                          f"de llegar ({numero(lento['h_siendo'], 1)} h): conviene darles prioridad en los despachos.")
        clinicas = self._por_clinica(f)
        if clinicas:
            mayor = max(clinicas, key=lambda c: c["ingresadas"])
            lineas.append(f"{mayor['clinica']} envía el {numero(porcentaje(mayor['ingresadas'], ingresadas), 0)} % "
                          "de las muestras: es la ruta que más conviene cuidar.")
        return lineas



# Agrupación de los reportes por tema: (nombre, ícono de Bootstrap Icons, color, descripción, reportes)
CATEGORIAS = [
    ("Clínicas", "hospital", "primary", "Actividad de cada clínica de la red", [ReporteAtencionesDerivaciones]),
    ("Pacientes", "heart-pulse", "danger", "Especies, tipos de atención y vacunación",
     [ReportePacientes, ReporteTratamientos, ReporteVacunasPendientes]),
    ("Muestras", "eyedropper", "info", "Ingresos, rechazos y tiempos del laboratorio",
     [ReporteMuestrasIngresadas, ReporteMuestrasRechazadas, ReporteTiemposMuestras]),
    ("Finanzas", "cash-coin", "success", "Ingresos por tipo de atención, clínica y servicio",
     [ReporteIngresosPorTipo, ReporteFacturacion]),
]

REPORTES = [reporte for *_, reportes in CATEGORIAS for reporte in reportes]
