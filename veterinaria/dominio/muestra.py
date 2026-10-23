"""Ciclo de vida de la muestra biológica.

Patrón State: cada estado es una clase que decide qué operaciones admite. Una operación
no permitida (p. ej. analizar una muestra rechazada) lanza TransicionInvalidaError.

    EXTRAIDA ──empaquetar──▶ EMPAQUETADA ──despachar──▶ EN_TRANSITO ──recibir──▶ RECIBIDA ──analizar──▶ ANALIZADA
        │                                                    │                     │
        └──────────────────────rechazar──────────────────────┴─────────────────────┴──▶ RECHAZADA

Patrón Observer: cada cambio de estado se notifica a los observadores registrados
(bitácora inmutable de trazabilidad, avisos al cliente, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from veterinaria.excepciones import TransicionInvalidaError, ValidacionError
from veterinaria.utils.fechas import normalizar


class ObservadorMuestra(ABC):
    @abstractmethod
    def estado_cambiado(self, muestra: "Muestra", anterior: Optional[str], nuevo: str,
                        fecha_hora: str, detalle: str) -> None:
        ...


class EstadoMuestra(ABC):
    nombre: str = ""
    etiqueta: str = ""
    es_final: bool = False

    def _no_permitido(self, accion: str):
        return TransicionInvalidaError(
            f"No se puede {accion} una muestra en estado '{self.etiqueta}'.")

    def empaquetar(self, muestra, remito_id, fecha_hora):
        raise self._no_permitido("empaquetar")

    def despachar(self, muestra, fecha_hora, detalle):
        raise self._no_permitido("despachar")

    def recibir(self, muestra, fecha_hora, detalle):
        raise self._no_permitido("recibir")

    def rechazar(self, muestra, motivo, fecha_hora):
        raise self._no_permitido("rechazar")

    def analizar(self, muestra, fecha_hora, detalle):
        raise self._no_permitido("analizar")


class Extraida(EstadoMuestra):
    nombre, etiqueta = "EXTRAIDA", "Extraída"

    def empaquetar(self, muestra, remito_id, fecha_hora):
        muestra.remito_id = remito_id
        muestra._transicionar(Empaquetada, fecha_hora, "Empaquetada en conservadora isotérmica")

    def rechazar(self, muestra, motivo, fecha_hora):
        # Descarte en la clínica (p. ej. venció su ventana de viabilidad antes de enviarse)
        muestra.motivo_rechazo = motivo
        muestra._transicionar(Rechazada, fecha_hora, motivo)


class Empaquetada(EstadoMuestra):
    nombre, etiqueta = "EMPAQUETADA", "Empaquetada"

    def despachar(self, muestra, fecha_hora, detalle):
        muestra._transicionar(EnTransito, fecha_hora, detalle or "Despachada hacia el laboratorio central")


class EnTransito(EstadoMuestra):
    nombre, etiqueta = "EN_TRANSITO", "En tránsito"

    def recibir(self, muestra, fecha_hora, detalle):
        muestra._transicionar(Recibida, fecha_hora, detalle or "Recibida en laboratorio: muestra viable")

    def rechazar(self, muestra, motivo, fecha_hora):
        muestra.motivo_rechazo = motivo
        muestra._transicionar(Rechazada, fecha_hora, motivo)


class Recibida(EstadoMuestra):
    nombre, etiqueta = "RECIBIDA", "Recibida"

    def analizar(self, muestra, fecha_hora, detalle):
        muestra._transicionar(Analizada, fecha_hora, detalle or "Análisis finalizado")

    def rechazar(self, muestra, motivo, fecha_hora):
        # El laboratorio puede descartarla al procesarla (p. ej. muestra hemolizada)
        muestra.motivo_rechazo = motivo
        muestra._transicionar(Rechazada, fecha_hora, motivo)


class Analizada(EstadoMuestra):
    nombre, etiqueta = "ANALIZADA", "Analizada"
    es_final = True


class Rechazada(EstadoMuestra):
    nombre, etiqueta = "RECHAZADA", "Muestra Rechazada"
    es_final = True

    def analizar(self, muestra, fecha_hora, detalle):
        raise TransicionInvalidaError(
            f"La muestra {muestra.codigo} fue rechazada ({muestra.motivo_rechazo}). "
            "No puede procesarse: se requiere una nueva extracción.")


ESTADOS: dict[str, EstadoMuestra] = {
    cls.nombre: cls() for cls in (Extraida, Empaquetada, EnTransito, Recibida, Analizada, Rechazada)
}
ETIQUETAS_ESTADO = {nombre: estado.etiqueta for nombre, estado in ESTADOS.items()}


@dataclass
class Muestra:
    codigo: str
    orden_id: int
    tipo_analisis_id: int
    fecha_extraccion: str
    estado: str = Extraida.nombre
    remito_id: Optional[int] = None
    motivo_rechazo: Optional[str] = None
    id: Optional[int] = None
    _observadores: list = field(default_factory=list, repr=False, compare=False,
                                metadata={"persistir": False})

    def __post_init__(self):
        self.fecha_extraccion = normalizar(self.fecha_extraccion)
        if self.estado not in ESTADOS:
            raise ValidacionError(f"Estado de muestra desconocido: {self.estado}")

    # --- Observer ---------------------------------------------------------
    def agregar_observador(self, observador: ObservadorMuestra):
        self._observadores.append(observador)

    def _notificar(self, anterior, nuevo, fecha_hora, detalle):
        for observador in self._observadores:
            observador.estado_cambiado(self, anterior, nuevo, fecha_hora, detalle)

    # --- State: las operaciones se delegan al estado actual -----------------
    @property
    def estado_actual(self) -> EstadoMuestra:
        return ESTADOS[self.estado]

    @property
    def etiqueta_estado(self) -> str:
        return self.estado_actual.etiqueta

    def registrar_extraccion(self):
        self._notificar(None, self.estado, self.fecha_extraccion, "Muestra extraída en la clínica")

    def empaquetar(self, remito_id, fecha_hora):
        self.estado_actual.empaquetar(self, remito_id, fecha_hora)

    def despachar(self, fecha_hora, detalle=""):
        self.estado_actual.despachar(self, fecha_hora, detalle)

    def recibir(self, fecha_hora, detalle=""):
        self.estado_actual.recibir(self, fecha_hora, detalle)

    def rechazar(self, motivo, fecha_hora):
        self.estado_actual.rechazar(self, motivo, fecha_hora)

    def analizar(self, fecha_hora, detalle=""):
        self.estado_actual.analizar(self, fecha_hora, detalle)

    def _transicionar(self, nuevo_estado: type[EstadoMuestra], fecha_hora, detalle):
        anterior = self.estado
        self.estado = nuevo_estado.nombre
        self._notificar(anterior, self.estado, normalizar(fecha_hora), detalle)
