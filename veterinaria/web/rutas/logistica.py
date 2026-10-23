"""Procesos 4, 5 y 6: empaquetado, cadena de envío y recepción en el laboratorio central."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.logistica import LogisticaService
from veterinaria.utils.fechas import ahora
from veterinaria.web.util import validar

bp = Blueprint("logistica", __name__, url_prefix="/logistica")
FILTROS_REMITO = {"EMITIDO": "Por despachar", "EN_TRANSITO": "En tránsito", "RECIBIDO": "Recibidos",
                  "RECHAZADO": "Rechazados", "": "Todos"}


# ------------------------------------------------------------------ 4. Empaquetado
@bp.get("/empaquetado")
def empaquetado(datos=None):
    catalogo, servicio = CatalogoService(), LogisticaService()
    clinicas = catalogo.clinicas()
    pendientes = {c.id: len(servicio.muestras_para_empaquetar(c.id)) for c in clinicas}
    # por defecto, la primera clínica que tenga muestras esperando
    clinica_id = (request.values.get("clinica", type=int)
                  or next((c.id for c in clinicas if pendientes[c.id]), clinicas[0].id))
    return render_template("empaquetado.html", clinicas=clinicas, clinica_id=clinica_id, pendientes=pendientes,
                           muestras=servicio.muestras_para_empaquetar(clinica_id),
                           contenedores=catalogo.contenedores(clinica_id, solo_disponibles=True),
                           marcadas=[int(m) for m in request.form.getlist("muestras")],
                           datos=datos or {"fecha_hora": ahora()})


@bp.post("/empaquetado")
@validar(empaquetado)
def empaquetar():
    f = request.form
    remito, precinto = LogisticaService().empaquetar(
        f.get("contenedor_id", type=int), [int(m) for m in f.getlist("muestras")], f.get("responsable", ""),
        f.get("fecha_hora"))
    flash(f"Remito biológico {remito.numero} emitido y precinto sanitario {precinto.codigo} colocado. "
          "Las muestras quedaron en estado 'Empaquetada'.", "success")
    return redirect(url_for(".remito", remito_id=remito.id))


@bp.post("/empaquetado/descartar")
def descartar():
    clinica_id = request.form.get("clinica", type=int)
    descartadas = LogisticaService().descartar_vencidas(clinica_id)
    if descartadas:
        flash(f"Se descartaron {len(descartadas)} muestra(s) fuera de su ventana de viabilidad: "
              + ", ".join(m.codigo for m in descartadas), "warning")
    else:
        flash("No hay muestras vencidas en esta clínica.", "info")
    return redirect(url_for(".empaquetado", clinica=clinica_id))


# ------------------------------------------------------------------ Remitos
@bp.get("/remitos")
def remitos():
    estado = request.args.get("estado", "EN_TRANSITO")
    servicio = LogisticaService()
    conteo = {clave: len(servicio.listar_remitos([clave] if clave else None)) for clave in FILTROS_REMITO}
    return render_template("remitos.html", remitos=servicio.listar_remitos([estado] if estado else None),
                           estado=estado, filtros=FILTROS_REMITO, conteo=conteo)


@bp.get("/remitos/<int:remito_id>")
def remito(remito_id, datos=None):
    servicio = LogisticaService()
    filas = servicio.listar_remitos(remito_id=remito_id)
    if not filas:
        abort(404)
    return render_template("remito.html", r=filas[0], eventos=servicio.eventos_de_remito(remito_id),
                           muestras=servicio.muestras_de_remito(remito_id), ahora=ahora(),
                           datos=datos or {}, formulario=request.form.get("formulario", ""))


# ------------------------------------------------------------------ 5. Cadena de envío
@bp.post("/remitos/<int:remito_id>/despachar")
@validar(remito)
def despachar(remito_id):
    f = request.form
    LogisticaService().despachar(remito_id, f.get("transportista", ""), f.get("temperatura"), f.get("vehiculo", ""),
                                 f.get("fecha_hora"))
    flash("Remito despachado: las muestras están en tránsito hacia el laboratorio central.", "success")
    return redirect(url_for(".remito", remito_id=remito_id))


@bp.post("/remitos/<int:remito_id>/control")
@validar(remito)
def control(remito_id):
    f = request.form
    evento = LogisticaService().registrar_punto_control(remito_id, f.get("ubicacion", ""), f.get("temperatura"),
                                                        f.get("responsable", ""), f.get("observacion", ""),
                                                        f.get("fecha_hora"))
    flash(f"Punto de control registrado en {evento.ubicacion} ({evento.temperatura:g} °C).", "success")
    return redirect(url_for(".remito", remito_id=remito_id))


# ------------------------------------------------------------------ 6. Recepción
@bp.post("/remitos/<int:remito_id>/recibir")
@validar(remito)
def recibir(remito_id):
    f = request.form
    intacto = f.get("precinto") == "INTACTO"
    _, detalle = LogisticaService().recibir(remito_id, f.get("recibido_por", ""), intacto, f.get("temperatura"),
                                            f.get("observaciones", ""), f.get("fecha_hora"))
    rechazadas = [(m, motivo) for m, motivo in detalle if motivo]
    if rechazadas:
        flash(f"Recepción registrada: {len(detalle) - len(rechazadas)} muestra(s) aceptada(s) y "
              f"{len(rechazadas)} rechazada(s).\n"
              + "\n".join(f"• {m.codigo}: {motivo}" for m, motivo in rechazadas), "danger")
    else:
        flash(f"Recepción registrada: las {len(detalle)} muestra(s) llegaron viables.", "success")
    return redirect(url_for(".remito", remito_id=remito_id))
