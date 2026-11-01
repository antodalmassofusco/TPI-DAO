"""Pruebas de la interfaz web: todas las páginas cargan y el circuito completo funciona desde los formularios."""
import re
import unittest

from datos_prueba import cargar_datos_prueba
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.utils.fechas import ahora
from veterinaria.web import crear_app


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bd = cargar_datos_prueba(":memory:")
        cls.app = crear_app()
        cls.app.testing = True

    @classmethod
    def tearDownClass(cls):
        BaseDatos.cerrar()

    def setUp(self):
        self.web = self.app.test_client()

    def ok(self, url):
        respuesta = self.web.get(url)
        self.assertEqual(respuesta.status_code, 200, url)
        return respuesta.get_data(as_text=True)

    def post(self, url, datos):
        return self.web.post(url, data=datos, follow_redirects=True).get_data(as_text=True)

    def test_todas_las_paginas(self):
        muestra = self.bd.consultar_uno("SELECT id, codigo FROM muestra WHERE estado = 'RECHAZADA' LIMIT 1")
        remito = self.bd.escalar("SELECT id FROM remito LIMIT 1")
        comprobante = self.bd.escalar("SELECT id FROM comprobante LIMIT 1")
        for url in ["/", "/clientes", "/clientes?editar=1", "/mascotas", "/mascotas?editar=1", "/mascotas/1/historia",
                    "/agenda", "/agenda?fecha=", "/atencion", "/atencion?mascota=1", "/atencion/1/orden",
                    "/logistica/empaquetado", "/logistica/remitos", "/logistica/remitos?estado=",
                    f"/logistica/remitos/{remito}", "/laboratorio/resultados?filtro=rechazadas",
                    f"/laboratorio/muestras/{muestra['id']}", f"/laboratorio/trazabilidad?codigo={muestra['codigo']}",
                    "/comprobantes", f"/comprobantes/{comprobante}", "/avisos", "/avisos?pendientes=0"]:
            self.ok(url)
        for clase in ("ReporteAtencionesDerivaciones", "ReporteMuestrasRechazadas", "ReporteTratamientos",
                      "ReporteVacunasPendientes", "ReporteFacturacion", "ReporteTiemposMuestras"):
            self.assertIn("<table", self.ok(f"/reportes?reporte={clase}"))
            self.assertEqual(self.web.get(f"/reportes/csv?reporte={clase}").status_code, 200)

    def test_ids_inexistentes_no_rompen(self):
        for url in ["/clientes?editar=99999", "/mascotas?editar=99999", "/mascotas/99999/historia",
                    "/atencion?mascota=99999", "/atencion/99999/orden", "/comprobantes/99999"]:
            respuesta = self.web.get(url, follow_redirects=True)
            self.assertEqual(respuesta.status_code, 200, url)
            self.assertIn("No existe", respuesta.get_data(as_text=True), url)
        self.ok("/laboratorio/resultados?filtro=inexistente")
        respuesta = self.web.get("/reportes/csv?reporte=ReporteFacturacion&desde=2026-12-01&hasta=2026-01-01",
                                 follow_redirects=True)
        self.assertIn("no puede ser posterior", respuesta.get_data(as_text=True))

    def test_remito_muestra_su_bitacora(self):
        remito = self.bd.escalar("SELECT id FROM remito WHERE estado = 'ANULADO'")
        html = self.ok(f"/logistica/remitos/{remito}")
        self.assertIn("Estados del remito", html)
        self.assertIn("Anulado", html)

    def test_validaciones_se_muestran(self):
        html = self.post("/mascotas", {"nombre": "Sin dueño", "especie": "Perro", "fecha_nacimiento": "2020-01-01"})
        self.assertIn("responsable", html)
        html = self.post("/clientes", {"dni": "123", "nombre": "A", "apellido": "B"})
        self.assertIn("7 u 8 dígitos", html)

    def test_cancelar_turno_ya_cancelado_no_rompe(self):
        vet = self.bd.escalar("SELECT id FROM veterinario LIMIT 1")
        self.bd.ejecutar("INSERT INTO turno (veterinario_id, mascota_id, inicio, fin, estado) "
                         "VALUES (?, 1, '2030-03-01 10:00', '2030-03-01 10:30', 'CANCELADO')", (vet,))
        turno = self.bd.escalar("SELECT MAX(id) FROM turno")
        respuesta = self.web.post(f"/agenda/{turno}/cancelar", follow_redirects=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Sólo se pueden cancelar", respuesta.get_data(as_text=True))

    def _muestra_empaquetada(self):
        fecha = ahora()
        vet = self.bd.consultar_uno("SELECT id, clinica_id FROM veterinario LIMIT 1")
        html = self.post("/atencion", {"mascota_id": 1, "veterinario_id": vet["id"], "tipo": "CONSULTA",
                                       "fecha_hora": fecha.replace(" ", "T"), "motivo": "Control web", "derivar": "1"})
        consulta_id = int(re.search(r"Atención #(\d+) registrada", html).group(1))
        analisis = self.bd.escalar("SELECT id FROM tipo_analisis WHERE nombre = 'Hemograma completo'")
        html = self.post(f"/atencion/{consulta_id}/orden", {"analisis": analisis, "prioridad": "NORMAL"})
        codigo = re.search(r"Muestras extraídas: (M-\d+)", html).group(1)
        muestra_id = self.bd.escalar("SELECT id FROM muestra WHERE codigo = ?", (codigo,))
        contenedor = self.bd.escalar(
            "SELECT id FROM contenedor WHERE clinica_id = ? AND estado = 'DISPONIBLE' AND temp_max <= 8", (vet["clinica_id"],))
        self.post("/logistica/empaquetado", {"clinica": vet["clinica_id"], "muestras": muestra_id,
                                             "contenedor_id": contenedor, "responsable": "Enf. Web", "fecha_hora": fecha})
        remito_id = self.bd.escalar("SELECT remito_id FROM muestra WHERE id = ?", (muestra_id,))
        return muestra_id, remito_id, contenedor, fecha

    def test_anular_remito_desde_la_web(self):
        muestra_id, remito_id, contenedor, fecha = self._muestra_empaquetada()
        self.assertIn("Anular remito", self.ok(f"/logistica/remitos/{remito_id}"))
        html = self.post(f"/logistica/remitos/{remito_id}/anular", {"responsable": "", "motivo": "", "fecha_hora": fecha})
        self.assertIn("Indique quién anula", html)
        html = self.post(f"/logistica/remitos/{remito_id}/anular",
                         {"responsable": "Enf. Web", "motivo": "Se canceló el retiro", "fecha_hora": fecha})
        self.assertIn("Remito anulado", html)
        self.assertEqual(self.bd.escalar("SELECT estado FROM muestra WHERE id = ?", (muestra_id,)), "RECHAZADA")
        self.assertEqual(self.bd.escalar("SELECT estado FROM contenedor WHERE id = ?", (contenedor,)), "DISPONIBLE")
        self.ok("/logistica/remitos?estado=ANULADO")

    def test_rechazar_muestra_desde_la_web(self):
        muestra_id, remito_id, _, fecha = self._muestra_empaquetada()
        self.post(f"/logistica/remitos/{remito_id}/despachar",
                  {"transportista": "Moto Web", "temperatura": "5", "fecha_hora": fecha})
        self.post(f"/logistica/remitos/{remito_id}/recibir",
                  {"precinto": "INTACTO", "recibido_por": "Bioq. Web", "temperatura": "5", "fecha_hora": fecha})
        self.assertIn("Rechazar muestra", self.ok(f"/laboratorio/muestras/{muestra_id}"))
        html = self.post(f"/laboratorio/muestras/{muestra_id}/rechazar",
                         {"profesional": "Bioq. Web", "motivo": "Hemolizada", "fecha_hora": fecha})
        self.assertIn("Muestra rechazada", html)
        self.assertNotIn("Rechazar muestra", self.ok(f"/laboratorio/muestras/{muestra_id}"))

    def test_circuito_completo_de_una_muestra(self):
        fecha = ahora()
        vet = self.bd.consultar_uno("SELECT id, clinica_id FROM veterinario LIMIT 1")
        html = self.post("/atencion", {"mascota_id": 1, "veterinario_id": vet["id"], "tipo": "CONSULTA",
                                       "fecha_hora": fecha.replace(" ", "T"), "motivo": "Control web", "derivar": "1"})
        consulta_id = int(re.search(r"Atención #(\d+) registrada", html).group(1))
        analisis = self.bd.escalar("SELECT id FROM tipo_analisis WHERE nombre = 'Hemograma completo'")
        html = self.post(f"/atencion/{consulta_id}/orden", {"analisis": analisis, "prioridad": "URGENTE"})
        codigo = re.search(r"Muestras extraídas: (M-\d+)", html).group(1)
        muestra_id = self.bd.escalar("SELECT id FROM muestra WHERE codigo = ?", (codigo,))

        contenedor = self.bd.escalar(
            "SELECT id FROM contenedor WHERE clinica_id = ? AND estado = 'DISPONIBLE' AND temp_max <= 8", (vet["clinica_id"],))
        html = self.post("/logistica/empaquetado", {"clinica": vet["clinica_id"], "muestras": muestra_id,
                                                    "contenedor_id": contenedor, "responsable": "Enf. Web",
                                                    "fecha_hora": fecha})
        self.assertIn("Remito biológico", html)
        remito_id = self.bd.escalar("SELECT remito_id FROM muestra WHERE id = ?", (muestra_id,))
        self.post(f"/logistica/remitos/{remito_id}/despachar",
                  {"transportista": "Moto Web", "temperatura": "5", "fecha_hora": fecha})
        self.post(f"/logistica/remitos/{remito_id}/control",
                  {"ubicacion": "Peaje", "temperatura": "12.5", "fecha_hora": fecha})
        html = self.post(f"/logistica/remitos/{remito_id}/recibir",
                         {"precinto": "INTACTO", "recibido_por": "Bioq. Web", "temperatura": "6", "fecha_hora": fecha})
        self.assertIn("cadena de frío", html)
        # una muestra rechazada no puede procesarse
        html = self.post(f"/laboratorio/muestras/{muestra_id}",
                         {"profesional": "Bioq", "valores": "x", "conclusion": "x", "fecha_hora": fecha})
        self.assertIn("No puede procesarse", html)
        html = self.post(f"/comprobantes/emitir/{consulta_id}", {})
        self.assertIn("Comprobante", html)


if __name__ == "__main__":
    unittest.main()
