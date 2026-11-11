# Huellitas - Red de clínicas y derivaciones de laboratorios

TP Integrador 2026 · Desarrollo de Aplicaciones con Objetos · Tema 2

**Documento explicativo** (casos de uso, modelo de dominio, diagramas de clases, DER, ciclos de vida de la muestra y
del remito, validaciones, patrones e informes): [docs/Documento_explicativo_Huellitas.pdf](docs/Documento_explicativo_Huellitas.pdf)

Aplicación web local en **Python 3.11 + Flask + Bootstrap 5 + SQLite**; los informes se exportan a PDF con
**reportlab**. Bootstrap, sus íconos y Chart.js están incluidos en el proyecto, así que funciona sin internet.

## Cómo ejecutar

```bash
pip install -r requirements.txt    # sólo la primera vez (instala Flask y reportlab)
python main.py                     # levanta el servidor y abre http://127.0.0.1:5000
python main.py --datos-prueba      # regenera la base de demostración y abre la app
python -m unittest -v              # corre las 45 pruebas (negocio + interfaz web)
```

Para detener el servidor: `Ctrl + C` en la terminal.

En Windows, si `python` o `pip` no se reconocen, usar el lanzador `py`: `py -m pip install -r requirements.txt`,
`py main.py`, `py -m unittest -v`.

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
    remito.py           ciclo de vida del remito biológico: patrones State + Observer
  persistencia/
    esquema.sql         tablas, restricciones y triggers de inmutabilidad (bitácoras de muestra y remito)
    conexion.py         conexión única a SQLite: patrón Singleton + transacciones anidables
    repositorios.py     patrón Repository (repositorio genérico por entidad)
  servicios/            lógica de negocio de cada proceso
  reportes/             informes: patrón Template Method, clase Grafico, 9 informes y exportación a PDF
  web/
    rutas/              vistas Flask, una por área (sólo llaman a los servicios)
    templates/          páginas Jinja + Bootstrap
    static/             estilos propios y librerías (Bootstrap, íconos, Chart.js)
tests/
  test_negocio.py       pruebas de procesos y validaciones
  test_web.py           pruebas de todas las páginas, los informes por período y el circuito completo desde los formularios
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

Además, un remito sin despachar se puede anular (`LogisticaService.anular`) y el laboratorio puede rechazar una
muestra recibida (`LaboratorioService.rechazar`). Si ya tenías una `veterinaria.db`, regenerala con
`python main.py --datos-prueba`: la bitácora del remito y sus triggers requieren el esquema nuevo.

Opcional implementado: recordatorios de vacunas y avisos de resultados (página Avisos). También se controla
la disponibilidad de las conservadoras, sin llegar a un stock de insumos.

Otras pantallas:

- **Mi día** (Clínica): el veterinario elige la fecha y ve sus turnos, las atenciones que registró, las muestras que
  derivó y los resultados de sus pacientes que llegaron ese día (`MiDiaService`).
- **Trazabilidad**: se busca por nombre o apellido del cliente y se elige la muestra de la lista.
- En las pantallas de muestras, el estado En tránsito se muestra como **Siendo analizada** (el remito conserva
  «En tránsito»).

## Informes

Nueve informes agrupados en cuatro categorías. Cada uno tiene resumen, gráficos elegidos según la pregunta que
responde, **conclusiones para la toma de decisiones** calculadas con los datos, tabla de detalle y descarga en CSV y
PDF (informe de gestión). Se filtran por **este mes, este trimestre, este año** o un rango personalizado.

| Categoría | Informe | Gráfico |
|-----------|---------|---------|
| Clínicas | Atenciones clínicas y derivaciones | Barras apiladas con énfasis en lo derivado |
| Pacientes | Pacientes por especie y tipo de atención | Dos tortas (especie; consultas, controles y urgencias) |
| Pacientes | Tratamientos aplicados | Columnas por semana |
| Pacientes | Vacunas obligatorias pendientes | Barras por tramo de atraso |
| Muestras | Muestras ingresadas al laboratorio | Barras apiladas por análisis y torta por clínica |
| Muestras | Muestras rechazadas por fallas en el transporte | Tasa de rechazo por transportista y causa |
| Muestras | Tiempos de tránsito y procesamiento | Barras apiladas por etapa |
| Finanzas | Ingresos por tipo de atención | Curva por período y barras |
| Finanzas | Facturación por clínica y servicio | Barras apiladas por servicio |

## Patrones de diseño

- **State**: `dominio/muestra.py` y `dominio/remito.py`. Cada estado de la muestra y del remito es una clase que decide
  qué operaciones admite.
- **Observer**: cada cambio de estado de la muestra se notifica a `RegistroTrazabilidad` (bitácora) y a `AvisoAlCliente`;
  cada cambio del remito, a `RegistroTrazabilidadRemito`.
- **Template Method**: `reportes/base.py`, `Reporte.generar()` (validar filtros → obtener datos → procesar → resumir →
  datos del gráfico → concluir). Cada informe declara sus `Grafico` (barras, columnas, líneas o torta), que se dibujan
  igual en pantalla y en el PDF, y redefine `concluir()` con sus conclusiones.
- **Singleton**: `persistencia/conexion.py`, `BaseDatos`.
- **Repository**: `persistencia/repositorios.py`.

La justificación de cada patrón, y de por qué no se aplicaron en otros lugares, está en la sección 7 del documento.

Consigna del tema: [docs/consigna_tema2.pdf](docs/consigna_tema2.pdf)
