# VetRed — Red de Clínicas y Derivación de Laboratorio

TP Integrador 2026 · Desarrollo de Aplicaciones con Objetos · Tema 2

Aplicación web local en **Python 3.11 + Flask + Bootstrap 5 + SQLite**. Bootstrap, sus íconos y Chart.js
están incluidos en el proyecto, así que funciona sin internet.

## Cómo ejecutar

```bash
pip install -r requirements.txt    # sólo la primera vez (instala Flask)
python main.py                     # levanta el servidor y abre http://127.0.0.1:5000
python main.py --datos-prueba      # regenera la base de demostración y abre la app
python -m unittest -v              # corre las pruebas (negocio + interfaz web)
```

Para detener el servidor: `Ctrl + C` en la terminal.

## Trabajo en grupo

```bash
git clone https://github.com/antodalmassofusco/TPI-DAO.git
cd TPI-DAO
pip install -r requirements.txt
python main.py
```

La base `veterinaria.db` no se sube al repositorio: cada integrante la genera con `python main.py`, así nadie
pisa los datos de otro. Antes de empezar a trabajar, `git pull`; al terminar, commit y `git push`.

## Estructura

```
main.py                 punto de entrada (servidor web local)
datos_prueba.py         genera ~75 días de actividad usando los servicios (respeta todas las validaciones)
veterinaria/
  config.py             parámetros (horario de agenda, precios de consulta, etc.)
  excepciones.py        errores de negocio
  dominio/
    entidades.py        entidades con sus invariantes (Cliente, Mascota, Remito, Precinto, ...)
    muestra.py          ciclo de vida de la muestra: patrones State + Observer
  persistencia/
    esquema.sql         tablas, restricciones y triggers de inmutabilidad
    conexion.py         conexión única a SQLite: patrón Singleton + transacciones anidables
    repositorios.py     patrón Repository (repositorio genérico por entidad)
  servicios/            lógica de negocio de cada proceso
  reportes/             patrón Template Method + 6 reportes
  web/
    rutas/              vistas Flask, una por área (sólo llaman a los servicios)
    templates/          páginas Jinja + Bootstrap
    static/             estilos propios y librerías (Bootstrap, íconos, Chart.js)
tests/
  test_negocio.py       pruebas de procesos y validaciones
  test_web.py           pruebas de todas las páginas y del circuito completo desde los formularios
```

## Procesos obligatorios → dónde están

| # | Proceso | Pantalla | Servicio |
|---|---------|----------|----------|
| 1 | Administrar clientes | Clientes | `ClienteService` |
| 2 | Mascotas e historias clínicas | Mascotas → Historia clínica | `MascotaService` |
| 3 | Consultas y órdenes de derivación | Atención clínica | `ConsultaService` |
| 4 | Empaquetado + remito biológico + precinto | Empaquetado | `LogisticaService.empaquetar` |
| 5 | Cadena de envío | Remitos y envíos → detalle del remito | `despachar`, `registrar_punto_control` |
| 6 | Recepción y verificación del precinto | Remitos y envíos → detalle del remito | `LogisticaService.recibir` |
| 7 | Resultados y comprobantes | Resultados · Comprobantes | `LaboratorioService`, `ComprobanteService` |

Opcionales implementados: agenda de turnos, recordatorios de vacunas y avisos de resultados (página Avisos)
y control de disponibilidad de conservadoras.

## Patrones de diseño

- **State**: `dominio/muestra.py`. Cada estado de la muestra es una clase que decide qué operaciones admite.
- **Observer**: cada cambio de estado de la muestra se notifica a `RegistroTrazabilidad` (bitácora) y a `AvisoAlCliente`.
- **Template Method**: `reportes/base.py`, `Reporte.generar()`.
- **Singleton**: `persistencia/conexion.py`, `BaseDatos`.
- **Repository**: `persistencia/repositorios.py`.
