"""Recordatorios y avisos a clientes (proceso opcional)."""
from veterinaria.dominio.entidades import Notificacion
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r
from veterinaria.servicios.vacunas import VacunaService
from veterinaria.utils.fechas import ahora, hoy


class NotificacionService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = r.RepoNotificacion(self.bd)

    def listar(self, solo_pendientes=False):
        condicion = "WHERE n.enviada = 0" if solo_pendientes else ""
        return self.bd.consultar(f"""
            SELECT n.*, m.nombre AS mascota FROM notificacion n
            LEFT JOIN mascota m ON m.id = n.mascota_id
            {condicion} ORDER BY n.fecha_hora DESC, n.id DESC""")

    def marcar_enviada(self, notificacion_id):
        notificacion = self.repo.obtener_o_error(notificacion_id)
        notificacion.enviada = True
        self.repo.actualizar(notificacion)

    def generar_recordatorios_vacunas(self, referencia=None) -> int:
        """Crea un recordatorio por mascota con vacunas obligatorias pendientes o vencidas.
        No duplica recordatorios que aún no fueron enviados."""
        referencia = referencia or hoy()
        vacunas = VacunaService(self.bd)
        creadas = 0
        with self.bd.transaccion():
            for mascota in r.RepoMascota(self.bd).listar("activo = 1"):
                pendientes = vacunas.pendientes(mascota, referencia)
                if not pendientes:
                    continue
                if self.repo.buscar_uno("tipo = 'RECORDATORIO_VACUNA' AND mascota_id = ? AND enviada = 0",
                                        (mascota.id,)):
                    continue
                cliente = r.RepoCliente(self.bd).obtener(mascota.cliente_id)
                detalle = ", ".join(f"{p['tipo'].nombre} ({p['estado'].lower()})" for p in pendientes)
                self.repo.insertar(Notificacion(
                    fecha_hora=ahora(), tipo="RECORDATORIO_VACUNA",
                    destinatario=cliente.email or cliente.telefono or "-",
                    mensaje=f"Hola {cliente.nombre}: {mascota.nombre} tiene vacunas por aplicar: {detalle}.",
                    cliente_id=cliente.id, mascota_id=mascota.id))
                creadas += 1
        return creadas
