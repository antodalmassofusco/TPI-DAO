"""Registro de resultados y consulta de trazabilidad de muestras."""
from veterinaria.dominio.entidades import Resultado
from veterinaria.dominio.muestra import ETIQUETAS_ESTADO
from veterinaria.excepciones import EntidadNoEncontradaError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r
from veterinaria.servicios.observadores import AvisoAlCliente, RegistroTrazabilidad
from veterinaria.utils.fechas import ahora, normalizar


class LaboratorioService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo_muestras = r.RepoMuestra(self.bd)

    def registrar_resultado(self, muestra_id, profesional, valores, conclusion, observaciones="",
                            fecha_hora=None) -> Resultado:
        fecha_hora = normalizar(fecha_hora or ahora())
        muestra = self.repo_muestras.obtener_o_error(muestra_id)
        muestra.agregar_observador(RegistroTrazabilidad(self.bd))
        muestra.agregar_observador(AvisoAlCliente(self.bd))
        resultado = Resultado(muestra_id=muestra.id, fecha_hora=fecha_hora, profesional=profesional,
                              valores=valores, conclusion=conclusion, observaciones=observaciones)
        with self.bd.transaccion():
            # El estado decide: si la muestra fue rechazada lanza TransicionInvalidaError
            muestra.analizar(fecha_hora, f"Analizada por {profesional}")
            self.repo_muestras.actualizar(muestra)
            r.RepoResultado(self.bd).insertar(resultado)
        return resultado

    def muestras(self, estados=None):
        condicion, parametros = "", []
        if estados:
            condicion = f"WHERE mu.estado IN ({', '.join('?' for _ in estados)})"
            parametros = list(estados)
        filas = self.bd.consultar(f"""
            SELECT mu.*, ta.nombre AS analisis, ta.tipo_muestra, m.nombre AS mascota, m.especie,
                   cl.nombre AS clinica, re.numero AS remito, o.prioridad
            FROM muestra mu
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            JOIN clinica cl ON cl.id = co.clinica_id
            LEFT JOIN remito re ON re.id = mu.remito_id
            {condicion} ORDER BY o.prioridad DESC, mu.fecha_extraccion""", parametros)
        for f in filas:
            f["estado_etiqueta"] = ETIQUETAS_ESTADO[f["estado"]]
        return filas

    def trazabilidad(self, codigo):
        """Recorrido completo de una muestra: datos, bitácora de estados, envío y resultado."""
        muestra = self.bd.consultar_uno("""
            SELECT mu.*, ta.nombre AS analisis, ta.temp_min, ta.temp_max, ta.horas_viabilidad,
                   m.nombre AS mascota, c.apellido || ', ' || c.nombre AS responsable,
                   cl.nombre AS clinica, o.prioridad, co.id AS consulta_id,
                   re.numero AS remito, re.estado AS estado_remito, p.codigo AS precinto,
                   p.estado AS estado_precinto, ct.codigo AS contenedor, e.transportista, e.vehiculo
            FROM muestra mu
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            JOIN cliente c ON c.id = m.cliente_id
            JOIN clinica cl ON cl.id = co.clinica_id
            LEFT JOIN remito re ON re.id = mu.remito_id
            LEFT JOIN precinto p ON p.remito_id = re.id
            LEFT JOIN contenedor ct ON ct.id = re.contenedor_id
            LEFT JOIN envio e ON e.remito_id = re.id
            WHERE mu.codigo = ?""", (codigo.strip().upper(),))
        if muestra is None:
            raise EntidadNoEncontradaError(f"No existe la muestra {codigo}.")
        muestra["estado_etiqueta"] = ETIQUETAS_ESTADO[muestra["estado"]]
        historial = self.bd.consultar(
            "SELECT * FROM historial_estado_muestra WHERE muestra_id = ? ORDER BY id", (muestra["id"],))
        for h in historial:
            h["estado_anterior"] = ETIQUETAS_ESTADO.get(h["estado_anterior"], "—")
            h["estado_nuevo"] = ETIQUETAS_ESTADO[h["estado_nuevo"]]
        eventos = self.bd.consultar("""
            SELECT ev.* FROM evento_envio ev JOIN envio e ON e.id = ev.envio_id
            WHERE e.remito_id = ? ORDER BY ev.fecha_hora, ev.id""", (muestra["remito_id"],))
        resultado = self.bd.consultar_uno("SELECT * FROM resultado WHERE muestra_id = ?", (muestra["id"],))
        return {"muestra": muestra, "historial": historial, "eventos": eventos, "resultado": resultado}
