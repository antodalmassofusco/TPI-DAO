"""Agenda de turnos y proceso 3: atenciones clínicas y órdenes de derivación."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from veterinaria.config import DURACION_TURNO_MIN, PRIORIDADES, TIPOS_CONSULTA
from veterinaria.persistencia import repositorios as r
from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.consultas import ConsultaService
from veterinaria.servicios.mascotas import MascotaService
from veterinaria.servicios.turnos import TurnoService
from veterinaria.servicios.vacunas import PENDIENTE, VENCIDA, VacunaService
from veterinaria.utils.fechas import ahora, hoy
from veterinaria.web.util import validar

bp = Blueprint("atencion", __name__)


def _veterinarios():
    clinicas = {c.id: c.nombre for c in CatalogoService().clinicas()}
    return [(v.id, f"{v.nombre_completo} · {clinicas[v.clinica_id]}") for v in CatalogoService().veterinarios()]


def _mascotas():
    return [(m["id"], f"{m['nombre']} ({m['especie']}) — {m['responsable']}") for m in MascotaService().listar()]


# ------------------------------------------------------------------ Agenda
@bp.get("/agenda")
def agenda(datos=None):
    fecha = request.args.get("fecha", hoy().isoformat())
    veterinario = request.args.get("veterinario", type=int)
    solo_pendientes = request.args.get("pendientes", "1") == "1"
    turnos = TurnoService().listar(fecha or None, veterinario, "PENDIENTE" if solo_pendientes else None)
    datos = datos or {"duracion_min": DURACION_TURNO_MIN, "inicio": f"{fecha or hoy().isoformat()}T09:00"}
    return render_template("agenda.html", turnos=turnos, datos=datos, veterinarios=_veterinarios(),
                           mascotas=_mascotas(), fecha=fecha, veterinario=veterinario, solo_pendientes=solo_pendientes)


@bp.post("/agenda")
@validar(agenda)
def reservar():
    f = request.form
    turno = TurnoService().reservar(f.get("veterinario_id", type=int), f.get("mascota_id", type=int), f["inicio"],
                                    f.get("duracion_min"), f.get("motivo", ""), ahora=ahora())
    flash(f"Turno reservado el {turno.inicio[:10]} de {turno.inicio[11:]} a {turno.fin[11:]}.", "success")
    return redirect(url_for(".agenda", fecha=turno.inicio[:10]))


@bp.post("/agenda/<int:turno_id>/cancelar")
@validar(agenda)
def cancelar(turno_id):
    TurnoService().cancelar(turno_id)
    flash("Turno cancelado.", "success")
    return redirect(request.referrer or url_for(".agenda"))


# ------------------------------------------------------------------ Atención clínica
@bp.get("/atencion")
def atencion(datos=None):
    datos = datos or {"fecha_hora": ahora(), "tipo": "CONSULTA"}
    mascota_id = request.values.get("mascota", type=int) or request.form.get("mascota_id", type=int)
    contexto = {}
    if mascota_id:
        mascota = MascotaService().obtener(mascota_id)
        esquema = VacunaService().estado_esquema(mascota)
        contexto = {
            "mascota": mascota,
            "esquema": esquema,
            "pendientes": [v for v in esquema if v["tipo"].obligatoria and v["estado"] in (PENDIENTE, VENCIDA)],
            "turnos": [(t["id"], f"{t['inicio']} — {t['veterinario']}")
                       for t in TurnoService().listar(estado="PENDIENTE", mascota_id=mascota_id)],
            "vacunas_marcadas": [int(v) for v in request.form.getlist("vacunas")],
        }
    return render_template("atencion.html", datos=datos, mascotas=_mascotas(), veterinarios=_veterinarios(),
                           tipos=[(t, t.capitalize()) for t in TIPOS_CONSULTA], mascota_id=mascota_id,
                           recientes=ConsultaService().listar(limite=60), **contexto)


@bp.post("/atencion")
@validar(atencion)
def registrar():
    f = request.form
    lote = f.get("lote", "").strip()
    consulta, pendientes = ConsultaService().registrar(
        f.get("mascota_id", type=int), f.get("veterinario_id", type=int), f["tipo"], f.get("motivo", ""),
        f.get("diagnostico", ""), f.get("tratamiento", ""), f.get("peso") or None,
        [(int(v), lote) for v in f.getlist("vacunas")], f.get("turno_id", type=int), f.get("fecha_hora"))
    flash(f"Atención #{consulta.id} registrada.", "success")
    if pendientes:
        flash("Siguen pendientes vacunas obligatorias: "
              + ", ".join(f"{p['tipo'].nombre} ({p['estado'].lower()})" for p in pendientes), "warning")
    if f.get("derivar"):
        return redirect(url_for(".orden", consulta_id=consulta.id))
    return redirect(url_for(".atencion"))


@bp.get("/atencion/<int:consulta_id>/orden")
def orden(consulta_id, datos=None):
    consulta = ConsultaService().detalle(consulta_id)
    ordenes = r.RepoOrden().listar("consulta_id = ?", (consulta_id,))
    muestras = r.RepoMuestra().listar("orden_id IN (SELECT id FROM orden_derivacion WHERE consulta_id = ?)",
                                      (consulta_id,))
    tipos = {t.id: t for t in CatalogoService().tipos_analisis()}
    return render_template("orden.html", consulta=consulta, ordenes=ordenes, muestras=muestras, tipos=tipos,
                           prioridades=[(p, p.capitalize()) for p in PRIORIDADES], datos=datos or {},
                           marcados=[int(a) for a in request.form.getlist("analisis")])


@bp.post("/atencion/<int:consulta_id>/orden")
@validar(orden)
def emitir_orden(consulta_id):
    f = request.form
    orden_, muestras = ConsultaService().emitir_orden(
        consulta_id, [int(a) for a in f.getlist("analisis")], f.get("prioridad", "NORMAL"), f.get("observaciones", ""))
    flash(f"Orden #{orden_.id} emitida. Muestras extraídas: {', '.join(m.codigo for m in muestras)}. "
          "Ya pueden empaquetarse para el envío al laboratorio.", "success")
    return redirect(url_for(".orden", consulta_id=consulta_id))
