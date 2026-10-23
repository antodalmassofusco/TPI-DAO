"""Formato de números al estilo argentino (punto de miles, coma decimal)."""


def numero(valor, decimales=2) -> str:
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


def moneda(valor) -> str:
    return f"$ {numero(valor)}"
