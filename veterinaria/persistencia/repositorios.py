"""Patrón Repository: aísla a los servicios del SQL de altas, bajas y modificaciones.

Un repositorio genérico mapea cada dataclass de dominio con su tabla (los nombres de los
atributos coinciden con los de las columnas). Las consultas con joins para listados y
reportes se escriben directamente en los servicios.
"""
from dataclasses import fields
from typing import Generic, Optional, TypeVar

from veterinaria.dominio import entidades as e
from veterinaria.dominio.muestra import Muestra
from veterinaria.excepciones import EntidadNoEncontradaError
from veterinaria.persistencia.conexion import BaseDatos

T = TypeVar("T")


class Repositorio(Generic[T]):
    tabla: str = ""
    entidad: type = None
    nombre: str = "registro"

    def __init__(self, bd: Optional[BaseDatos] = None):
        self.bd = bd or BaseDatos()

    def _campos(self):
        return [f.name for f in fields(self.entidad) if f.metadata.get("persistir", True)]

    def _a_entidad(self, fila) -> Optional[T]:
        if fila is None:
            return None
        return self.entidad(**{c: fila[c] for c in self._campos() if c in fila})

    @staticmethod
    def _a_sql(valor):
        return int(valor) if isinstance(valor, bool) else valor

    def obtener(self, id_) -> Optional[T]:
        return self._a_entidad(self.bd.consultar_uno(f"SELECT * FROM {self.tabla} WHERE id = ?", (id_,)))

    def obtener_o_error(self, id_) -> T:
        entidad = self.obtener(id_) if id_ else None
        if entidad is None:
            raise EntidadNoEncontradaError(f"No existe {self.nombre} con id {id_}.")
        return entidad

    def listar(self, condicion="", parametros=(), orden="id") -> list[T]:
        sql = f"SELECT * FROM {self.tabla}"
        if condicion:
            sql += f" WHERE {condicion}"
        sql += f" ORDER BY {orden}"
        return [self._a_entidad(f) for f in self.bd.consultar(sql, parametros)]

    def buscar_uno(self, condicion, parametros=()) -> Optional[T]:
        fila = self.bd.consultar_uno(f"SELECT * FROM {self.tabla} WHERE {condicion} LIMIT 1", parametros)
        return self._a_entidad(fila)

    def insertar(self, obj: T) -> T:
        campos = [c for c in self._campos() if c != "id"]
        valores = [self._a_sql(getattr(obj, c)) for c in campos]
        marcas = ", ".join("?" for _ in campos)
        cursor = self.bd.ejecutar(
            f"INSERT INTO {self.tabla} ({', '.join(campos)}) VALUES ({marcas})", valores)
        obj.id = cursor.lastrowid
        return obj

    def actualizar(self, obj: T) -> T:
        campos = [c for c in self._campos() if c != "id"]
        asignaciones = ", ".join(f"{c} = ?" for c in campos)
        valores = [self._a_sql(getattr(obj, c)) for c in campos] + [obj.id]
        self.bd.ejecutar(f"UPDATE {self.tabla} SET {asignaciones} WHERE id = ?", valores)
        return obj


def _repo(nombre_clase, tabla, entidad, nombre):
    return type(nombre_clase, (Repositorio,), {"tabla": tabla, "entidad": entidad, "nombre": nombre})


RepoClinica = _repo("RepoClinica", "clinica", e.Clinica, "la clínica")
RepoLaboratorio = _repo("RepoLaboratorio", "laboratorio", e.Laboratorio, "el laboratorio")
RepoVeterinario = _repo("RepoVeterinario", "veterinario", e.Veterinario, "el veterinario")
RepoCliente = _repo("RepoCliente", "cliente", e.Cliente, "el cliente")
RepoMascota = _repo("RepoMascota", "mascota", e.Mascota, "la mascota")
RepoTurno = _repo("RepoTurno", "turno", e.Turno, "el turno")
RepoConsulta = _repo("RepoConsulta", "consulta", e.Consulta, "la consulta")
RepoTipoVacuna = _repo("RepoTipoVacuna", "tipo_vacuna", e.TipoVacuna, "el tipo de vacuna")
RepoVacunaAplicada = _repo("RepoVacunaAplicada", "vacuna_aplicada", e.VacunaAplicada, "la vacuna aplicada")
RepoTipoAnalisis = _repo("RepoTipoAnalisis", "tipo_analisis", e.TipoAnalisis, "el tipo de análisis")
RepoOrden = _repo("RepoOrden", "orden_derivacion", e.OrdenDerivacion, "la orden de derivación")
RepoContenedor = _repo("RepoContenedor", "contenedor", e.Contenedor, "la conservadora")
RepoRemito = _repo("RepoRemito", "remito", e.Remito, "el remito")
RepoPrecinto = _repo("RepoPrecinto", "precinto", e.Precinto, "el precinto")
RepoMuestra = _repo("RepoMuestra", "muestra", Muestra, "la muestra")
RepoHistorial = _repo("RepoHistorial", "historial_estado_muestra", e.HistorialEstado, "el historial")
RepoEnvio = _repo("RepoEnvio", "envio", e.Envio, "el envío")
RepoEventoEnvio = _repo("RepoEventoEnvio", "evento_envio", e.EventoEnvio, "el evento de envío")
RepoRecepcion = _repo("RepoRecepcion", "recepcion", e.Recepcion, "la recepción")
RepoResultado = _repo("RepoResultado", "resultado", e.Resultado, "el resultado")
RepoComprobante = _repo("RepoComprobante", "comprobante", e.Comprobante, "el comprobante")
RepoItemComprobante = _repo("RepoItemComprobante", "item_comprobante", e.ItemComprobante, "el ítem")
RepoNotificacion = _repo("RepoNotificacion", "notificacion", e.Notificacion, "la notificación")
