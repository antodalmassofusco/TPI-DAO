"""Emisión de comprobantes de atención (consulta + vacunas + análisis de laboratorio)."""
from veterinaria.dominio.entidades import Comprobante, ItemComprobante
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r
from veterinaria.utils.fechas import ahora, normalizar
from veterinaria.utils.formato import numero


class ComprobanteService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo = r.RepoComprobante(self.bd)

    def emitir(self, consulta_id, fecha_hora=None) -> Comprobante:
        fecha_hora = normalizar(fecha_hora or ahora())
        consulta = r.RepoConsulta(self.bd).obtener_o_error(consulta_id)
        if self.repo.buscar_uno("consulta_id = ?", (consulta.id,)):
            raise ValidacionError("La atención ya tiene un comprobante emitido.")
        pendientes = self.bd.consultar("""
            SELECT mu.codigo FROM muestra mu JOIN orden_derivacion o ON o.id = mu.orden_id
            WHERE o.consulta_id = ? AND mu.estado NOT IN ('ANALIZADA', 'RECHAZADA')""", (consulta.id,))
        if pendientes:
            codigos = ", ".join(p["codigo"] for p in pendientes)
            raise ValidacionError(f"No se puede emitir el comprobante: hay muestras sin resultado ({codigos}).")

        items = [("CONSULTA", f"Atención clínica ({consulta.tipo.lower()})", 1, consulta.precio)]
        for v in self.bd.consultar("""
                SELECT tv.nombre, va.precio FROM vacuna_aplicada va
                JOIN tipo_vacuna tv ON tv.id = va.tipo_vacuna_id WHERE va.consulta_id = ?""", (consulta.id,)):
            items.append(("VACUNA", f"Vacuna {v['nombre']}", 1, v["precio"]))
        # Sólo se facturan los análisis efectivamente realizados (no las muestras rechazadas)
        for a in self.bd.consultar("""
                SELECT ta.nombre, ta.precio, mu.codigo FROM muestra mu
                JOIN orden_derivacion o ON o.id = mu.orden_id
                JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
                WHERE o.consulta_id = ? AND mu.estado = 'ANALIZADA'""", (consulta.id,)):
            items.append(("LABORATORIO", f"Análisis {a['nombre']} ({a['codigo']})", 1, a["precio"]))

        cliente_id = self.bd.escalar("SELECT cliente_id FROM mascota WHERE id = ?", (consulta.mascota_id,))
        with self.bd.transaccion():
            comprobante = self.repo.insertar(Comprobante(
                numero=self.bd.siguiente_numero("comprobante", "0001-", 8), consulta_id=consulta.id,
                cliente_id=cliente_id, clinica_id=consulta.clinica_id, fecha_hora=fecha_hora,
                total=sum(cant * precio for _, _, cant, precio in items)))
            repo_items = r.RepoItemComprobante(self.bd)
            for tipo, descripcion, cantidad, precio in items:
                repo_items.insertar(ItemComprobante(
                    comprobante_id=comprobante.id, tipo_servicio=tipo, descripcion=descripcion,
                    cantidad=cantidad, precio_unitario=precio, subtotal=cantidad * precio))
        return comprobante

    def listar(self):
        return self.bd.consultar("""
            SELECT cp.*, c.apellido || ', ' || c.nombre AS cliente, cl.nombre AS clinica, m.nombre AS mascota
            FROM comprobante cp
            JOIN cliente c ON c.id = cp.cliente_id
            JOIN clinica cl ON cl.id = cp.clinica_id
            JOIN consulta co ON co.id = cp.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            ORDER BY cp.fecha_hora DESC""")

    def consultas_sin_comprobante(self):
        return self.bd.consultar("""
            SELECT co.id, co.fecha_hora, co.tipo, m.nombre AS mascota, cl.nombre AS clinica,
                   (SELECT COUNT(*) FROM muestra mu JOIN orden_derivacion o ON o.id = mu.orden_id
                    WHERE o.consulta_id = co.id AND mu.estado NOT IN ('ANALIZADA', 'RECHAZADA')) AS muestras_pendientes
            FROM consulta co
            JOIN mascota m ON m.id = co.mascota_id
            JOIN clinica cl ON cl.id = co.clinica_id
            WHERE NOT EXISTS (SELECT 1 FROM comprobante cp WHERE cp.consulta_id = co.id)
            ORDER BY co.fecha_hora DESC""")

    def detalle(self, comprobante_id) -> dict:
        cp = self.bd.consultar_uno("""
            SELECT cp.*, c.apellido || ', ' || c.nombre AS cliente, c.dni, cl.nombre AS clinica,
                   cl.direccion, m.nombre AS mascota, m.especie,
                   v.apellido || ', ' || v.nombre AS veterinario, co.fecha_hora AS fecha_atencion
            FROM comprobante cp
            JOIN cliente c ON c.id = cp.cliente_id
            JOIN clinica cl ON cl.id = cp.clinica_id
            JOIN consulta co ON co.id = cp.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            JOIN veterinario v ON v.id = co.veterinario_id
            WHERE cp.id = ?""", (comprobante_id,))
        if cp is None:
            raise ValidacionError("Comprobante inexistente.")
        cp["items"] = self.bd.consultar(
            "SELECT * FROM item_comprobante WHERE comprobante_id = ? ORDER BY id", (comprobante_id,))
        return cp

    def texto(self, comprobante_id) -> str:
        cp = self.detalle(comprobante_id)
        ancho = 64
        lineas = [
            "=" * ancho,
            f"{cp['clinica'].upper():^{ancho}}",
            f"{cp['direccion']:^{ancho}}",
            "=" * ancho,
            f"COMPROBANTE DE ATENCIÓN N° {cp['numero']}",
            f"Fecha de emisión: {cp['fecha_hora']}",
            f"Cliente: {cp['cliente']} (DNI {cp['dni']})",
            f"Paciente: {cp['mascota']} ({cp['especie']})",
            f"Atendido por: {cp['veterinario']} el {cp['fecha_atencion']}",
            "-" * ancho,
            f"{'Concepto':<44}{'Cant.':>6}{'Subtotal':>14}",
            "-" * ancho,
        ]
        for it in cp["items"]:
            lineas.append(f"{it['descripcion'][:44]:<44}{it['cantidad']:>6}{numero(it['subtotal']):>14}")
        lineas += ["-" * ancho, f"{'TOTAL $':<50}{numero(cp['total']):>14}", "=" * ancho]
        return "\n".join(lineas)
