"""Control del esquema de vacunación obligatorio."""
from veterinaria.dominio.entidades import Mascota, TipoVacuna
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia.repositorios import RepoTipoVacuna
from veterinaria.utils.fechas import hoy, meses_entre, parse_fecha, sumar_meses

AL_DIA, PENDIENTE, VENCIDA, NO_CORRESPONDE = "Al día", "Pendiente", "Vencida", "Aún no corresponde"


class VacunaService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo_tipos = RepoTipoVacuna(self.bd)

    def tipos_para_especie(self, especie) -> list[TipoVacuna]:
        return self.repo_tipos.listar("especie = ?", (especie,), orden="obligatoria DESC, nombre")

    def ultima_aplicacion(self, mascota_id, tipo_vacuna_id, antes_de=None):
        sql = "SELECT MAX(fecha) FROM vacuna_aplicada WHERE mascota_id = ? AND tipo_vacuna_id = ?"
        parametros = [mascota_id, tipo_vacuna_id]
        if antes_de:
            sql += " AND fecha <= ?"
            parametros.append(antes_de)
        valor = self.bd.escalar(sql, parametros)
        return parse_fecha(valor) if valor else None

    def estado_esquema(self, mascota: Mascota, referencia=None) -> list[dict]:
        """Situación de cada vacuna de la especie para la mascota en una fecha dada."""
        referencia = parse_fecha(referencia or hoy())
        edad = mascota.edad_meses(referencia)
        filas = []
        for tipo in self.tipos_para_especie(mascota.especie):
            ultima = self.ultima_aplicacion(mascota.id, tipo.id, f"{referencia.isoformat()} 23:59")
            if ultima is None:
                proxima = sumar_meses(parse_fecha(mascota.fecha_nacimiento), tipo.edad_minima_meses)
                estado = PENDIENTE if edad >= tipo.edad_minima_meses else NO_CORRESPONDE
            elif tipo.intervalo_refuerzo_meses:
                proxima = sumar_meses(ultima, tipo.intervalo_refuerzo_meses)
                estado = VENCIDA if proxima <= referencia else AL_DIA
            else:
                proxima, estado = None, AL_DIA
            filas.append({"tipo": tipo, "ultima": ultima, "proxima": proxima, "estado": estado})
        return filas

    def pendientes(self, mascota: Mascota, referencia=None) -> list[dict]:
        return [f for f in self.estado_esquema(mascota, referencia)
                if f["tipo"].obligatoria and f["estado"] in (PENDIENTE, VENCIDA)]

    def validar_aplicacion(self, mascota: Mascota, tipo: TipoVacuna, fecha):
        fecha = parse_fecha(fecha)
        if tipo.especie != mascota.especie:
            raise ValidacionError(f"La vacuna {tipo.nombre} es para {tipo.especie}, no para {mascota.especie}.")
        edad = mascota.edad_meses(fecha)
        if edad < tipo.edad_minima_meses:
            raise ValidacionError(
                f"{mascota.nombre} tiene {edad} meses; la vacuna {tipo.nombre} se aplica desde los "
                f"{tipo.edad_minima_meses} meses.")
        ultima = self.ultima_aplicacion(mascota.id, tipo.id, f"{fecha.isoformat()} 23:59")
        if ultima is None:
            return
        if not tipo.intervalo_refuerzo_meses:
            raise ValidacionError(f"La vacuna {tipo.nombre} es de dosis única y ya fue aplicada el {ultima}.")
        # Se tolera adelantar el refuerzo hasta un mes
        if meses_entre(ultima, fecha) < tipo.intervalo_refuerzo_meses - 1:
            proxima = sumar_meses(ultima, tipo.intervalo_refuerzo_meses)
            raise ValidacionError(
                f"Refuerzo prematuro de {tipo.nombre}: última dosis el {ultima}, corresponde a partir de {proxima}.")
