"""Entidades del dominio. Cada una valida sus propias invariantes al construirse,
por lo que es imposible persistir un objeto inconsistente."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from veterinaria.config import ESPECIES, PRIORIDADES, SEXOS, TIPOS_CONSULTA
from veterinaria.excepciones import TransicionInvalidaError, ValidacionError
from veterinaria.utils.fechas import hoy, meses_entre, normalizar, parse_fecha, parse_fecha_hora


def _requerido(valor, nombre):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValidacionError(f"El campo '{nombre}' es obligatorio.")


def _numero(valor, nombre, positivo=False, opcional=False):
    if valor in (None, ""):
        if opcional:
            return None
        raise ValidacionError(f"El campo '{nombre}' es obligatorio.")
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"El campo '{nombre}' debe ser numérico.")
    if positivo and numero <= 0:
        raise ValidacionError(f"El campo '{nombre}' debe ser mayor a cero.")
    return numero


@dataclass
class Clinica:
    nombre: str
    direccion: str
    telefono: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.nombre, "nombre")
        _requerido(self.direccion, "dirección")


@dataclass
class Laboratorio:
    nombre: str
    direccion: str
    telefono: str = ""
    id: Optional[int] = None


@dataclass
class Veterinario:
    nombre: str
    apellido: str
    matricula: str
    clinica_id: int
    especialidad: str = ""
    activo: bool = True
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.nombre, "nombre")
        _requerido(self.apellido, "apellido")
        _requerido(self.matricula, "matrícula")
        _requerido(self.clinica_id, "clínica")
        self.activo = bool(self.activo)

    @property
    def nombre_completo(self):
        return f"{self.apellido}, {self.nombre}"


@dataclass
class Cliente:
    dni: str
    nombre: str
    apellido: str
    telefono: str = ""
    email: str = ""
    direccion: str = ""
    activo: bool = True
    id: Optional[int] = None

    def __post_init__(self):
        self.dni = str(self.dni or "").strip()
        if not re.fullmatch(r"\d{7,8}", self.dni):
            raise ValidacionError("El DNI debe tener 7 u 8 dígitos numéricos.")
        _requerido(self.nombre, "nombre")
        _requerido(self.apellido, "apellido")
        self.email = (self.email or "").strip()
        if self.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            raise ValidacionError(f"El email '{self.email}' no es válido.")
        self.activo = bool(self.activo)

    @property
    def nombre_completo(self):
        return f"{self.apellido}, {self.nombre}"


@dataclass
class Mascota:
    nombre: str
    especie: str
    fecha_nacimiento: str
    cliente_id: Optional[int]
    raza: str = ""
    sexo: str = "M"
    peso: Optional[float] = None
    activo: bool = True
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.nombre, "nombre")
        if self.especie not in ESPECIES:
            raise ValidacionError(f"Especie inválida. Valores admitidos: {', '.join(ESPECIES)}.")
        # Validación de negocio: toda mascota debe tener un responsable asociado
        if not self.cliente_id:
            raise ValidacionError("Toda mascota debe tener un responsable (cliente) asociado.")
        nacimiento = parse_fecha(self.fecha_nacimiento)
        if nacimiento > hoy():
            raise ValidacionError("La fecha de nacimiento no puede ser futura.")
        self.fecha_nacimiento = nacimiento.isoformat()
        if self.sexo not in SEXOS:
            raise ValidacionError("El sexo debe ser 'M' (macho) o 'H' (hembra).")
        self.peso = _numero(self.peso, "peso", positivo=True, opcional=True)
        self.activo = bool(self.activo)

    def edad_meses(self, referencia: date | None = None) -> int:
        return meses_entre(parse_fecha(self.fecha_nacimiento), referencia or hoy())


@dataclass
class Turno:
    veterinario_id: int
    mascota_id: int
    inicio: str
    fin: str
    motivo: str = ""
    estado: str = "PENDIENTE"
    id: Optional[int] = None

    def __post_init__(self):
        self.inicio = normalizar(self.inicio)
        self.fin = normalizar(self.fin)
        if self.fin <= self.inicio:
            raise ValidacionError("El fin del turno debe ser posterior al inicio.")

    def se_superpone(self, inicio: str, fin: str) -> bool:
        return self.inicio < fin and inicio < self.fin


@dataclass
class Consulta:
    mascota_id: int
    veterinario_id: int
    clinica_id: int
    fecha_hora: str
    tipo: str
    motivo: str
    diagnostico: str = ""
    tratamiento: str = ""
    peso: Optional[float] = None
    precio: float = 0.0
    turno_id: Optional[int] = None
    id: Optional[int] = None

    def __post_init__(self):
        self.fecha_hora = normalizar(self.fecha_hora)
        if self.tipo not in TIPOS_CONSULTA:
            raise ValidacionError(f"Tipo de atención inválido. Valores: {', '.join(TIPOS_CONSULTA)}.")
        _requerido(self.motivo, "motivo")
        self.peso = _numero(self.peso, "peso", positivo=True, opcional=True)


@dataclass
class TipoVacuna:
    nombre: str
    especie: str
    edad_minima_meses: int
    precio: float
    obligatoria: bool = True
    intervalo_refuerzo_meses: Optional[int] = None
    id: Optional[int] = None

    def __post_init__(self):
        self.obligatoria = bool(self.obligatoria)


@dataclass
class VacunaAplicada:
    consulta_id: int
    mascota_id: int
    tipo_vacuna_id: int
    fecha: str
    precio: float
    lote: str = ""
    id: Optional[int] = None


@dataclass
class TipoAnalisis:
    nombre: str
    tipo_muestra: str
    temp_min: float
    temp_max: float
    horas_viabilidad: int
    precio: float
    id: Optional[int] = None

    def temperatura_admisible(self, temperatura: float) -> bool:
        return self.temp_min <= temperatura <= self.temp_max


@dataclass
class OrdenDerivacion:
    consulta_id: int
    laboratorio_id: int
    fecha_hora: str
    prioridad: str = "NORMAL"
    observaciones: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        self.fecha_hora = normalizar(self.fecha_hora)
        if self.prioridad not in PRIORIDADES:
            raise ValidacionError("Prioridad inválida.")


@dataclass
class Contenedor:
    """Conservadora isotérmica reutilizable para transportar muestras."""
    codigo: str
    clinica_id: int
    temp_min: float
    temp_max: float
    capacidad: int
    descripcion: str = ""
    estado: str = "DISPONIBLE"
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.codigo, "código")
        self.temp_min = _numero(self.temp_min, "temperatura mínima")
        self.temp_max = _numero(self.temp_max, "temperatura máxima")
        if self.temp_min >= self.temp_max:
            raise ValidacionError("La temperatura mínima debe ser menor que la máxima.")
        capacidad = _numero(self.capacidad, "capacidad", positivo=True)
        self.capacidad = int(capacidad)

    def apta_para(self, tipo: TipoAnalisis) -> bool:
        """La conservadora sirve si su rango térmico garantizado cae dentro del exigido por el análisis."""
        return tipo.temp_min <= self.temp_min and self.temp_max <= tipo.temp_max


@dataclass
class Remito:
    """Remito biológico: documento que acompaña a la conservadora en todo su recorrido."""
    numero: str
    clinica_id: int
    laboratorio_id: int
    contenedor_id: int
    fecha_emision: str
    responsable: str
    estado: str = "EMITIDO"
    id: Optional[int] = None

    TRANSICIONES = {
        "EMITIDO": {"EN_TRANSITO"},
        "EN_TRANSITO": {"RECIBIDO", "RECHAZADO"},
        "RECIBIDO": set(),
        "RECHAZADO": set(),
    }

    def __post_init__(self):
        _requerido(self.responsable, "responsable del empaquetado")
        self.fecha_emision = normalizar(self.fecha_emision)

    def cambiar_estado(self, nuevo: str):
        if nuevo not in self.TRANSICIONES[self.estado]:
            raise TransicionInvalidaError(
                f"El remito {self.numero} está {self.estado} y no puede pasar a {nuevo}.")
        self.estado = nuevo


@dataclass
class Precinto:
    """Precinto sanitario colocado al cerrar la conservadora."""
    codigo: str
    remito_id: int
    fecha_colocacion: str
    estado: str = "COLOCADO"
    fecha_verificacion: Optional[str] = None
    observacion: str = ""
    id: Optional[int] = None

    def verificar(self, intacto: bool, fecha_hora: str, observacion: str = ""):
        if self.estado != "COLOCADO":
            raise TransicionInvalidaError(f"El precinto {self.codigo} ya fue verificado ({self.estado}).")
        self.estado = "INTACTO" if intacto else "ROTO"
        self.fecha_verificacion = normalizar(fecha_hora)
        self.observacion = observacion


@dataclass
class HistorialEstado:
    muestra_id: int
    estado_nuevo: str
    fecha_hora: str
    estado_anterior: Optional[str] = None
    detalle: str = ""
    id: Optional[int] = None


@dataclass
class Envio:
    remito_id: int
    transportista: str
    fecha_salida: str
    vehiculo: str = ""
    fecha_llegada: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.transportista, "transportista")


@dataclass
class EventoEnvio:
    """Un eslabón de la cadena de envío (salida, punto de control intermedio o llegada)."""
    envio_id: int
    fecha_hora: str
    tipo: str
    ubicacion: str
    temperatura: float
    responsable: str = ""
    observacion: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        self.fecha_hora = normalizar(self.fecha_hora)
        _requerido(self.ubicacion, "ubicación")
        self.temperatura = _numero(self.temperatura, "temperatura")


@dataclass
class Recepcion:
    remito_id: int
    fecha_hora: str
    recibido_por: str
    estado_precinto: str
    temperatura_llegada: float
    muestras_aceptadas: int = 0
    muestras_rechazadas: int = 0
    observaciones: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.recibido_por, "recibido por")


@dataclass
class Resultado:
    muestra_id: int
    fecha_hora: str
    profesional: str
    valores: str
    conclusion: str
    observaciones: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        _requerido(self.profesional, "profesional")
        _requerido(self.valores, "valores obtenidos")
        _requerido(self.conclusion, "conclusión")


@dataclass
class Comprobante:
    numero: str
    consulta_id: int
    cliente_id: int
    clinica_id: int
    fecha_hora: str
    total: float
    id: Optional[int] = None


@dataclass
class ItemComprobante:
    comprobante_id: int
    tipo_servicio: str
    descripcion: str
    cantidad: int
    precio_unitario: float
    subtotal: float
    id: Optional[int] = None


@dataclass
class Notificacion:
    fecha_hora: str
    tipo: str
    destinatario: str
    mensaje: str
    cliente_id: Optional[int] = None
    mascota_id: Optional[int] = None
    enviada: bool = False
    id: Optional[int] = None


def fecha_no_anterior(fecha_hora: str, referencia: str, que: str, respecto: str):
    """Valida el orden cronológico de los eventos de la trazabilidad."""
    if parse_fecha_hora(fecha_hora) < parse_fecha_hora(referencia):
        raise ValidacionError(f"La fecha de {que} ({fecha_hora}) no puede ser anterior a {respecto} ({referencia}).")
