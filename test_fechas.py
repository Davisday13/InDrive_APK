# -*- coding: utf-8 -*-
"""Pruebas de DateInput y de los helpers de fecha.

    python test_fechas.py
"""
import datetime
import sys

import widgets
from widgets import DateInput, fecha_iso, mostrar_fecha, parse_fecha

FALLOS = []


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


apuntar = chk


def _textos(raiz):
    """Todas las etiquetas de texto de un arbol de widgets."""
    from kivy.uix.label import Label
    vistas = []
    for hijo in raiz.children:
        if isinstance(hijo, Label):
            vistas.append(hijo.text)
        vistas.extend(_textos(hijo))
    return vistas


def _boton(raiz, texto):
    from kivy.uix.button import Button
    for hijo in raiz.children:
        if isinstance(hijo, Button) and hijo.text == texto:
            return hijo
        otro = _boton(hijo, texto)
        if otro is not None:
            return otro
    return None


def main():
    d = DateInput()
    chk(d.text == "", "vacio inicial")

    # tipear los digitos "15122024" de corrido
    d.insert_text("15122024")
    chk(d.text == "15/12/2024", "mascara corrida, got %r" % d.text)
    chk(d.fecha_iso == "2024-12-15", "fecha_iso, got %r" % d.fecha_iso)
    chk(d.fecha_valida, "fecha_valida True")

    # escribir en el medio (cursor al inicio)
    d.cursor = (0, 0)
    d.insert_text("1")
    chk(d.text.startswith("1"), "insert al inicio, got %r" % d.text)

    # tolerancia a otros formatos comunes
    d2 = DateInput()
    d2.text = "2024-12-31"
    chk(d2.text == "31/12/2024", "tolerancia AAAA-MM-DD, got %r" % d2.text)
    chk(d2.fecha_iso == "2024-12-31", "iso con formato largo, got %r" % d2.fecha_iso)

    d3 = DateInput()
    d3.text = "31-12-2024"
    chk(d3.text == "31/12/2024", "tolerancia DD-MM-AAAA, got %r" % d3.text)

    # backspace final
    d4 = DateInput()
    d4.insert_text("15122024")
    d4.cursor = (len(d4.text), 0)
    d4.do_backspace()
    chk(d4.text == "15/12/202", "backspace final, got %r" % d4.text)

    # cursor justo antes de una barra: el retroceso borra el digito previo
    d5 = DateInput()
    d5.insert_text("15122024")
    d5.cursor = (5, 0)
    d5.do_backspace()
    chk(d5.text == "15/12/024", "backspace antes de barra, got %r" % d5.text)

    # cursor justo detras de la barra: debe saltarla
    d5b = DateInput()
    d5b.insert_text("15122024")
    d5b.cursor = (6, 0)
    d5b.do_backspace()
    chk(d5b.text == "15/12/024", "backspace despues de barra, got %r" % d5b.text)

    # borrar una seleccion
    d5c = DateInput()
    d5c.insert_text("15122024")
    d5c.select_text(3, 5)
    chk(d5c.selection_text == "12", "seleccion, got %r" % d5c.selection_text)
    d5c.delete_selection()
    chk(d5c.text == "15/20/24", "delete_selection, got %r" % d5c.text)

    # no se puede escribir letras ni llenar de mas
    d6 = DateInput()
    d6.insert_text("abcdefgh999999999999")
    chk(len(DateInput._digitos(d6.text)) <= 8, "max 8 digitos, got %r" % d6.text)

    # fecha invalida marca el flag
    d7 = DateInput()
    d7.insert_text("32012024")
    chk(not d7.fecha_valida, "32/01/2024 debe ser invalida")
    chk(d7.fecha_iso == "", "iso vacio en invalida, got %r" % d7.fecha_iso)

    # vacio es valido (no es campo obligatorio)
    chk(DateInput().fecha_valida, "vacio valido")

    # helpers de fecha
    chk(widgets.hoy_iso() == datetime.datetime.now().strftime("%Y-%m-%d"), "hoy_iso")
    chk(mostrar_fecha("2024-12-31") == "31/12/2024", "mostrar_fecha iso")
    chk(mostrar_fecha(None) == "-", "mostrar_fecha None")
    chk(fecha_iso("") == "", "fecha_iso vacio")
    chk(fecha_iso("xx") is None, "fecha_iso invalido -> None")
    chk(parse_fecha("5/3/24") == ("2024-03-05", "05/03/2024"),
        "parse 5/3/24 -> %s" % (parse_fecha("5/3/24"),))

    # el calendario abre en el mes del valor y se puede navegar
    campo = DateInput(text="15/07/2023")
    popup = widgets.mostrar_selector_fecha(campo)
    if "JULIO 2023" not in _textos(popup.content):
        apuntar("el calendario no arranca en JULIO 2023: %s" % _textos(popup.content))
    boton = _boton(popup.content, "<<")
    if boton is None:
        apuntar("el boton '<<' no existe")
    else:
        boton.dispatch('on_release')
        if "JUNIO 2023" not in _textos(popup.content):
            apuntar("'<<' no retrocedio un mes: %s" % _textos(popup.content))
    if campo.text != "15/07/2023":
        apuntar("el calendario cambio el valor sin elegir: %r" % campo.text)
    popup.dismiss()

    # elegir un dia siembra el campo en formato corto
    elegida = []

    def _coger(iso):
        elegida.append(iso)

    campo2 = DateInput()
    popup2 = widgets.mostrar_selector_fecha(campo2, _coger)
    dia = _boton(popup2.content, "15")
    if dia is None:
        apuntar("no hay boton de dia 15")
    else:
        dia.dispatch('on_release')
        if not elegida or not elegida[0].endswith("-15"):
            apuntar("al elegir no devolvio el dia: %s" % elegida)
        if campo2.text != datetime.datetime.now().strftime("15/%m/%Y"):
            apuntar("al elegir no relleno el campo: %r" % campo2.text)
    popup2.dismiss()

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
