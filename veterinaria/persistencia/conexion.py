"""Acceso a la base de datos.

Patrón Singleton: toda la aplicación comparte una única conexión a SQLite, de modo que
las transacciones abiertas por un servicio incluyen lo que hagan los demás servicios
que éste invoque.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from veterinaria.config import RUTA_BD
from veterinaria.excepciones import ValidacionError

_ESQUEMA = Path(__file__).with_name("esquema.sql")


class BaseDatos:
    _instancia = None

    def __new__(cls, ruta=None):
        if cls._instancia is None:
            instancia = super().__new__(cls)
            instancia._inicializar(ruta or RUTA_BD)
            cls._instancia = instancia
        return cls._instancia

    def _inicializar(self, ruta):
        self.ruta = str(ruta)
        # isolation_level=None: el control de transacciones es explícito (ver transaccion()).
        # check_same_thread=False: el servidor web atiende las peticiones en un hilo distinto al que
        # creó la conexión; como corre con un único hilo, nunca hay accesos simultáneos.
        self._con = sqlite3.connect(self.ruta, isolation_level=None, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON")
        self._profundidad = 0
        self._con.executescript(_ESQUEMA.read_text(encoding="utf-8"))

    @classmethod
    def cerrar(cls):
        if cls._instancia is not None:
            cls._instancia._con.close()
            cls._instancia = None

    @classmethod
    def reiniciar(cls, ruta=None):
        """Cierra la conexión actual y abre una nueva (usado por tests y por la carga de datos)."""
        cls.cerrar()
        return cls(ruta)

    @contextmanager
    def transaccion(self):
        """Transacción anidable: sólo la más externa hace COMMIT o ROLLBACK."""
        if self._profundidad == 0:
            self._con.execute("BEGIN")
        self._profundidad += 1
        try:
            yield self
        except BaseException:
            self._profundidad -= 1
            if self._profundidad == 0:
                self._con.execute("ROLLBACK")
            raise
        else:
            self._profundidad -= 1
            if self._profundidad == 0:
                self._con.execute("COMMIT")

    def ejecutar(self, sql, parametros=()):
        try:
            return self._con.execute(sql, parametros)
        except sqlite3.IntegrityError as e:
            # Los triggers y restricciones de la base se informan como errores de negocio
            raise ValidacionError(f"Restricción de integridad: {e}") from e

    def consultar(self, sql, parametros=()):
        return [dict(fila) for fila in self._con.execute(sql, parametros).fetchall()]

    def consultar_uno(self, sql, parametros=()):
        fila = self._con.execute(sql, parametros).fetchone()
        return dict(fila) if fila else None

    def escalar(self, sql, parametros=()):
        fila = self._con.execute(sql, parametros).fetchone()
        return fila[0] if fila else None

    def siguiente_numero(self, tabla, prefijo, ancho=6):
        """Genera un número correlativo legible (p. ej. RB-000012) a partir del último id."""
        ultimo = self.escalar(f"SELECT COALESCE(MAX(id), 0) FROM {tabla}")
        return f"{prefijo}{ultimo + 1:0{ancho}d}"
