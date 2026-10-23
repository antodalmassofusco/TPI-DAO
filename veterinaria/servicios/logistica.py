"""Cadena de custodia: empaquetado, envío y recepción de muestras en el laboratorio central."""
from veterinaria.dominio.entidades import (Envio, EventoEnvio, Precinto, Recepcion, Remito,
                                           fecha_no_anterior)
from veterinaria.dominio.muestra import ETIQUETAS_ESTADO, Muestra
from veterinaria.excepciones import ValidacionError
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.persistencia import repositorios as r
from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.observadores import AvisoAlCliente, RegistroTrazabilidad
from veterinaria.utils.fechas import ahora, horas_entre, normalizar

MOTIVO_PRECINTO = "Precinto sanitario roto: cadena de custodia comprometida"


class LogisticaService:
    def __init__(self, bd=None):
        self.bd = bd or BaseDatos()
        self.repo_remitos = r.RepoRemito(self.bd)
        self.repo_muestras = r.RepoMuestra(self.bd)
        self.repo_contenedores = r.RepoContenedor(self.bd)
        self.repo_envios = r.RepoEnvio(self.bd)
        self.repo_eventos = r.RepoEventoEnvio(self.bd)

    def _con_observadores(self, muestra: Muestra) -> Muestra:
        muestra.agregar_observador(RegistroTrazabilidad(self.bd))
        muestra.agregar_observador(AvisoAlCliente(self.bd))
        return muestra

    def _muestras_de_remito(self, remito_id):
        return [self._con_observadores(m) for m in self.repo_muestras.listar("remito_id = ?", (remito_id,))]

    def _clinica_de_muestra(self, muestra_id):
        return self.bd.escalar("""
            SELECT co.clinica_id FROM muestra mu
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id WHERE mu.id = ?""", (muestra_id,))

    def _envio_de(self, remito_id) -> Envio:
        envio = self.repo_envios.buscar_uno("remito_id = ?", (remito_id,))
        if envio is None:
            raise ValidacionError("El remito todavía no fue despachado.")
        return envio

    def _ultimo_evento(self, envio_id):
        return self.bd.escalar("SELECT MAX(fecha_hora) FROM evento_envio WHERE envio_id = ?", (envio_id,))

    # ------------------------------------------------------------------ 4. Empaquetado
    def empaquetar(self, contenedor_id, muestra_ids, responsable, fecha_hora=None):
        """Coloca las muestras en una conservadora, emite el remito biológico y el precinto sanitario."""
        fecha_hora = normalizar(fecha_hora or ahora())
        if not muestra_ids:
            raise ValidacionError("Seleccione al menos una muestra para empaquetar.")
        if not contenedor_id:
            raise ValidacionError("Seleccione la conservadora isotérmica.")
        contenedor = self.repo_contenedores.obtener_o_error(contenedor_id)
        if contenedor.estado != "DISPONIBLE":
            raise ValidacionError(f"La conservadora {contenedor.codigo} no está disponible ({contenedor.estado}).")
        if len(muestra_ids) > contenedor.capacidad:
            raise ValidacionError(
                f"La conservadora {contenedor.codigo} admite hasta {contenedor.capacidad} muestras.")

        repo_tipos = r.RepoTipoAnalisis(self.bd)
        muestras = []
        for muestra_id in muestra_ids:
            muestra = self._con_observadores(self.repo_muestras.obtener_o_error(muestra_id))
            tipo = repo_tipos.obtener(muestra.tipo_analisis_id)
            if muestra.estado != "EXTRAIDA":
                raise ValidacionError(
                    f"La muestra {muestra.codigo} está '{ETIQUETAS_ESTADO[muestra.estado]}' y no puede empaquetarse.")
            if self._clinica_de_muestra(muestra.id) != contenedor.clinica_id:
                raise ValidacionError(f"La muestra {muestra.codigo} no pertenece a la clínica de la conservadora.")
            if not contenedor.apta_para(tipo):
                raise ValidacionError(
                    f"La conservadora {contenedor.codigo} ({contenedor.temp_min:g} a {contenedor.temp_max:g} °C) "
                    f"no es apta para {tipo.nombre}, que requiere {tipo.temp_min:g} a {tipo.temp_max:g} °C.")
            fecha_no_anterior(fecha_hora, muestra.fecha_extraccion, "empaquetado", "la extracción")
            if horas_entre(muestra.fecha_extraccion, fecha_hora) > tipo.horas_viabilidad:
                raise ValidacionError(
                    f"La muestra {muestra.codigo} superó su ventana de viabilidad ({tipo.horas_viabilidad} h).")
            muestras.append(muestra)

        laboratorio = CatalogoService(self.bd).laboratorio_central()
        with self.bd.transaccion():
            remito = self.repo_remitos.insertar(Remito(
                numero=self.bd.siguiente_numero("remito", "RB-"), clinica_id=contenedor.clinica_id,
                laboratorio_id=laboratorio.id, contenedor_id=contenedor.id,
                fecha_emision=fecha_hora, responsable=responsable))
            precinto = r.RepoPrecinto(self.bd).insertar(Precinto(
                codigo=self.bd.siguiente_numero("precinto", "PS-"), remito_id=remito.id,
                fecha_colocacion=fecha_hora))
            for muestra in muestras:
                muestra.empaquetar(remito.id, fecha_hora)
                self.repo_muestras.actualizar(muestra)
            contenedor.estado = "EN_USO"
            self.repo_contenedores.actualizar(contenedor)
        return remito, precinto

    def descartar_vencidas(self, clinica_id, fecha_hora=None) -> list:
        """Rechaza las muestras extraídas que superaron su ventana de viabilidad sin ser enviadas."""
        fecha_hora = normalizar(fecha_hora or ahora())
        repo_tipos = r.RepoTipoAnalisis(self.bd)
        descartadas = []
        with self.bd.transaccion():
            for fila in self.muestras_para_empaquetar(clinica_id):
                muestra = self._con_observadores(self.repo_muestras.obtener(fila["id"]))
                tipo = repo_tipos.obtener(muestra.tipo_analisis_id)
                horas = horas_entre(muestra.fecha_extraccion, fecha_hora)
                if horas > tipo.horas_viabilidad:
                    muestra.rechazar(f"Muestra no viable: descartada en clínica tras {horas:.0f} h sin envío "
                                     f"(máximo {tipo.horas_viabilidad} h)", fecha_hora)
                    self.repo_muestras.actualizar(muestra)
                    descartadas.append(muestra)
        return descartadas

    # ------------------------------------------------------------------ 5. Cadena de envío
    def despachar(self, remito_id, transportista, temperatura_salida, vehiculo="", fecha_hora=None):
        fecha_hora = normalizar(fecha_hora or ahora())
        remito = self.repo_remitos.obtener_o_error(remito_id)
        fecha_no_anterior(fecha_hora, remito.fecha_emision, "salida", "la emisión del remito")
        clinica = r.RepoClinica(self.bd).obtener(remito.clinica_id)
        with self.bd.transaccion():
            remito.cambiar_estado("EN_TRANSITO")
            self.repo_remitos.actualizar(remito)
            envio = self.repo_envios.insertar(Envio(
                remito_id=remito.id, transportista=transportista, vehiculo=vehiculo, fecha_salida=fecha_hora))
            self.repo_eventos.insertar(EventoEnvio(
                envio_id=envio.id, fecha_hora=fecha_hora, tipo="SALIDA", ubicacion=clinica.nombre,
                temperatura=temperatura_salida, responsable=transportista,
                observacion=f"Retiro de conservadora con remito {remito.numero}"))
            for muestra in self._muestras_de_remito(remito.id):
                muestra.despachar(fecha_hora, f"Despachada con {transportista} (remito {remito.numero})")
                self.repo_muestras.actualizar(muestra)
        return envio

    def registrar_punto_control(self, remito_id, ubicacion, temperatura, responsable="", observacion="",
                                fecha_hora=None) -> EventoEnvio:
        fecha_hora = normalizar(fecha_hora or ahora())
        remito = self.repo_remitos.obtener_o_error(remito_id)
        if remito.estado != "EN_TRANSITO":
            raise ValidacionError(f"El remito {remito.numero} no está en tránsito.")
        envio = self._envio_de(remito.id)
        fecha_no_anterior(fecha_hora, self._ultimo_evento(envio.id), "el control", "el evento anterior")
        return self.repo_eventos.insertar(EventoEnvio(
            envio_id=envio.id, fecha_hora=fecha_hora, tipo="PUNTO_CONTROL", ubicacion=ubicacion,
            temperatura=temperatura, responsable=responsable, observacion=observacion))

    # ------------------------------------------------------------------ 6. Recepción
    def recibir(self, remito_id, recibido_por, precinto_intacto: bool, temperatura_llegada,
                observaciones="", fecha_hora=None):
        """Verifica precinto, temperatura y viabilidad de cada muestra.

        Si el precinto llegó roto se rechazan todas las muestras del remito (Muestra Rechazada).
        Devuelve (recepcion, [(muestra, motivo_rechazo | None), ...]).
        """
        fecha_hora = normalizar(fecha_hora or ahora())
        remito = self.repo_remitos.obtener_o_error(remito_id)
        if remito.estado != "EN_TRANSITO":
            raise ValidacionError(f"El remito {remito.numero} no está en tránsito ({remito.estado}).")
        envio = self._envio_de(remito.id)
        fecha_no_anterior(fecha_hora, self._ultimo_evento(envio.id), "recepción", "el último evento del envío")
        laboratorio = r.RepoLaboratorio(self.bd).obtener(remito.laboratorio_id)
        repo_tipos = r.RepoTipoAnalisis(self.bd)
        repo_precintos = r.RepoPrecinto(self.bd)

        with self.bd.transaccion():
            llegada = self.repo_eventos.insertar(EventoEnvio(
                envio_id=envio.id, fecha_hora=fecha_hora, tipo="LLEGADA", ubicacion=laboratorio.nombre,
                temperatura=temperatura_llegada, responsable=recibido_por,
                observacion="Precinto intacto" if precinto_intacto else "PRECINTO ROTO"))
            envio.fecha_llegada = fecha_hora
            self.repo_envios.actualizar(envio)

            precinto = repo_precintos.buscar_uno("remito_id = ?", (remito.id,))
            precinto.verificar(precinto_intacto, fecha_hora, observaciones)
            repo_precintos.actualizar(precinto)

            temperaturas = [ev.temperatura for ev in self.repo_eventos.listar("envio_id = ?", (envio.id,))]
            resultado = []
            for muestra in self._muestras_de_remito(remito.id):
                tipo = repo_tipos.obtener(muestra.tipo_analisis_id)
                motivo = self._motivo_rechazo(precinto_intacto, temperaturas, tipo, muestra, fecha_hora)
                if motivo:
                    muestra.rechazar(motivo, fecha_hora)
                else:
                    muestra.recibir(fecha_hora, f"Recibida por {recibido_por}: precinto intacto, muestra viable")
                self.repo_muestras.actualizar(muestra)
                resultado.append((muestra, motivo))

            rechazadas = sum(1 for _, motivo in resultado if motivo)
            remito.cambiar_estado("RECHAZADO" if not precinto_intacto or rechazadas == len(resultado)
                                  else "RECIBIDO")
            self.repo_remitos.actualizar(remito)

            contenedor = self.repo_contenedores.obtener(remito.contenedor_id)
            contenedor.estado = "DISPONIBLE"
            self.repo_contenedores.actualizar(contenedor)

            recepcion = r.RepoRecepcion(self.bd).insertar(Recepcion(
                remito_id=remito.id, fecha_hora=fecha_hora, recibido_por=recibido_por,
                estado_precinto=precinto.estado, temperatura_llegada=llegada.temperatura,
                muestras_aceptadas=len(resultado) - rechazadas, muestras_rechazadas=rechazadas,
                observaciones=observaciones))
        return recepcion, resultado

    @staticmethod
    def _motivo_rechazo(precinto_intacto, temperaturas, tipo, muestra, fecha_hora):
        if not precinto_intacto:
            return MOTIVO_PRECINTO
        fuera_de_rango = [t for t in temperaturas if not tipo.temperatura_admisible(t)]
        if fuera_de_rango:
            peor = max(fuera_de_rango, key=lambda t: max(tipo.temp_min - t, t - tipo.temp_max))
            return (f"Ruptura de cadena de frío: se registró {peor:g} °C "
                    f"(admisible {tipo.temp_min:g} a {tipo.temp_max:g} °C)")
        horas = horas_entre(muestra.fecha_extraccion, fecha_hora)
        if horas > tipo.horas_viabilidad:
            return f"Muestra no viable: {horas:.1f} h desde la extracción (máximo {tipo.horas_viabilidad} h)"
        return None

    # ------------------------------------------------------------------ Consultas
    def muestras_para_empaquetar(self, clinica_id):
        return self.bd.consultar("""
            SELECT mu.id, mu.codigo, mu.fecha_extraccion, ta.nombre AS analisis, ta.tipo_muestra,
                   ta.temp_min, ta.temp_max, m.nombre AS mascota, o.prioridad
            FROM muestra mu
            JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            WHERE mu.estado = 'EXTRAIDA' AND co.clinica_id = ?
            ORDER BY o.prioridad DESC, mu.fecha_extraccion""", (clinica_id,))

    def listar_remitos(self, estados=None, remito_id=None):
        condiciones, parametros = ["1 = 1"], []
        if estados:
            condiciones.append(f"re.estado IN ({', '.join('?' for _ in estados)})")
            parametros += list(estados)
        if remito_id:
            condiciones.append("re.id = ?")
            parametros.append(remito_id)
        condicion = "WHERE " + " AND ".join(condiciones)
        return self.bd.consultar(f"""
            SELECT re.*, cl.nombre AS clinica, ct.codigo AS contenedor, ct.temp_min, ct.temp_max,
                   p.codigo AS precinto, p.estado AS estado_precinto, e.transportista, e.vehiculo,
                   (SELECT COUNT(*) FROM muestra mu WHERE mu.remito_id = re.id) AS muestras
            FROM remito re
            JOIN clinica cl ON cl.id = re.clinica_id
            JOIN contenedor ct ON ct.id = re.contenedor_id
            JOIN precinto p ON p.remito_id = re.id
            LEFT JOIN envio e ON e.remito_id = re.id
            {condicion} ORDER BY re.fecha_emision DESC""", parametros)

    def eventos_de_remito(self, remito_id):
        return self.bd.consultar("""
            SELECT ev.* FROM evento_envio ev JOIN envio e ON e.id = ev.envio_id
            WHERE e.remito_id = ? ORDER BY ev.fecha_hora, ev.id""", (remito_id,))

    def muestras_de_remito(self, remito_id):
        filas = self.bd.consultar("""
            SELECT mu.codigo, mu.estado, mu.motivo_rechazo, ta.nombre AS analisis, m.nombre AS mascota
            FROM muestra mu JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
            JOIN orden_derivacion o ON o.id = mu.orden_id
            JOIN consulta co ON co.id = o.consulta_id
            JOIN mascota m ON m.id = co.mascota_id
            WHERE mu.remito_id = ? ORDER BY mu.id""", (remito_id,))
        for f in filas:
            f["estado_clave"], f["estado"] = f["estado"], ETIQUETAS_ESTADO[f["estado"]]
        return filas
