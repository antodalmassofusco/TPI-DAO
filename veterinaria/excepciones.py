"""Excepciones de negocio. La interfaz las muestra como advertencias al usuario."""


class VeterinariaError(Exception):
    """Base de todos los errores de negocio."""


class ValidacionError(VeterinariaError):
    """Un dato o una regla de negocio no se cumple."""


class EntidadNoEncontradaError(VeterinariaError):
    """Se buscó una entidad por id y no existe."""


class TransicionInvalidaError(VeterinariaError):
    """Se intentó un cambio de estado no permitido (p. ej. analizar una muestra rechazada)."""
