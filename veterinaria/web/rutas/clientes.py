"""Procesos 1 y 2: clientes, mascotas e historias clínicas."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from veterinaria.config import ESPECIES
from veterinaria.servicios.clientes import ClienteService
from veterinaria.servicios.mascotas import MascotaService
from veterinaria.web.util import validar

bp = Blueprint("clientes", __name__)
CAMPOS_CLIENTE = ("dni", "nombre", "apellido", "telefono", "email", "direccion")
CAMPOS_MASCOTA = ("nombre", "especie", "raza", "sexo", "fecha_nacimiento", "peso", "cliente_id")


# ------------------------------------------------------------------ Clientes
@bp.get("/clientes")
def listar(datos=None, cliente_id=None):
    servicio = ClienteService()
    cliente_id = cliente_id or request.args.get("editar", type=int)
    if not datos and cliente_id:
        cliente = servicio.obtener(cliente_id)
        datos = {c: getattr(cliente, c) for c in CAMPOS_CLIENTE}
    return render_template("clientes.html", clientes=servicio.listar(request.args.get("q", "")),
                           datos=datos or {}, cliente_id=cliente_id, q=request.args.get("q", ""))


@bp.post("/clientes")
@validar(listar)
def guardar():
    datos = {c: request.form.get(c, "").strip() for c in CAMPOS_CLIENTE}
    ClienteService().alta(**datos)
    flash(f"Cliente {datos['apellido']}, {datos['nombre']} registrado.", "success")
    return redirect(url_for(".listar"))


@bp.post("/clientes/<int:cliente_id>")
@validar(listar)
def modificar(cliente_id):
    ClienteService().modificar(cliente_id, **{c: request.form.get(c, "").strip() for c in CAMPOS_CLIENTE})
    flash("Datos del cliente actualizados.", "success")
    return redirect(url_for(".listar"))


@bp.post("/clientes/<int:cliente_id>/baja")
@validar(listar)
def baja(cliente_id):
    ClienteService().baja(cliente_id)
    flash("Cliente dado de baja.", "success")
    return redirect(url_for(".listar"))


# ------------------------------------------------------------------ Mascotas
@bp.get("/mascotas")
def mascotas(datos=None, mascota_id=None):
    servicio = MascotaService()
    mascota_id = mascota_id or request.args.get("editar", type=int)
    if not datos and mascota_id:
        mascota = servicio.obtener(mascota_id)
        datos = {c: getattr(mascota, c) for c in CAMPOS_MASCOTA}
        datos["peso"] = "" if mascota.peso is None else f"{mascota.peso:g}"
    datos = datos or {"cliente_id": request.args.get("cliente", "")}
    clientes = [(c["id"], f"{c['apellido']}, {c['nombre']} — DNI {c['dni']}") for c in ClienteService().listar()]
    return render_template("mascotas.html", mascotas=servicio.listar(request.args.get("q", "")), datos=datos,
                           mascota_id=mascota_id, clientes=clientes, especies=[(e, e) for e in ESPECIES],
                           q=request.args.get("q", ""))


def _datos_mascota():
    datos = {c: request.form.get(c, "").strip() for c in CAMPOS_MASCOTA}
    datos["cliente_id"] = int(datos["cliente_id"]) if datos["cliente_id"] else None
    datos["peso"] = datos["peso"] or None
    return datos


@bp.post("/mascotas")
@validar(mascotas)
def guardar_mascota():
    mascota = MascotaService().alta(**_datos_mascota())
    flash(f"{mascota.nombre} fue registrada.", "success")
    return redirect(url_for(".mascotas"))


@bp.post("/mascotas/<int:mascota_id>")
@validar(mascotas)
def modificar_mascota(mascota_id):
    MascotaService().modificar(mascota_id, **_datos_mascota())
    flash("Datos de la mascota actualizados.", "success")
    return redirect(url_for(".mascotas"))


@bp.post("/mascotas/<int:mascota_id>/baja")
def baja_mascota(mascota_id):
    MascotaService().baja(mascota_id)
    flash("Mascota dada de baja.", "success")
    return redirect(url_for(".mascotas"))


@bp.get("/mascotas/<int:mascota_id>/historia")
def historia(mascota_id):
    return render_template("historia.html", h=MascotaService().historia_clinica(mascota_id))
