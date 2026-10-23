"""Agenda médica: reserva de turnos sin superposición."""
from datetime import time, timedelta

from veterinaria.config import DURACION_TURNO_MIN, HORA_APERTURA, HORA_CIERRE
from veterinaria.dominio.entidades import Turno
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia.repositorios import RepoMascota, RepoTurno, RepoVeterinario
from veterinaria.utils.fechas import formatear, parse_fecha_hora


class TurnoService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = RepoTurno(self.bd)

    def _superpuesto(self, campo, valor, inicio, fin, excluir_id=None):
        return self.bd.consultar_uno(f"""
            SELECT t.*, m.nombre AS mascota, v.apellido AS veterinario
            FROM turno t JOIN mascota m ON m.id = t.mascota_id JOIN veterinario v ON v.id = t.veterinario_id
            WHERE t.{campo} = ? AND t.estado <> 'CANCELADO' AND t.inicio < ? AND t.fin > ? AND t.id IS NOT ?
            LIMIT 1""", (valor, fin, inicio, excluir_id))

    def reservar(self, veterinario_id, mascota_id, inicio, duracion_min=DURACION_TURNO_MIN,
                 motivo="", ahora=None) -> Turno:
        inicio_dt = parse_fecha_hora(inicio)
        try:
            duracion = int(duracion_min)
        except (TypeError, ValueError):
            raise ValidacionError("La duración debe ser un número entero de minutos.")
        if duracion <= 0:
            raise ValidacionError("La duración debe ser mayor a cero.")
        fin_dt = inicio_dt + timedelta(minutes=duracion)

        if ahora is not None and inicio_dt < parse_fecha_hora(ahora):
            raise ValidacionError("No se pueden reservar turnos en el pasado.")
        if (inicio_dt.time() < time(HORA_APERTURA) or fin_dt.date() != inicio_dt.date()
                or fin_dt.time() > time(HORA_CIERRE)):
            raise ValidacionError(f"El turno debe estar dentro del horario de atención "
                                  f"({HORA_APERTURA}:00 a {HORA_CIERRE}:00).")

        veterinario = RepoVeterinario(self.bd).obtener_o_error(veterinario_id)
        mascota = RepoMascota(self.bd).obtener_o_error(mascota_id)
        if not veterinario.activo or not mascota.activo:
            raise ValidacionError("El veterinario y la mascota deben estar activos.")

        turno = Turno(veterinario_id=veterinario_id, mascota_id=mascota_id,
                      inicio=formatear(inicio_dt), fin=formatear(fin_dt), motivo=motivo)
        choque = self._superpuesto("veterinario_id", veterinario_id, turno.inicio, turno.fin)
        if choque:
            raise ValidacionError(
                f"Superposición de agenda: {veterinario.nombre_completo} ya tiene un turno de "
                f"{choque['inicio'][11:]} a {choque['fin'][11:]} ({choque['mascota']}).")
        choque = self._superpuesto("mascota_id", mascota_id, turno.inicio, turno.fin)
        if choque:
            raise ValidacionError(
                f"{mascota.nombre} ya tiene un turno de {choque['inicio'][11:]} a {choque['fin'][11:]} "
                f"con {choque['veterinario']}.")
        return self.repo.insertar(turno)

    def cancelar(self, turno_id):
        turno = self.repo.obtener_o_error(turno_id)
        if turno.estado != "PENDIENTE":
            raise ValidacionError(f"Sólo se pueden cancelar turnos pendientes (estado actual: {turno.estado}).")
        turno.estado = "CANCELADO"
        self.repo.actualizar(turno)

    def listar(self, fecha=None, veterinario_id=None, estado=None, mascota_id=None):
        condiciones, parametros = ["1 = 1"], []
        if fecha:
            condiciones.append("substr(t.inicio, 1, 10) = ?")
            parametros.append(str(fecha)[:10])
        if veterinario_id:
            condiciones.append("t.veterinario_id = ?")
            parametros.append(veterinario_id)
        if estado:
            condiciones.append("t.estado = ?")
            parametros.append(estado)
        if mascota_id:
            condiciones.append("t.mascota_id = ?")
            parametros.append(mascota_id)
        return self.bd.consultar(f"""
            SELECT t.*, m.nombre AS mascota, v.apellido || ', ' || v.nombre AS veterinario,
                   cl.nombre AS clinica
            FROM turno t
            JOIN mascota m ON m.id = t.mascota_id
            JOIN veterinario v ON v.id = t.veterinario_id
            JOIN clinica cl ON cl.id = v.clinica_id
            WHERE {' AND '.join(condiciones)} ORDER BY t.inicio""", parametros)
