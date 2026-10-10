# -*- coding: utf-8 -*-
"""Pruebas del Control Contable de Estadisticas: ingresos, egresos,
margen y factibilidad mensual.

    python test_contable.py

No toca la base real: usa un archivo temporal con el mismo esquema de
`transacciones`, y no abre la app.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import main

FALLOS = []

DDL_TRANSACCIONES = """
    CREATE TABLE IF NOT EXISTS transacciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        cuenta TEXT NOT NULL,
        tipo TEXT NOT NULL,
        monto REAL NOT NULL,
        comision REAL DEFAULT 0,
        viajes INTEGER DEFAULT 0,
        km REAL DEFAULT 0,
        categoria TEXT NOT NULL,
        descripcion TEXT
    )
"""

# Datos de prueba (misma tanda que test_stats, para poder cruzarlos):
#   sep/2025: entran 42 (30 de viaje + 12 de propina) y salen 17
#             (10 de comision+gasolina+aporte: 5 + 8 + 4) -> balance 25
#   oct/2025: entran 50 y salen 10 de comision          -> balance 40
MOVIMIENTOS = [
    ("2025-09-05", "Ahorro InDrive", "Ingreso", 30.0, 5.0,
     1, 10, "Viaje InDrive", "sesion"),
    ("2025-09-05", "Ahorro InDrive", "Gasto", 8.0, 0.0,
     0, 0, "Combustible", "gasolina"),
    ("2025-09-05", "Ahorro InDrive", "Gasto", 4.0, 0.0,
     0, 0, "Uso del Carro", "aporte"),
    ("2025-09-20", "Ahorro InDrive", "Ingreso", 12.0, 0.0,
     0, 0, "Propina", ""),
    ("2025-10-02", "Ahorro InDrive", "Ingreso", 50.0, 10.0,
     2, 25, "Viaje InDrive", "sesion"),
    # otra cuenta: no entra en el analisis del negocio
    ("2025-10-03", "Uso del Carro", "Ingreso", 999.0, 0.0,
     0, 0, "Aporte", "no cuenta"),
]


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


def _aprox(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


def _extraer_regla(nombre):
    """Corta del KV las lineas de `<Nombre>:` hasta la siguiente regla."""
    lineas = main.KV.splitlines()
    marca = "<%s>:" % nombre
    inicio = None
    for i, linea in enumerate(lineas):
        if linea.startswith(marca):
            inicio = i
            break
    if inicio is None:
        return ""
    fin = inicio + 1
    while fin < len(lineas):
        linea = lineas[fin]
        if linea.strip() and not linea[0].isspace():
            break
        fin += 1
    return "\n".join(lineas[inicio:fin])


def _armar_pantalla():
    regla = "\n\n".join(t for t in (_extraer_regla('RoundedCard'),
                                    _extraer_regla('StatsScreen')) if t)
    if regla:
        main.Builder.load_string(regla)
    return main.StatsScreen(name='stats')


def main_test():
    # ------------------------------------------------ resumen contable ----
    contable = main._calcular_contable(
        [('2025-10', 50.0, 10.0), ('2025-09', 42.0, 17.0), ('2025-08', 0.0, 0.0)])
    chk([f[0] for f in contable["filas"]] == ['Oct 2025', 'Sep 2025', 'Ago 2025'],
        "el orden o las etiquetas salieron mal: %r"
        % ([f[0] for f in contable["filas"]],))
    chk(_aprox(contable["ingresos"], 92.0),
        "ingresos debia dar 92 y dio %r" % contable["ingresos"])
    chk(_aprox(contable["egresos"], 27.0),
        "egresos debia dar 27 y dio %r" % contable["egresos"])
    chk(_aprox(contable["balance"], 65.0),
        "balance debia dar 65 y dio %r" % contable["balance"])
    chk(contable["margen"] is not None and
        _aprox(contable["margen"], 65.0 / 92.0 * 100.0),
        "margen debia ser ~70.7%% y dio %r" % contable["margen"])

    fila_oct = contable["filas"][0]
    chk(_aprox(fila_oct[1], 50.0) and _aprox(fila_oct[2], 10.0) and
        _aprox(fila_oct[3], 40.0),
        "la fila de octubre salio mal: %r" % (fila_oct,))
    chk(fila_oct[4] is not None and _aprox(fila_oct[4], 80.0),
        "el margen de octubre debia dar 80%% y dio %r" % (fila_oct[4],))

    fila_ago = contable["filas"][2]
    chk(fila_ago[4] is None,
        "sin ingresos el margen debe ser None: %r" % (fila_ago[4],))

    vacio = main._calcular_contable([])
    chk(vacio["filas"] == [], "sin datos el detalle debe quedar vacio")
    chk(_aprox(vacio["ingresos"], 0.0) and _aprox(vacio["egresos"], 0.0) and
        _aprox(vacio["balance"], 0.0),
        "los totales sin datos deben ser 0: %r" % (vacio,))
    chk(vacio["margen"] is None,
        "sin ingresos el margen total debe ser None: %r" % (vacio["margen"],))

    # ------------------------------------------------ factibilidad -------
    casos = [
        ((100.0, 25.0), "factible"),
        ((100.0, 20.0), "factible"),
        ((100.0, 19.9), "ajustado"),
        ((100.0, 0.0), "ajustado"),
        ((100.0, -10.0), "no_factible"),
        ((0.0, -5.0), "no_factible"),
        ((0.0, 0.0), "sin_datos"),
    ]
    for (ingresos, balance), esperado in casos:
        codigo, texto = main._clasificar_factibilidad(ingresos, balance)
        chk(codigo == esperado,
            "_clasificar_factibilidad(%s, %s) -> %r y se esperaba %r"
            % (ingresos, balance, codigo, esperado))
        chk(bool(texto) and isinstance(texto, str),
            "el texto de factibilidad vino vacio para %r" % (codigo,))
        chk(codigo in main.COLORES_FACTIBILIDAD,
            "falta color para el codigo %r" % (codigo,))

    # el texto debe explicar el margen sobre una base de $100
    _, texto_ajustado = main._clasificar_factibilidad(100.0, 10.0)
    chk("$100" in texto_ajustado and "10" in texto_ajustado,
        "el texto ajustado no explica el margen: %r" % texto_ajustado)
    _, texto_perdida = main._clasificar_factibilidad(100.0, -10.0)
    chk("pierden" in texto_perdida,
        "el texto de perdida no dice que se pierde: %r" % texto_perdida)

    chk(_aprox(main._margen_color(None)[0], main.TEXT_SECONDARY[0]),
        "sin margen el color debe ser el de texto secundario")
    chk(main._margen_color(30.0) == main.PRIMARY,
        "margen sano debe ser verde")
    chk(main._margen_color(-5.0) == main.NEG,
        "margen negativo debe ser rojo")

    # ------------------------------------------------ desglose ----------
    filas_rubro = [
        ('2025-09', 'Combustible', 8.0),
        ('2025-09', 'Uso del Carro', 4.0),
        ('2025-09', 'Viaje InDrive', 5.0),
        ('2025-10', 'Viaje InDrive', 10.0),
        ('2025-08', 'Combustible', 77.0),   # mes fuera de la ventana
    ]
    mezcla, total = main._desglose_egresos(filas_rubro, ['2025-10', '2025-09'])
    chk(_aprox(total, 27.0),
        "el total de egresos debia dar 27 y dio %r" % total)
    chk([m[0] for m in mezcla] == ['Comisiones InDrive', 'Combustible',
                                   'Aporte al carro'],
        "el orden o los nombres del desglose salieron mal: %r"
        % ([m[0] for m in mezcla],))
    chk(_aprox(mezcla[0][1], 15.0),
        "comisiones debian sumar 15 y dio %r" % mezcla[0][1])
    chk(mezcla[0][2] > mezcla[1][2] > mezcla[2][2] > 0,
        "los porcentajes no quedaron en orden: %r" % (mezcla,))
    chk(_aprox(sum(m[2] for m in mezcla), 100.0, tol=1e-3),
        "los porcentajes deben sumar 100: %r"
        % (sum(m[2] for m in mezcla),))

    # los rubros de mas de `tope` se juntan en "Otros"
    muchas = [('2025-09', 'Rubro %d' % i, float(i)) for i in range(1, 5)]
    corto, _ = main._desglose_egresos(muchas, None, tope=2)
    chk(len(corto) == 3 and corto[-1][0] == u"Otros",
        "sobrantes no se agruparon en Otros: %r" % ([c[0] for c in corto],))
    chk(_aprox(corto[-1][1], 3.0),
        "Otros debia sumar 2+1=3 y dio %r" % corto[-1][1])

    sin_dato, total_vacio = main._desglose_egresos([], ['2025-09'])
    chk(sin_dato == [] and _aprox(total_vacio, 0.0),
        "sin egresos el desglose debe venir vacio: %r" % (sin_dato,))

    # ------------------------------------------------------ la SQL -------
    tmp = tempfile.mkdtemp(prefix="indrive_contable_")
    ruta = os.path.join(tmp, "prueba.db")
    ruta_origen = main.writable_db_path
    pantalla = None
    conn = None
    try:
        conn = sqlite3.connect(ruta)
        conn.execute(DDL_TRANSACCIONES)
        conn.executemany(
            "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
            " viajes, km, categoria, descripcion)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            MOVIMIENTOS)
        conn.commit()

        cur = conn.cursor()
        cur.execute(main.SQL_CONTABLE_MES)
        filas_mes = cur.fetchall()
        chk([f[0] for f in filas_mes] == ['2025-10', '2025-09'],
            "SQL_CONTABLE_MES debe venir en orden descendente: %r"
            % ([f[0] for f in filas_mes],))
        datos = dict((m, (i, e)) for m, i, e in filas_mes)
        chk(_aprox(datos['2025-09'][0], 42.0) and _aprox(datos['2025-09'][1], 17.0),
            "septiembre debia dar (42, 17) y dio %r" % (datos.get('2025-09'),))
        chk(_aprox(datos['2025-10'][0], 50.0) and _aprox(datos['2025-10'][1], 10.0),
            "octubre debia dar (50, 10) y dio %r" % (datos.get('2025-10'),))
        chk('2025-08' not in datos, "mes sin movimientos no debe aparecer")
        chk('999' not in str(datos.values()),
            "un movimiento de otra cuenta entro al analisis: %r" % (datos,))

        # el balance del contable tiene que dar el mismo numero que la
        # ganancia mensual: si no, la pantalla se contradice sola.
        cur.execute(main.SQL_GANANCIA_MES)
        ganancias = dict(cur.fetchall())
        for mes, (ingresos, egresos) in datos.items():
            chk(_aprox(ingresos - egresos, ganancias.get(mes)),
                "el balance de %s (%s) no coincide con la ganancia (%r)"
                % (mes, ingresos - egresos, ganancias.get(mes)))

        # la pintada completa de la pantalla sobre esa base temporal
        main.writable_db_path = ruta
        pantalla = _armar_pantalla()
        for clave in ('accounting_card', 'accounting_detail_card',
                      'lbl_ingresos_totales', 'lbl_egresos_totales',
                      'lbl_balance_total', 'lbl_margen_total',
                      'lbl_factibilidad', 'list_expense_mix',
                      'lbl_expense_empty', 'list_accounting',
                      'lbl_accounting_empty'):
            chk(clave in pantalla.ids,
                "falta la id %r en <StatsScreen>" % clave)

        chk(isinstance(pantalla.badge_texto, str) and pantalla.badge_texto,
            "el distintivo de factibilidad arranca vacio")
        chk(pantalla.badge_color == main.COLORES_FACTIBILIDAD["sin_datos"],
            "el distintivo debe arrancar en gris neutro")

        pantalla.ids.chart_canvas.size = (300, 200)
        pantalla.draw_chart()

        chk(pantalla.ids.lbl_ingresos_totales.text == "$92.00",
            "la tarjeta de ingresos dice %r"
            % pantalla.ids.lbl_ingresos_totales.text)
        chk(pantalla.ids.lbl_egresos_totales.text == "$27.00",
            "la tarjeta de egresos dice %r"
            % pantalla.ids.lbl_egresos_totales.text)
        chk(pantalla.ids.lbl_balance_total.text == "+$65.00",
            "la tarjeta de balance dice %r"
            % pantalla.ids.lbl_balance_total.text)
        margen_txt = pantalla.ids.lbl_margen_total.text
        chk(margen_txt.endswith("%") and margen_txt.startswith("70."),
            "la tarjeta de margen dice %r" % margen_txt)

        chk("FACTIBLE" in pantalla.badge_texto,
            "con 70%% de margen el veredicto debia ser FACTIBLE: %r"
            % pantalla.badge_texto)
        chk(pantalla.badge_color == main.COLORES_FACTIBILIDAD["factible"],
            "el distintivo debia ponerse verde: %r" % pantalla.badge_color)

        pintadas = len(pantalla.ids.list_accounting.children)
        chk(pintadas == 2,
            "se pintaron %d de 2 filas contables" % pintadas)
        chk(pantalla.ids.lbl_accounting_empty.text == "",
            "con datos el aviso de vacio debe quedarse en blanco")

        rubros_pintados = len(pantalla.ids.list_expense_mix.children)
        chk(rubros_pintados == 3,
            "se pintaron %d de 3 rubros de egreso" % rubros_pintados)
        chk(pantalla.ids.lbl_expense_empty.text == "",
            "con rubros el aviso de vacio debe quedarse en blanco")

        # fila contable: el mes, los tres importes y el margen a la vista
        filas = [_hijos(f) for f in pantalla.ids.list_accounting.children]
        fila_oct = next((t for t in filas if 'Oct 2025' in t), None)
        chk(fila_oct is not None,
            "no aparece la fila de Oct 2025: %r" % (filas,))
        if fila_oct:
            chk('$50.00' in fila_oct and '$10.00' in fila_oct and
                '+$40.00' in fila_oct,
                "la fila de octubre no muestra ingresos/egresos/balance: %r"
                % (fila_oct,))
            chk(any('80%' in t for t in fila_oct),
                "la fila de octubre no muestra el margen: %r" % (fila_oct,))

        # rubro: nombre, monto y participacion
        rubros = [_hijos(r) for r in pantalla.ids.list_expense_mix.children]
        comisiones = next((t for t in rubros
                           if any('Comisiones InDrive' in x for x in t)), None)
        chk(comisiones is not None,
            "no aparece el rubro Comisiones InDrive: %r" % (rubros,))
        if comisiones:
            chk(any('$15.00' in t for t in comisiones),
                "el monto del rubro no se pinto: %r" % (comisiones,))
    finally:
        main.writable_db_path = ruta_origen
        try:
            conn.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------- base vacia: nada de mentiras ---
    tmp2 = tempfile.mkdtemp(prefix="indrive_contable_vacio_")
    ruta2 = os.path.join(tmp2, "prueba.db")
    try:
        conn2 = sqlite3.connect(ruta2)
        conn2.execute(DDL_TRANSACCIONES)
        conn2.commit()
        conn2.close()

        main.writable_db_path = ruta2
        if pantalla is None:
            pantalla = _armar_pantalla()
        pantalla.ids.chart_canvas.size = (300, 200)
        pantalla.draw_chart()

        chk(pantalla.ids.lbl_accounting_empty.text != "",
            "sin movimientos hay que avisarlo en la tabla contable")
        chk(pantalla.ids.lbl_expense_empty.text != "",
            "sin egresos hay que avisarlo en el desglose")
        chk(len(pantalla.ids.list_accounting.children) == 0,
            "sin datos no debe pintarse ninguna fila contable")
        chk(pantalla.badge_texto == "Sin movimientos todavía",
            "sin datos el veredicto debe decirlo: %r" % pantalla.badge_texto)
        chk(pantalla.ids.lbl_margen_total.text == "—",
            "sin ingresos el margen debe ser un guion: %r"
            % pantalla.ids.lbl_margen_total.text)
    finally:
        main.writable_db_path = ruta_origen
        shutil.rmtree(tmp2, ignore_errors=True)

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


def _hijos(fila):
    """Textos de una fila, incluidos los que viven en celdas anidadas."""
    textos = []
    for hijo in fila.children:
        if hasattr(hijo, 'text'):
            textos.append(hijo.text)
        else:
            for nieto in hijo.children:
                if hasattr(nieto, 'text'):
                    textos.append(nieto.text)
    return textos


if __name__ == "__main__":
    sys.exit(main_test())
