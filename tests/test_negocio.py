"""Pruebas de los procesos obligatorios y validaciones de negocio.

Ejecutar desde la raíz del proyecto:  python -m unittest -v
"""
import unittest
from datetime import datetime, timedelta

from veterinaria.dominio.entidades import Clinica, Laboratorio, TipoAnalisis, TipoVacuna, Veterinario
from veterinaria.dominio.muestra import Muestra
from veterinaria.excepciones import TransicionInvalidaError, ValidacionError
from veterinaria.persistencia import repositorios as r
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.reportes.reportes import REPORTES
from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.clientes import ClienteService
from veterinaria.servicios.comprobantes import ComprobanteService
from veterinaria.servicios.consultas import ConsultaService
from veterinaria.servicios.laboratorio import LaboratorioService
from veterinaria.servicios.logistica import LogisticaService
from veterinaria.servicios.mascotas import MascotaService
from veterinaria.servicios.turnos import TurnoService


def fh(dias=0, horas=0):
    base = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=5)
    return (base + timedelta(days=dias, hours=horas)).strftime("%Y-%m-%d %H:%M")


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.bd = BaseDatos.reiniciar(":memory:")
        self.clinica = r.RepoClinica(self.bd).insertar(Clinica("Clínica Centro", "Av. Colón 100"))
        r.RepoLaboratorio(self.bd).insertar(Laboratorio("Laboratorio Central", "Bv. San Juan 500"))
        self.vet = r.RepoVeterinario(self.bd).insertar(Veterinario("Ana", "Pérez", "MP-1", self.clinica.id))
        self.hemograma = r.RepoTipoAnalisis(self.bd).insertar(
            TipoAnalisis("Hemograma", "Sangre", 2, 8, 48, 9000))
        self.rabia = r.RepoTipoVacuna(self.bd).insertar(
            TipoVacuna("Antirrábica", "Perro", 3, 7000, True, 12))
        self.conservadora = CatalogoService(self.bd).alta_contenedor("CI-01", self.clinica.id, 2, 8, 4)
        self.cliente = ClienteService(self.bd).alta("30111222", "Juan", "Gómez", email="juan@mail.com")
        self.mascota = MascotaService(self.bd).alta("Firulais", "Perro", "2022-01-10", self.cliente.id)
        self.consultas = ConsultaService(self.bd)
        self.logistica = LogisticaService(self.bd)
        self.lab = LaboratorioService(self.bd)

    def _muestra_en_transito(self):
        consulta, _ = self.consultas.registrar(self.mascota.id, self.vet.id, "CONSULTA", "Decaimiento",
                                               fecha_hora=fh(0))
        _, muestras = self.consultas.emitir_orden(consulta.id, [self.hemograma.id], fecha_hora=fh(0, 1))
        remito, precinto = self.logistica.empaquetar(self.conservadora.id, [muestras[0].id], "Enf. Ruiz",
                                                     fecha_hora=fh(0, 2))
        self.logistica.despachar(remito.id, "Moto Express", 5, fecha_hora=fh(0, 3))
        return consulta, muestras[0], remito


class TestClientesYMascotas(BaseTest):
    def test_mascota_sin_responsable(self):
        with self.assertRaises(ValidacionError):
            MascotaService(self.bd).alta("Michi", "Gato", "2023-01-01", None)

    def test_dni_duplicado(self):
        with self.assertRaises(ValidacionError):
            ClienteService(self.bd).alta("30111222", "Otro", "Cliente")

    def test_no_baja_cliente_con_mascotas(self):
        with self.assertRaises(ValidacionError):
            ClienteService(self.bd).baja(self.cliente.id)


class TestAgenda(BaseTest):
    def test_superposicion_de_turnos(self):
        turnos = TurnoService(self.bd)
        otra = MascotaService(self.bd).alta("Luna", "Perro", "2021-05-01", self.cliente.id)
        turnos.reservar(self.vet.id, self.mascota.id, "2030-03-01 10:00", 30)
        with self.assertRaises(ValidacionError):
            turnos.reservar(self.vet.id, otra.id, "2030-03-01 10:15", 30)
        turnos.reservar(self.vet.id, otra.id, "2030-03-01 10:30", 30)  # contiguo: válido

    def test_fuera_de_horario(self):
        with self.assertRaises(ValidacionError):
            TurnoService(self.bd).reservar(self.vet.id, self.mascota.id, "2030-03-01 19:45", 30)


class TestVacunas(BaseTest):
    def test_pendiente_y_refuerzo_prematuro(self):
        _, pendientes = self.consultas.registrar(self.mascota.id, self.vet.id, "CONTROL", "Control anual",
                                                 fecha_hora=fh(0))
        self.assertEqual([p["tipo"].nombre for p in pendientes], ["Antirrábica"])
        _, pendientes = self.consultas.registrar(self.mascota.id, self.vet.id, "CONTROL", "Vacunación",
                                                 vacunas=[(self.rabia.id, "L1")], fecha_hora=fh(1))
        self.assertEqual(pendientes, [])
        with self.assertRaises(ValidacionError):
            self.consultas.registrar(self.mascota.id, self.vet.id, "CONTROL", "Otra",
                                     vacunas=[(self.rabia.id, "L2")], fecha_hora=fh(2))


class TestCicloDeVidaMuestra(BaseTest):
    def test_recorrido_completo_y_trazabilidad(self):
        consulta, muestra, remito = self._muestra_en_transito()
        self.logistica.registrar_punto_control(remito.id, "Ruta 9 km 12", 6, fecha_hora=fh(0, 4))
        _, detalle = self.logistica.recibir(remito.id, "Bioq. Sosa", True, 5, fecha_hora=fh(0, 5))
        self.assertIsNone(detalle[0][1])
        self.lab.registrar_resultado(muestra.id, "Bioq. Sosa", "Hto 45%", "Normal", fecha_hora=fh(0, 8))
        traza = self.lab.trazabilidad(muestra.codigo)
        estados = [h["estado_nuevo"] for h in traza["historial"]]
        self.assertEqual(estados, ["Extraída", "Empaquetada", "En tránsito", "Recibida", "Analizada"])
        comprobante = ComprobanteService(self.bd).emitir(consulta.id, fh(1))
        self.assertEqual(comprobante.total, 18000 + 9000)
        # aviso automático al cliente (Observer)
        self.assertEqual(self.bd.escalar("SELECT COUNT(*) FROM notificacion WHERE tipo='RESULTADO_LISTO'"), 1)

    def test_precinto_roto_rechaza_y_bloquea_procesamiento(self):
        consulta, muestra, remito = self._muestra_en_transito()
        _, detalle = self.logistica.recibir(remito.id, "Bioq. Sosa", False, 5, fecha_hora=fh(0, 5))
        self.assertIn("Precinto", detalle[0][1])
        self.assertEqual(r.RepoMuestra(self.bd).obtener(muestra.id).estado, "RECHAZADA")
        self.assertEqual(r.RepoRemito(self.bd).obtener(remito.id).estado, "RECHAZADO")
        with self.assertRaises(TransicionInvalidaError):
            self.lab.registrar_resultado(muestra.id, "Bioq. Sosa", "x", "x", fecha_hora=fh(0, 6))
        # el rechazo no se factura
        self.assertEqual(ComprobanteService(self.bd).emitir(consulta.id, fh(1)).total, 18000)

    def test_ruptura_cadena_de_frio(self):
        _, muestra, remito = self._muestra_en_transito()
        self.logistica.registrar_punto_control(remito.id, "Peaje", 14, fecha_hora=fh(0, 4))
        _, detalle = self.logistica.recibir(remito.id, "Bioq. Sosa", True, 6, fecha_hora=fh(0, 5))
        self.assertIn("cadena de frío", detalle[0][1])

    def test_historial_inmutable(self):
        _, muestra, _ = self._muestra_en_transito()
        with self.assertRaises(ValidacionError):
            self.bd.ejecutar("UPDATE historial_estado_muestra SET estado_nuevo = 'ANALIZADA'")
        with self.assertRaises(ValidacionError):
            self.bd.ejecutar("DELETE FROM historial_estado_muestra")

    def test_transicion_invalida_en_dominio(self):
        m = Muestra("M-X", 1, 1, fh(0))
        with self.assertRaises(TransicionInvalidaError):
            m.analizar(fh(1))

    def test_conservadora_no_apta(self):
        congelada = CatalogoService(self.bd).alta_contenedor("CI-02", self.clinica.id, -20, -10, 4)
        consulta, _ = self.consultas.registrar(self.mascota.id, self.vet.id, "CONSULTA", "x", fecha_hora=fh(0))
        _, muestras = self.consultas.emitir_orden(consulta.id, [self.hemograma.id], fecha_hora=fh(0))
        with self.assertRaises(ValidacionError):
            self.logistica.empaquetar(congelada.id, [muestras[0].id], "Enf.", fecha_hora=fh(0, 1))

    def test_comprobante_requiere_resultados(self):
        consulta, _, _ = self._muestra_en_transito()
        with self.assertRaises(ValidacionError):
            ComprobanteService(self.bd).emitir(consulta.id)


class TestReportes(BaseTest):
    def test_todos_los_reportes_generan(self):
        consulta, muestra, remito = self._muestra_en_transito()
        self.logistica.recibir(remito.id, "Bioq. Sosa", True, 5, fecha_hora=fh(0, 5))
        self.lab.registrar_resultado(muestra.id, "Bioq. Sosa", "ok", "ok", fecha_hora=fh(0, 9))
        ComprobanteService(self.bd).emitir(consulta.id, fh(1))
        for clase in REPORTES:
            resultado = clase(self.bd).generar(desde=fh(-10)[:10], hasta=fh(10)[:10])
            self.assertIsInstance(resultado.filas, list, clase.__name__)
        tiempos = REPORTES[-1](self.bd).generar(desde=fh(-10)[:10], hasta=fh(10)[:10])
        self.assertEqual(tiempos.filas[0]["h_transito"], 2.0)


if __name__ == "__main__":
    unittest.main()
