"""Datos maestros: clínicas, veterinarios, laboratorio, tipos de vacuna/análisis y conservadoras."""
from veterinaria.dominio.entidades import Contenedor
from veterinaria.excepciones import EntidadNoEncontradaError, ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r


class CatalogoService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()

    def clinicas(self):
        return r.RepoClinica(self.bd).listar(orden="nombre")

    def laboratorio_central(self):
        laboratorio = r.RepoLaboratorio(self.bd).buscar_uno("1 = 1")
        if laboratorio is None:
            raise EntidadNoEncontradaError("No hay un laboratorio central configurado.")
        return laboratorio

    def veterinarios(self, clinica_id=None):
        if clinica_id:
            return r.RepoVeterinario(self.bd).listar("activo = 1 AND clinica_id = ?", (clinica_id,), "apellido")
        return r.RepoVeterinario(self.bd).listar("activo = 1", orden="apellido")

    def tipos_analisis(self):
        return r.RepoTipoAnalisis(self.bd).listar(orden="nombre")

    def tipos_vacuna(self):
        return r.RepoTipoVacuna(self.bd).listar(orden="especie, nombre")

    def contenedores(self, clinica_id=None, solo_disponibles=False):
        condiciones, parametros = ["estado <> 'BAJA'"], []
        if clinica_id:
            condiciones.append("clinica_id = ?")
            parametros.append(clinica_id)
        if solo_disponibles:
            condiciones.append("estado = 'DISPONIBLE'")
        return r.RepoContenedor(self.bd).listar(" AND ".join(condiciones), parametros, "codigo")

    def alta_contenedor(self, codigo, clinica_id, temp_min, temp_max, capacidad, descripcion="") -> Contenedor:
        repo = r.RepoContenedor(self.bd)
        contenedor = Contenedor(codigo=codigo.strip().upper(), clinica_id=clinica_id, temp_min=temp_min,
                                temp_max=temp_max, capacidad=capacidad, descripcion=descripcion)
        r.RepoClinica(self.bd).obtener_o_error(clinica_id)
        if repo.buscar_uno("codigo = ?", (contenedor.codigo,)):
            raise ValidacionError(f"Ya existe una conservadora con código {contenedor.codigo}.")
        return repo.insertar(contenedor)
