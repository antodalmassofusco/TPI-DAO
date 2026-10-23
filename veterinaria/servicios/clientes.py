from dataclasses import replace

from veterinaria.dominio.entidades import Cliente
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia.repositorios import RepoCliente


class ClienteService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = RepoCliente(self.bd)

    def _validar_dni_unico(self, dni, id_actual=None):
        existente = self.repo.buscar_uno("dni = ?", (dni,))
        if existente and existente.id != id_actual:
            raise ValidacionError(f"Ya existe un cliente con DNI {dni} ({existente.nombre_completo}).")

    def alta(self, dni, nombre, apellido, telefono="", email="", direccion="") -> Cliente:
        cliente = Cliente(dni=dni, nombre=nombre.strip(), apellido=apellido.strip(),
                          telefono=telefono, email=email, direccion=direccion)
        self._validar_dni_unico(cliente.dni)
        return self.repo.insertar(cliente)

    def modificar(self, cliente_id, **datos) -> Cliente:
        cliente = replace(self.repo.obtener_o_error(cliente_id), **datos)
        self._validar_dni_unico(cliente.dni, cliente.id)
        return self.repo.actualizar(cliente)

    def baja(self, cliente_id):
        cliente = self.repo.obtener_o_error(cliente_id)
        activas = self.bd.escalar(
            "SELECT COUNT(*) FROM mascota WHERE cliente_id = ? AND activo = 1", (cliente_id,))
        if activas:
            raise ValidacionError(
                f"No se puede dar de baja a {cliente.nombre_completo}: es responsable de {activas} mascota(s) activa(s). "
                "Reasígnelas o déles de baja primero.")
        cliente.activo = False
        self.repo.actualizar(cliente)

    def obtener(self, cliente_id) -> Cliente:
        return self.repo.obtener_o_error(cliente_id)

    def listar(self, filtro="", incluir_inactivos=False):
        condicion = "(dni LIKE ? OR nombre LIKE ? OR apellido LIKE ?)"
        patron = f"%{filtro.strip()}%"
        parametros = [patron, patron, patron]
        if not incluir_inactivos:
            condicion += " AND activo = 1"
        return self.bd.consultar(f"""
            SELECT c.*, (SELECT COUNT(*) FROM mascota m WHERE m.cliente_id = c.id AND m.activo = 1) AS mascotas
            FROM cliente c WHERE {condicion} ORDER BY apellido, nombre""", parametros)
