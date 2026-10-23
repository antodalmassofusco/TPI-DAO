"""Registro de atenciones clínicas y emisión de órdenes de derivación a laboratorio."""
from veterinaria.config import PRECIOS_CONSULTA
from veterinaria.dominio.entidades import Consulta, OrdenDerivacion, VacunaAplicada, fecha_no_anterior
from veterinaria.dominio.muestra import Muestra
from veterinaria.excepciones import EntidadNoEncontradaError, ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r
from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.observadores import RegistroTrazabilidad
from veterinaria.servicios.vacunas import VacunaService
from veterinaria.utils.fechas import ahora, normalizar


class ConsultaService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = r.RepoConsulta(self.bd)
        self.vacunas = VacunaService(self.bd)

    def registrar(self, mascota_id, veterinario_id, tipo, motivo, diagnostico="", tratamiento="",
                  peso=None, vacunas=None, turno_id=None, fecha_hora=None):
        """Registra la atención. `vacunas` es una lista de (tipo_vacuna_id, lote).

        Devuelve (consulta, vacunas_pendientes): las obligatorias que siguen faltando luego
        de la atención, para alertar al profesional.
        """
        fecha_hora = normalizar(fecha_hora or ahora())
        mascota = r.RepoMascota(self.bd).obtener_o_error(mascota_id)
        veterinario = r.RepoVeterinario(self.bd).obtener_o_error(veterinario_id)
        if not mascota.activo:
            raise ValidacionError(f"{mascota.nombre} está dada de baja.")
        if not veterinario.activo:
            raise ValidacionError("El veterinario está inactivo.")

        with self.bd.transaccion():
            if turno_id:
                repo_turnos = r.RepoTurno(self.bd)
                turno = repo_turnos.obtener_o_error(turno_id)
                if turno.estado != "PENDIENTE":
                    raise ValidacionError(f"El turno seleccionado está {turno.estado}.")
                if turno.mascota_id != mascota.id or turno.veterinario_id != veterinario.id:
                    raise ValidacionError("El turno no corresponde a la mascota y veterinario indicados.")
                turno.estado = "ATENDIDO"
                repo_turnos.actualizar(turno)

            consulta = self.repo.insertar(Consulta(
                mascota_id=mascota.id, veterinario_id=veterinario.id, clinica_id=veterinario.clinica_id,
                fecha_hora=fecha_hora, tipo=tipo, motivo=motivo, diagnostico=diagnostico,
                tratamiento=tratamiento, peso=peso, precio=PRECIOS_CONSULTA.get(tipo, 0.0),
                turno_id=turno_id))

            repo_tipos = r.RepoTipoVacuna(self.bd)
            repo_aplicadas = r.RepoVacunaAplicada(self.bd)
            vistos = set()
            for tipo_vacuna_id, lote in vacunas or []:
                if tipo_vacuna_id in vistos:
                    raise ValidacionError("Se indicó la misma vacuna dos veces.")
                vistos.add(tipo_vacuna_id)
                tipo_vacuna = repo_tipos.obtener_o_error(tipo_vacuna_id)
                # Control del esquema de vacunas al registrar la atención
                self.vacunas.validar_aplicacion(mascota, tipo_vacuna, fecha_hora)
                repo_aplicadas.insertar(VacunaAplicada(
                    consulta_id=consulta.id, mascota_id=mascota.id, tipo_vacuna_id=tipo_vacuna.id,
                    fecha=fecha_hora, lote=lote or "", precio=tipo_vacuna.precio))

            if consulta.peso:
                mascota.peso = consulta.peso
                r.RepoMascota(self.bd).actualizar(mascota)

        return consulta, self.vacunas.pendientes(mascota, fecha_hora)

    def emitir_orden(self, consulta_id, tipos_analisis_ids, prioridad="NORMAL", observaciones="",
                     fecha_hora=None):
        """Emite la orden de derivación y registra la extracción de una muestra por análisis."""
        if not tipos_analisis_ids:
            raise ValidacionError("Debe seleccionar al menos un análisis.")
        if len(set(tipos_analisis_ids)) != len(tipos_analisis_ids):
            raise ValidacionError("Hay análisis repetidos en la orden.")
        consulta = self.repo.obtener_o_error(consulta_id)
        fecha_hora = normalizar(fecha_hora or ahora())
        fecha_no_anterior(fecha_hora, consulta.fecha_hora, "la orden", "la consulta")
        laboratorio = CatalogoService(self.bd).laboratorio_central()
        repo_tipos = r.RepoTipoAnalisis(self.bd)
        tipos = [repo_tipos.obtener_o_error(i) for i in tipos_analisis_ids]

        with self.bd.transaccion():
            orden = r.RepoOrden(self.bd).insertar(OrdenDerivacion(
                consulta_id=consulta.id, laboratorio_id=laboratorio.id, fecha_hora=fecha_hora,
                prioridad=prioridad, observaciones=observaciones))
            repo_muestras = r.RepoMuestra(self.bd)
            trazabilidad = RegistroTrazabilidad(self.bd)
            muestras = []
            for tipo in tipos:
                muestra = repo_muestras.insertar(Muestra(
                    codigo=self.bd.siguiente_numero("muestra", "M-"), orden_id=orden.id,
                    tipo_analisis_id=tipo.id, fecha_extraccion=fecha_hora))
                muestra.agregar_observador(trazabilidad)
                muestra.registrar_extraccion()
                muestras.append(muestra)
        return orden, muestras

    def detalle(self, consulta_id) -> dict:
        filas = self.listar(consulta_id=consulta_id)
        if not filas:
            raise EntidadNoEncontradaError(f"No existe la atención #{consulta_id}.")
        return filas[0]

    def listar(self, desde=None, hasta=None, mascota_id=None, consulta_id=None, limite=300):
        condiciones, parametros = ["1 = 1"], []
        if consulta_id:
            condiciones.append("co.id = ?")
            parametros.append(consulta_id)
        if desde:
            condiciones.append("co.fecha_hora >= ?")
            parametros.append(str(desde)[:10])
        if hasta:
            condiciones.append("co.fecha_hora <= ?")
            parametros.append(f"{str(hasta)[:10]} 23:59")
        if mascota_id:
            condiciones.append("co.mascota_id = ?")
            parametros.append(mascota_id)
        return self.bd.consultar(f"""
            SELECT co.*, m.nombre AS mascota, m.especie, v.apellido || ', ' || v.nombre AS veterinario,
                   cl.nombre AS clinica,
                   (SELECT COUNT(*) FROM orden_derivacion o WHERE o.consulta_id = co.id) AS ordenes,
                   (SELECT numero FROM comprobante cp WHERE cp.consulta_id = co.id) AS comprobante
            FROM consulta co
            JOIN mascota m ON m.id = co.mascota_id
            JOIN veterinario v ON v.id = co.veterinario_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE {' AND '.join(condiciones)}
            ORDER BY co.fecha_hora DESC LIMIT ?""", parametros + [limite])
