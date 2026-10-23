from dataclasses import replace

from veterinaria.dominio.entidades import Mascota
from veterinaria.dominio.muestra import ETIQUETAS_ESTADO
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia.repositorios import RepoCliente, RepoMascota
from veterinaria.servicios.vacunas import VacunaService


class MascotaService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = RepoMascota(self.bd)
        self.repo_clientes = RepoCliente(self.bd)

    def _validar_responsable(self, cliente_id):
        cliente = self.repo_clientes.obtener(cliente_id) if cliente_id else None
        if cliente is None or not cliente.activo:
            raise ValidacionError("Toda mascota debe tener un responsable activo asociado.")

    def alta(self, nombre, especie, fecha_nacimiento, cliente_id, raza="", sexo="M", peso=None) -> Mascota:
        mascota = Mascota(nombre=nombre.strip(), especie=especie, fecha_nacimiento=fecha_nacimiento,
                          cliente_id=cliente_id, raza=raza, sexo=sexo, peso=peso)
        self._validar_responsable(mascota.cliente_id)
        return self.repo.insertar(mascota)

    def modificar(self, mascota_id, **datos) -> Mascota:
        mascota = replace(self.repo.obtener_o_error(mascota_id), **datos)
        self._validar_responsable(mascota.cliente_id)
        return self.repo.actualizar(mascota)

    def baja(self, mascota_id):
        mascota = self.repo.obtener_o_error(mascota_id)
        mascota.activo = False
        self.repo.actualizar(mascota)

    def obtener(self, mascota_id) -> Mascota:
        return self.repo.obtener_o_error(mascota_id)

    def listar(self, filtro="", cliente_id=None):
        condicion = "m.activo = 1 AND (m.nombre LIKE ? OR c.apellido LIKE ? OR c.dni LIKE ?)"
        patron = f"%{filtro.strip()}%"
        parametros = [patron, patron, patron]
        if cliente_id:
            condicion += " AND m.cliente_id = ?"
            parametros.append(cliente_id)
        return self.bd.consultar(f"""
            SELECT m.*, c.apellido || ', ' || c.nombre AS responsable, c.dni
            FROM mascota m JOIN cliente c ON c.id = m.cliente_id
            WHERE {condicion} ORDER BY m.nombre""", parametros)

    def historia_clinica(self, mascota_id) -> dict:
        mascota = self.obtener(mascota_id)
        cliente = self.repo_clientes.obtener(mascota.cliente_id)
        consultas = self.bd.consultar("""
            SELECT co.*, v.apellido || ', ' || v.nombre AS veterinario, cl.nombre AS clinica
            FROM consulta co
            JOIN veterinario v ON v.id = co.veterinario_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE co.mascota_id = ? ORDER BY co.fecha_hora DESC""", (mascota_id,))
        for consulta in consultas:
            consulta["vacunas"] = self.bd.consultar("""
                SELECT tv.nombre, va.lote FROM vacuna_aplicada va
                JOIN tipo_vacuna tv ON tv.id = va.tipo_vacuna_id WHERE va.consulta_id = ?""", (consulta["id"],))
            consulta["muestras"] = self.bd.consultar("""
                SELECT mu.codigo, mu.estado, mu.motivo_rechazo, ta.nombre AS analisis,
                       r.conclusion, r.valores
                FROM muestra mu
                JOIN orden_derivacion o ON o.id = mu.orden_id
                JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
                LEFT JOIN resultado r ON r.muestra_id = mu.id
                WHERE o.consulta_id = ? ORDER BY mu.id""", (consulta["id"],))
            for m in consulta["muestras"]:
                m["estado"] = ETIQUETAS_ESTADO[m["estado"]]
        return {
            "mascota": mascota,
            "cliente": cliente,
            "consultas": consultas,
            "esquema_vacunas": VacunaService(self.bd).estado_esquema(mascota),
        }
