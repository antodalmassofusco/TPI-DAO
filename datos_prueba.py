"""Genera una base de datos de demostración con ~75 días de actividad.

Toda la carga se hace a través de los servicios, por lo que los datos respetan las mismas
validaciones que la interfaz. Incluye a propósito precintos rotos, rupturas de cadena de
frío y demoras, para que los reportes de rechazos y tiempos tengan contenido.

Uso:  python datos_prueba.py
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

from veterinaria.config import RUTA_BD
from veterinaria.dominio.entidades import Clinica, Laboratorio, TipoAnalisis, TipoVacuna, Veterinario
from veterinaria.excepciones import VeterinariaError
from veterinaria.persistencia import repositorios as r
from veterinaria.persistencia.conexion import BaseDatos
from veterinaria.servicios.catalogos import CatalogoService
from veterinaria.servicios.clientes import ClienteService
from veterinaria.servicios.comprobantes import ComprobanteService
from veterinaria.servicios.consultas import ConsultaService
from veterinaria.servicios.laboratorio import LaboratorioService
from veterinaria.servicios.logistica import LogisticaService
from veterinaria.servicios.mascotas import MascotaService
from veterinaria.servicios.notificaciones import NotificacionService
from veterinaria.servicios.turnos import TurnoService
from veterinaria.servicios.vacunas import VacunaService
from veterinaria.utils.fechas import formatear

DIAS_HISTORIA = 75

CLINICAS = [("Clínica Centro", "Av. Colón 1250, Córdoba", "351-4221100"),
            ("Clínica Norte", "Av. Rafael Núñez 4500, Córdoba", "351-4813300"),
            ("Clínica Sur", "Av. Vélez Sarsfield 3200, Córdoba", "351-4689900")]

VETERINARIOS = [("Lucía", "Fernández", "MP-2231", 0, "Clínica general"),
                ("Martín", "Gutiérrez", "MP-1874", 0, "Cirugía"),
                ("Carolina", "Sosa", "MP-2540", 1, "Dermatología"),
                ("Diego", "Romero", "MP-1990", 1, "Clínica general"),
                ("Valeria", "Álvarez", "MP-2712", 2, "Felinos"),
                ("Pablo", "Herrera", "MP-2105", 2, "Clínica general")]

VACUNAS = [("Antirrábica", "Perro", 3, 7500, True, 12), ("Séxtuple", "Perro", 2, 12000, True, 12),
           ("Tos de las perreras", "Perro", 4, 9000, False, 12),
           ("Antirrábica", "Gato", 3, 7500, True, 12), ("Triple felina", "Gato", 2, 11000, True, 12),
           ("Leucemia felina", "Gato", 3, 13000, False, 12)]

ANALISIS = [("Hemograma completo", "Sangre entera (EDTA)", 2, 8, 48, 9500),
            ("Bioquímica sérica", "Suero", 2, 8, 72, 14000),
            ("Urianálisis", "Orina", 2, 8, 24, 7000),
            ("Coproparasitológico", "Materia fecal", 2, 8, 72, 6000),
            ("Cultivo y antibiograma", "Hisopado", 2, 8, 48, 18000),
            ("Histopatología", "Tejido en formol", 15, 25, 240, 28000)]

CLIENTES = [("28456123", "María", "González", "351-6112233"), ("31789456", "Jorge", "Rodríguez", "351-6223344"),
            ("25123789", "Laura", "Martínez", "351-6334455"), ("33456789", "Santiago", "López", "351-6445566"),
            ("29874561", "Florencia", "Díaz", "351-6556677"), ("35698741", "Federico", "Pereyra", "351-6667788"),
            ("27412589", "Gabriela", "Torres", "351-6778899"), ("30258741", "Nicolás", "Ramírez", "351-6889900"),
            ("32147852", "Camila", "Flores", "351-6990011"), ("26987412", "Ricardo", "Acosta", "351-7001122"),
            ("34521478", "Agustina", "Benítez", "351-7112233"), ("24789632", "Héctor", "Medina", "351-7223344"),
            ("36985214", "Sofía", "Castro", "351-7334455"), ("31478523", "Matías", "Ortiz", "351-7445566"),
            ("28965412", "Paula", "Molina", "351-7556677")]

MASCOTAS = [("Toby", "Perro", "Caniche"), ("Luna", "Perro", "Labrador"), ("Michi", "Gato", "Común europeo"),
            ("Rocco", "Perro", "Bulldog francés"), ("Nina", "Gato", "Siamés"), ("Simón", "Perro", "Mestizo"),
            ("Kiara", "Perro", "Golden retriever"), ("Felipe", "Gato", "Persa"), ("Lola", "Perro", "Beagle"),
            ("Milo", "Gato", "Mestizo"), ("Bruno", "Perro", "Ovejero alemán"), ("Olivia", "Gato", "Maine coon"),
            ("Thor", "Perro", "Rottweiler"), ("Mora", "Perro", "Mestizo"), ("Pancho", "Gato", "Común europeo"),
            ("Coco", "Perro", "Shih tzu"), ("Frida", "Gato", "Bengalí"), ("Max", "Perro", "Border collie"),
            ("Chispa", "Perro", "Jack russell"), ("Tom", "Gato", "Mestizo"), ("Uma", "Perro", "Boxer"),
            ("Salem", "Gato", "Bombay"), ("Pipa", "Perro", "Mestizo"), ("Garfield", "Gato", "Exótico")]

CASOS = [  # (motivo, diagnóstico, tratamiento, análisis sugeridos)
    ("Vómitos y diarrea", "Gastroenteritis aguda", "Dieta blanda 72 h, metronidazol 15 mg/kg c/12 h",
     ["Hemograma completo", "Coproparasitológico"]),
    ("Decaimiento y pérdida de apetito", "Síndrome febril a esclarecer", "Fluidoterapia, control en 48 h",
     ["Hemograma completo", "Bioquímica sérica"]),
    ("Orina con sangre", "Cistitis", "Amoxicilina-clavulánico 7 días", ["Urianálisis", "Cultivo y antibiograma"]),
    ("Prurito intenso", "Dermatitis alérgica", "Antihistamínico, baño medicado semanal", []),
    ("Bulto en flanco", "Nódulo subcutáneo", "Exéresis quirúrgica programada", ["Histopatología"]),
    ("Tos persistente", "Traqueobronquitis", "Doxiciclina 10 días", ["Hemograma completo"]),
    ("Otitis", "Otitis externa bacteriana", "Limpieza y gotas óticas c/12 h", ["Cultivo y antibiograma"]),
    ("Pérdida de peso", "Sospecha de enfermedad renal", "Dieta renal, control bioquímico",
     ["Bioquímica sérica", "Urianálisis"]),
    ("Cojera miembro posterior", "Esguince", "Antiinflamatorio 5 días y reposo", []),
    ("Chequeo prequirúrgico", "Paciente apto", "", ["Hemograma completo", "Bioquímica sérica"]),
]

TRANSPORTISTAS = [("BioLogística Córdoba", "Utilitario AB123CD"), ("Moto Express Salud", "Moto A045XYZ"),
                  ("TransMed Refrigerados", "Furgón AC987EF")]
BIOQUIMICOS = ["Bioq. Andrea Paz", "Bioq. Ramiro Luna", "Bioq. Inés Quiroga"]


def _fh(dt):
    return formatear(dt)


def cargar_datos_prueba(ruta=RUTA_BD, semilla=42):
    rnd = random.Random(semilla)
    BaseDatos.cerrar()
    if ruta != ":memory:" and Path(ruta).exists():
        Path(ruta).unlink()
    bd = BaseDatos(ruta)

    # ------------------------------------------------------------------ Catálogos
    clinicas = [r.RepoClinica(bd).insertar(Clinica(*c)) for c in CLINICAS]
    r.RepoLaboratorio(bd).insertar(Laboratorio("Laboratorio Central VetLab", "Bv. San Juan 800, Córdoba",
                                               "351-4250000"))
    vets = [r.RepoVeterinario(bd).insertar(Veterinario(n, a, m, clinicas[i].id, esp))
            for n, a, m, i, esp in VETERINARIOS]
    for nombre, especie, edad, precio, oblig, refuerzo in VACUNAS:
        r.RepoTipoVacuna(bd).insertar(TipoVacuna(nombre, especie, edad, precio, oblig, refuerzo))
    analisis = {a[0]: r.RepoTipoAnalisis(bd).insertar(TipoAnalisis(*a)) for a in ANALISIS}
    catalogo = CatalogoService(bd)
    for clinica in clinicas:
        sigla = clinica.nombre.split()[-1][:3].upper()
        catalogo.alta_contenedor(f"CI-{sigla}-01", clinica.id, 2, 8, 6, "Conservadora refrigerada grande")
        catalogo.alta_contenedor(f"CI-{sigla}-02", clinica.id, 2, 8, 4, "Conservadora refrigerada chica")
        catalogo.alta_contenedor(f"CI-{sigla}-03", clinica.id, 15, 25, 6, "Contenedor temperatura ambiente")

    # ------------------------------------------------------------------ Clientes y mascotas
    hoy = datetime.now().replace(second=0, microsecond=0)
    clientes_srv, mascotas_srv = ClienteService(bd), MascotaService(bd)
    clientes = []
    for dni, nombre, apellido, tel in CLIENTES:
        email = f"{nombre.lower()}.{apellido.lower()}@mail.com".translate(str.maketrans("áéíóúñ", "aeioun"))
        clientes.append(clientes_srv.alta(dni, nombre, apellido, tel, email, f"Calle {rnd.randint(100, 9999)}"))
    mascotas = []
    for i, (nombre, especie, raza) in enumerate(MASCOTAS):
        edad_dias = rnd.choice([rnd.randint(150, 400), rnd.randint(400, 4500), rnd.randint(400, 4500)])
        peso = round(rnd.uniform(3, 35) if especie == "Perro" else rnd.uniform(2.5, 6.5), 1)
        mascotas.append(mascotas_srv.alta(nombre, especie, (hoy - timedelta(days=edad_dias + DIAS_HISTORIA)).date(),
                                          clientes[i % len(clientes)].id, raza, rnd.choice("MH"), peso))
    # Un cachorro recién llegado (aún no le corresponden vacunas)
    mascotas.append(mascotas_srv.alta("Pochoclo", "Perro", (hoy - timedelta(days=40)).date(),
                                      clientes[0].id, "Mestizo", "M", 2.1))

    # ------------------------------------------------------------------ Actividad diaria
    consultas_srv, logistica = ConsultaService(bd), LogisticaService(bd)
    lab, vacunas_srv = LaboratorioService(bd), VacunaService(bd)
    resultados_pendientes = []   # (instante, muestra_id)
    remitos_pendientes = []      # (instante_llegada, remito_id, precinto_ok, temp)
    consultas_hechas = []

    for dias_atras in range(DIAS_HISTORIA, 0, -1):
        dia = (hoy - timedelta(days=dias_atras)).replace(hour=0, minute=0)
        if dia.weekday() == 6:      # domingo cerrado
            continue
        # 1) llegadas demoradas de días anteriores
        for pendiente in [p for p in remitos_pendientes if p[0] <= dia + timedelta(hours=12)]:
            remitos_pendientes.remove(pendiente)
            llegada, remito_id, ok, temp = pendiente
            logistica.recibir(remito_id, rnd.choice(BIOQUIMICOS), ok, temp, fecha_hora=_fh(llegada))
            _programar_resultados(bd, rnd, remito_id, llegada, resultados_pendientes)

        # 2) atenciones del día
        for _ in range(rnd.randint(3, 6)):
            mascota = rnd.choice(mascotas[:-1])
            vet = rnd.choice(vets)
            instante = dia + timedelta(hours=rnd.randint(9, 16), minutes=rnd.choice([0, 15, 30, 45]))
            pendientes = vacunas_srv.pendientes(mascota, instante.date())
            # algunos responsables descuidan el calendario de vacunación (mascota.id múltiplo de 4)
            if pendientes and mascota.id % 4 and rnd.random() < 0.55:
                tipo, motivo, diag, trat, sugeridos = "CONTROL", "Control y vacunación", "Paciente sano", "", []
                aplicar = [(p["tipo"].id, f"L{rnd.randint(1000, 9999)}") for p in pendientes]
            else:
                motivo, diag, trat, sugeridos = rnd.choice(CASOS)
                tipo = "URGENCIA" if rnd.random() < 0.15 else "CONSULTA"
                aplicar = []
            try:
                consulta, _ = consultas_srv.registrar(mascota.id, vet.id, tipo, motivo, diag, trat,
                                                      vacunas=aplicar, fecha_hora=_fh(instante))
            except VeterinariaError:
                continue
            consultas_hechas.append(consulta)
            if sugeridos and rnd.random() < 0.8:
                consultas_srv.emitir_orden(
                    consulta.id, [analisis[n].id for n in sugeridos],
                    "URGENTE" if tipo == "URGENCIA" else "NORMAL",
                    fecha_hora=_fh(instante + timedelta(minutes=20)))

        # 3) empaquetado y despacho de cada clínica a las 17 h (el último día queda sin empaquetar)
        if dias_atras > 1:
            for clinica in clinicas:
                _empaquetar_y_despachar(bd, rnd, logistica, clinica, dia, dias_atras,
                                        remitos_pendientes, resultados_pendientes)

        # 4) resultados del laboratorio que ya corresponden
        for pendiente in sorted(p for p in resultados_pendientes if p[0] <= dia + timedelta(hours=23)):
            resultados_pendientes.remove(pendiente)
            instante, muestra_id = pendiente
            _registrar_resultado(lab, rnd, bd, muestra_id, instante)

    # ------------------------------------------------------------------ Comprobantes
    comprobantes = ComprobanteService(bd)
    for consulta in consultas_hechas:
        ultimo = bd.escalar("""
            SELECT MAX(h.fecha_hora) FROM historial_estado_muestra h
            JOIN muestra mu ON mu.id = h.muestra_id JOIN orden_derivacion o ON o.id = mu.orden_id
            WHERE o.consulta_id = ?""", (consulta.id,)) or consulta.fecha_hora
        emision = datetime.strptime(ultimo, "%Y-%m-%d %H:%M") + timedelta(hours=1)
        if emision < hoy - timedelta(days=1) and rnd.random() < 0.92:
            try:
                comprobantes.emitir(consulta.id, _fh(emision))
            except VeterinariaError:
                pass   # tiene muestras pendientes: queda para emitir desde la interfaz

    # ------------------------------------------------------------------ Turnos futuros
    turnos = TurnoService(bd)
    for dias in range(0, 8):
        dia = (hoy + timedelta(days=dias)).replace(hour=0, minute=0)
        if dia.weekday() == 6:
            continue
        for _ in range(rnd.randint(4, 8)):
            inicio = dia + timedelta(hours=rnd.randint(8, 19), minutes=rnd.choice([0, 30]))
            try:
                turnos.reservar(rnd.choice(vets).id, rnd.choice(mascotas).id, _fh(inicio), 30,
                                rnd.choice(["Control", "Vacunación", "Consulta", "Revisión de análisis"]),
                                ahora=_fh(hoy))
            except VeterinariaError:
                pass   # superposición u horario pasado: se descarta, igual que en la interfaz

    NotificacionService(bd).generar_recordatorios_vacunas()
    return bd


def _empaquetar_y_despachar(bd, rnd, logistica, clinica, dia, dias_atras, remitos_pendientes,
                            resultados_pendientes):
    logistica.descartar_vencidas(clinica.id, _fh(dia + timedelta(hours=16, minutes=55)))
    muestras = logistica.muestras_para_empaquetar(clinica.id)
    grupos = {"frio": [m for m in muestras if m["temp_max"] <= 8],
              "ambiente": [m for m in muestras if m["temp_min"] >= 15]}
    for clave, grupo in grupos.items():
        while grupo:
            disponibles = [c for c in CatalogoService(bd).contenedores(clinica.id, solo_disponibles=True)
                           if (c.temp_max <= 8) == (clave == "frio")]
            if not disponibles:
                break
            contenedor = disponibles[0]
            lote, grupo[:] = grupo[:contenedor.capacidad], grupo[contenedor.capacidad:]
            empaque = dia + timedelta(hours=17, minutes=rnd.randint(0, 20))
            try:
                remito, _ = logistica.empaquetar(contenedor.id, [m["id"] for m in lote],
                                                 f"Enf. {rnd.choice(['Ruiz', 'Paz', 'Vera'])}", _fh(empaque))
            except VeterinariaError:
                continue
            transportista, vehiculo = rnd.choice(TRANSPORTISTAS)
            salida = empaque + timedelta(minutes=rnd.randint(15, 50))
            logistica.despachar(remito.id, transportista, round(rnd.uniform(3.5, 6.5), 1) if clave == "frio"
                                else round(rnd.uniform(18, 23), 1), vehiculo, _fh(salida))
            if dias_atras == 2:     # queda en tránsito para mostrar la recepción en la demo
                continue
            control = salida + timedelta(minutes=rnd.randint(30, 70))
            falla_frio = clave == "frio" and rnd.random() < 0.05
            temp_control = (round(rnd.uniform(10.5, 14), 1) if falla_frio else
                            round(rnd.uniform(3, 7), 1) if clave == "frio" else round(rnd.uniform(17, 24), 1))
            logistica.registrar_punto_control(remito.id, rnd.choice(["Peaje Av. Circunvalación", "Base logística Ruta 20",
                                                                     "Control Bv. Los Andes"]),
                                              temp_control, transportista,
                                              "Falla en equipo de frío" if falla_frio else "", _fh(control))
            precinto_ok = rnd.random() > 0.04
            temp_llegada = round(rnd.uniform(3.5, 7.5), 1) if clave == "frio" else round(rnd.uniform(18, 24), 1)
            if rnd.random() < 0.12:    # demora: llega al día siguiente
                llegada = dia + timedelta(days=1, hours=rnd.randint(9, 11))
                remitos_pendientes.append((llegada, remito.id, precinto_ok, temp_llegada))
                continue
            llegada = control + timedelta(minutes=rnd.randint(30, 90))
            logistica.recibir(remito.id, rnd.choice(BIOQUIMICOS), precinto_ok, temp_llegada,
                              "" if precinto_ok else "Precinto con signos de apertura", _fh(llegada))
            _programar_resultados(bd, rnd, remito.id, llegada, resultados_pendientes)


def _programar_resultados(bd, rnd, remito_id, llegada, resultados_pendientes):
    # lo recibido en los últimos 3 días queda sin resultado, para cargarlo desde la interfaz
    if llegada >= datetime.now().replace(hour=0, minute=0) - timedelta(days=3):
        return
    for m in r.RepoMuestra(bd).listar("remito_id = ? AND estado = 'RECIBIDA'", (remito_id,)):
        resultados_pendientes.append((llegada + timedelta(hours=rnd.randint(4, 30)), m.id))


VALORES = {
    "Hemograma completo": ("Hto 42 %, GB 11.200/µl, Plaquetas 280.000/µl", "Valores dentro de rango"),
    "Bioquímica sérica": ("Urea 68 mg/dl, Creatinina 1,9 mg/dl, ALT 54 U/l", "Leve elevación de azoemia"),
    "Urianálisis": ("Densidad 1.018, pH 7, proteínas ++, sedimento con leucocitos", "Compatible con cistitis"),
    "Coproparasitológico": ("Huevos de Toxocara spp. (+)", "Parasitosis intestinal"),
    "Cultivo y antibiograma": ("E. coli > 100.000 UFC/ml. Sensible a amoxicilina-clavulánico", "Infección bacteriana"),
    "Histopatología": ("Proliferación de adipocitos maduros bien diferenciados", "Lipoma benigno"),
}


def _registrar_resultado(lab, rnd, bd, muestra_id, instante):
    nombre = bd.escalar("""SELECT ta.nombre FROM muestra mu JOIN tipo_analisis ta ON ta.id = mu.tipo_analisis_id
                           WHERE mu.id = ?""", (muestra_id,))
    valores, conclusion = VALORES[nombre]
    lab.registrar_resultado(muestra_id, rnd.choice(BIOQUIMICOS), valores, conclusion, fecha_hora=_fh(instante))


if __name__ == "__main__":
    base = cargar_datos_prueba()
    for tabla in ("cliente", "mascota", "consulta", "muestra", "remito", "resultado", "comprobante", "turno"):
        print(f"{tabla:12} {base.escalar(f'SELECT COUNT(*) FROM {tabla}')}")
    print("Muestras por estado:",
          {f["estado"]: f["n"] for f in base.consultar("SELECT estado, COUNT(*) n FROM muestra GROUP BY estado")})
