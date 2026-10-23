"""Proceso 7 (comprobantes de atención) y avisos a clientes."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from veterinaria.excepciones import VeterinariaError
from veterinaria.servicios.comprobantes import ComprobanteService
from veterinaria.servicios.notificaciones import NotificacionService

bp = Blueprint("facturacion", __name__)


@bp.get("/comprobantes")
def comprobantes():
    servicio = ComprobanteService()
    return render_template("comprobantes.html", pendientes=servicio.consultas_sin_comprobante(),
                           emitidos=servicio.listar())


@bp.post("/comprobantes/emitir/<int:consulta_id>")
def emitir(consulta_id):
    try:
        comprobante = ComprobanteService().emitir(consulta_id)
    except VeterinariaError as e:
        flash(str(e), "warning")
        return redirect(url_for(".comprobantes"))
    flash(f"Comprobante {comprobante.numero} emitido.", "success")
    return redirect(url_for(".comprobante", comprobante_id=comprobante.id))


@bp.get("/comprobantes/<int:comprobante_id>")
def comprobante(comprobante_id):
    return render_template("comprobante.html", cp=ComprobanteService().detalle(comprobante_id))


@bp.get("/avisos")
def avisos():
    solo_pendientes = request.args.get("pendientes", "1") == "1"
    return render_template("avisos.html", avisos=NotificacionService().listar(solo_pendientes),
                           solo_pendientes=solo_pendientes)


@bp.post("/avisos/recordatorios")
def generar_recordatorios():
    creadas = NotificacionService().generar_recordatorios_vacunas()
    flash(f"Se generaron {creadas} recordatorio(s) de vacunación." if creadas else
          "No hay recordatorios nuevos para generar.", "success" if creadas else "info")
    return redirect(url_for(".avisos"))


@bp.post("/avisos/<int:aviso_id>/enviado")
def marcar_enviado(aviso_id):
    NotificacionService().marcar_enviada(aviso_id)
    return redirect(request.referrer or url_for(".avisos"))
