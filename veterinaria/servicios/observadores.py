"""Observadores concretos de los cambios de estado de una muestra (patrón Observer)."""
from veterinaria.dominio.entidades import HistorialEstado, Notificacion
from veterinaria.dominio.muestra import ObservadorMuestra
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.repositorios import RepoHistorial, RepoNotificacion


class RegistroTrazabilidad(ObservadorMuestra):
    """Asienta cada cambio de estado en la bitácora inmutable de la muestra."""

    def __init__(self, bd):
        self.repo = RepoHistorial(bd)

    def estado_cambiado(self, muestra, anterior, nuevo, fecha_hora, detalle):
        ultimo = self.repo.bd.escalar(
            "SELECT MAX(fecha_hora) FROM historial_estado_muestra WHERE muestra_id = ?", (muestra.id,))
        if ultimo and fecha_hora < ultimo:
            raise ValidacionError(
                f"La fecha {fecha_hora} es anterior al último movimiento de la muestra {muestra.codigo} ({ultimo}).")
        self.repo.insertar(HistorialEstado(
            muestra_id=muestra.id, estado_anterior=anterior, estado_nuevo=nuevo,
            fecha_hora=fecha_hora, detalle=detalle))


class AvisoAlCliente(ObservadorMuestra):
    """Genera un aviso al responsable de la mascota cuando hay resultados o cuando la muestra
    fue rechazada y hay que volver a extraerla."""

    def __init__(self, bd):
        self.bd = bd
        self.repo = RepoNotificacion(bd)

    def estado_cambiado(self, muestra, anterior, nuevo, fecha_hora, detalle):
        if nuevo not in ("ANALIZADA", "RECHAZADA"):
            return
        datos = self.bd.consultar_uno("""
            SELECT c.id AS cliente_id, c.nombre || ' ' || c.apellido AS cliente,
                   COALESCE(NULLIF(c.email, ''), c.telefono) AS contacto,
                   m.id AS mascota_id, m.nombre AS mascota, ta.nombre AS analisis
            FROM muestra mu
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            JOIN cliente c ON c.id = m.cliente_id
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            WHERE mu.id = ?""", (muestra.id,))
        if nuevo == "ANALIZADA":
            tipo = "RESULTADO_LISTO"
            mensaje = (f"Hola {datos['cliente']}: ya están disponibles los resultados de "
                       f"{datos['analisis']} de {datos['mascota']} (muestra {muestra.codigo}).")
        else:
            tipo = "MUESTRA_RECHAZADA"
            mensaje = (f"Hola {datos['cliente']}: la muestra de {datos['mascota']} para {datos['analisis']} "
                       f"no pudo procesarse ({detalle}). Por favor solicite un nuevo turno de extracción.")
        self.repo.insertar(Notificacion(
            fecha_hora=fecha_hora, tipo=tipo, destinatario=datos["contacto"] or "-",
            mensaje=mensaje, cliente_id=datos["cliente_id"], mascota_id=datos["mascota_id"]))
