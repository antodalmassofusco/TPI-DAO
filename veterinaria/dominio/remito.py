"""Ciclo de vida del remito biológico.

Patrón State (igual que la muestra): cada estado es una clase que decide qué operaciones admite.
Una operación no permitida (p. ej. despachar un remito ya recibido) lanza TransicionInvalidaError.

    EMITIDO ──despachar──▶ EN_TRANSITO ──recibir──▶ RECIBIDO
       │                        │
       └──anular──▶ ANULADO     └──rechazar──▶ RECHAZADO   (precinto roto o todas las muestras rechazadas)

Patrón Observer: cada cambio de estado se notifica a los observadores registrados
(bitácora inmutable de estados del remito).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from veterinaria.excepciones import TransicionInvalidaError, ValidacionError
from veterinaria.utils.fechas import normalizar


class ObservadorRemito(ABC):
    @abstractmethod
    def estado_cambiado(self, remito: "Remito", anterior: Optional[str], nuevo: str,
                        fecha_hora: str, detalle: str) -> None:
        ...


class EstadoRemito(ABC):
    nombre: str = ""
    etiqueta: str = ""
    es_final: bool = False
    en_ruta: bool = False          # admite puntos de control y recepción

    def _no_permitido(self, accion: str):
        return TransicionInvalidaError(f"No se puede {accion} un remito en estado '{self.etiqueta}'.")

    def despachar(self, remito, fecha_hora, detalle):
        raise self._no_permitido("despachar")

    def anular(self, remito, fecha_hora, motivo):
        raise self._no_permitido("anular")

    def recibir(self, remito, fecha_hora, detalle):
        raise self._no_permitido("recibir")

    def rechazar(self, remito, fecha_hora, motivo):
        raise self._no_permitido("rechazar")


class Emitido(EstadoRemito):
    nombre, etiqueta = "EMITIDO", "Emitido"

    def despachar(self, remito, fecha_hora, detalle):
        remito._transicionar(EnTransito, fecha_hora, detalle)

    def anular(self, remito, fecha_hora, motivo):
        remito._transicionar(Anulado, fecha_hora, motivo)


class EnTransito(EstadoRemito):
    nombre, etiqueta = "EN_TRANSITO", "En tránsito"
    en_ruta = True

    def recibir(self, remito, fecha_hora, detalle):
        remito._transicionar(Recibido, fecha_hora, detalle)

    def rechazar(self, remito, fecha_hora, motivo):
        remito._transicionar(Rechazado, fecha_hora, motivo)


class Recibido(EstadoRemito):
    nombre, etiqueta = "RECIBIDO", "Recibido"
    es_final = True


class Rechazado(EstadoRemito):
    nombre, etiqueta = "RECHAZADO", "Rechazado"
    es_final = True


class Anulado(EstadoRemito):
    nombre, etiqueta = "ANULADO", "Anulado"
    es_final = True


ESTADOS_REMITO: dict[str, EstadoRemito] = {
    cls.nombre: cls() for cls in (Emitido, EnTransito, Recibido, Rechazado, Anulado)
}
ETIQUETAS_ESTADO_REMITO = {nombre: estado.etiqueta for nombre, estado in ESTADOS_REMITO.items()}


@dataclass
class Remito:
    """Remito biológico: documento que acompaña a la conservadora en todo su recorrido."""
    numero: str
    clinica_id: int
    laboratorio_id: int
    contenedor_id: int
    fecha_emision: str
    responsable: str
    estado: str = Emitido.nombre
    id: Optional[int] = None
    _observadores: list = field(default_factory=list, repr=False, compare=False,
                                metadata={"persistir": False})

    def __post_init__(self):
        if not str(self.responsable or "").strip():
            raise ValidacionError("El campo 'responsable del empaquetado' es obligatorio.")
        self.fecha_emision = normalizar(self.fecha_emision)
        if self.estado not in ESTADOS_REMITO:
            raise ValidacionError(f"Estado de remito desconocido: {self.estado}")

    # --- Observer ---------------------------------------------------------
    def agregar_observador(self, observador: ObservadorRemito):
        self._observadores.append(observador)

    def _notificar(self, anterior, nuevo, fecha_hora, detalle):
        for observador in self._observadores:
            observador.estado_cambiado(self, anterior, nuevo, fecha_hora, detalle)

    # --- State: las operaciones se delegan al estado actual -----------------
    @property
    def estado_actual(self) -> EstadoRemito:
        return ESTADOS_REMITO[self.estado]

    @property
    def etiqueta_estado(self) -> str:
        return self.estado_actual.etiqueta

    def registrar_emision(self, detalle=""):
        self._notificar(None, self.estado, self.fecha_emision, detalle or "Remito emitido y conservadora precintada")

    def despachar(self, fecha_hora, detalle=""):
        self.estado_actual.despachar(self, fecha_hora, detalle or "Despachado hacia el laboratorio central")

    def anular(self, fecha_hora, motivo):
        self.estado_actual.anular(self, fecha_hora, motivo)

    def recibir(self, fecha_hora, detalle=""):
        self.estado_actual.recibir(self, fecha_hora, detalle or "Recibido en el laboratorio central")

    def rechazar(self, fecha_hora, motivo):
        self.estado_actual.rechazar(self, fecha_hora, motivo)

    def _transicionar(self, nuevo_estado: type[EstadoRemito], fecha_hora, detalle):
        anterior = self.estado
        self.estado = nuevo_estado.nombre
        self._notificar(anterior, self.estado, normalizar(fecha_hora), detalle)
