# -*- coding: utf-8 -*-
"""Pruebas de Estadisticas: la lista "Ganancia por Mes".

    python test_stats.py

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


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


def _extraer_regla(nombre):
    """Corta del KV las lineas de `<Nombre>:` hasta la siguiente regla.

    El KV completo se carga dentro de InDriveApp.build(), asi que fuera de
    la app hay que traerse solo las reglas que se quieren probar.
    """
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


def _apilar(pantalla, filas):
    lista = pantalla.ids.list_monthly_profits
    lista.clear_widgets()
    for etiqueta, valor, variacion in filas:
        lista.add_widget(main.MonthlyProfitItem(etiqueta, valor, variacion))
    return len(lista.children)


def main_test():
    # ------------------------------------------------ etiquetas de mes ----
    chk(main._etiqueta_mes('2025-09') == 'Sep 2025',
        "_etiqueta_mes(2025-09) -> %r" % main._etiqueta_mes('2025-09'))
    chk(main._etiqueta_mes('2024-12') == 'Dic 2024',
        "_etiqueta_mes(2024-12) -> %r" % main._etiqueta_mes('2024-12'))
    chk(main._etiqueta_mes('2025-13') == '2025-13',
        "_etiqueta_mes con mes 13 -> %r" % main._etiqueta_mes('2025-13'))
    chk(main._etiqueta_mes('cualquiera') == 'cualquiera',
        "_etiqueta_mes con texto -> %r" % main._etiqueta_mes('cualquiera'))

    chk(main._mes_previo_clave('2025-01') == '2024-12',
        "_mes_previo_clave(2025-01) -> %r" % main._mes_previo_clave('2025-01'))
    chk(main._mes_previo_clave('2025-12') == '2025-11',
        "_mes_previo_clave(2025-12) -> %r" % main._mes_previo_clave('2025-12'))
    chk(main._mes_previo_clave('2025-07') == '2025-06',
        "_mes_previo_clave(2025-07) -> %r" % main._mes_previo_clave('2025-07'))
    chk(main._mes_previo_clave('2025-00') is None,
        "_mes_previo_clave(2025-00) no devolvio None")
    chk(main._mes_previo_clave('hola') is None,
        "_mes_previo_clave(hola) no devolvio None")

    # -------------------------------------------------- variaciones -------
    filas = main._calcular_ganancias_mensuales(
        [('2025-10', 100.0), ('2025-09', 80.0), ('2025-08', 0.0),
         ('2025-06', 50.0), ('2025-05', -20.0)])
    chk([f[0] for f in filas] == ['Oct 2025', 'Sep 2025', 'Ago 2025',
                                  'Jun 2025', 'May 2025'],
        "el orden o las etiquetas salieron mal: %r" % ([f[0] for f in filas],))
    chk(filas[0][2] is not None and abs(filas[0][2] - 25.0) < 1e-6,
        "Oct sobre Sep debia dar 25%% y dio %r" % (filas[0][2],))
    chk(filas[1][2] is None,
        "con base ~0 la variacion debe ser None: %r" % (filas[1][2],))
    chk(filas[2][2] is None,
        "si falta julio la variacion de agosto debe ser None: %r"
        % (filas[2][2],))
    chk(filas[3][2] is not None and abs(filas[3][2] - 350.0) < 1e-6,
        "Jun sobre -20 debia dar 350%% y dio %r" % (filas[3][2],))
    chk(filas[4][2] is None, "el mes mas viejo no tiene variacion")
    chk(main._calcular_ganancias_mensuales([]) == [],
        "sin datos la lista debe quedar vacia")

    # ------------------------------------------------------ la SQL --------
    tmp = tempfile.mkdtemp(prefix="indrive_stats_")
    ruta = os.path.join(tmp, "prueba.db")
    filas_mes = []
    try:
        conn = sqlite3.connect(ruta)
        conn.execute(DDL_TRANSACCIONES)
        conn.executemany(
            "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
            " viajes, km, categoria, descripcion)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                # septiembre: viaje con comision + gasolina + aporte carro
                ("2025-09-05", "Ahorro InDrive", "Ingreso", 30.0, 5.0,
                 1, 10, "Viaje InDrive", "sesion"),
                ("2025-09-05", "Ahorro InDrive", "Gasto", 8.0, 0.0,
                 0, 0, "Combustible", "gasolina"),
                ("2025-09-05", "Ahorro InDrive", "Gasto", 4.0, 0.0,
                 0, 0, "Uso del Carro", "aporte"),
                # septiembre: ingreso manual, sin comision
                ("2025-09-20", "Ahorro InDrive", "Ingreso", 12.0, 0.0,
                 0, 0, "Propina", ""),
                # octubre
                ("2025-10-02", "Ahorro InDrive", "Ingreso", 50.0, 10.0,
                 2, 25, "Viaje InDrive", "sesion"),
                # otra cuenta: no debe entrar en la ganancia
                ("2025-10-03", "Uso del Carro", "Ingreso", 999.0, 0.0,
                 0, 0, "Aporte", "no cuenta"),
            ])
        conn.commit()

        cur = conn.cursor()
        cur.execute(main.SQL_GANANCIA_MES)
        filas_crudas = cur.fetchall()
        conn.close()

        datos = dict(filas_crudas)
        chk(list(datos.keys()) == ['2025-10', '2025-09'],
            "la SQL debe venir en orden descendente: %r" % (list(datos.keys()),))
        chk(abs(datos.get('2025-09', 0) - 25.0) < 1e-6,
            "septiembre debia dar 25.0 y dio %r" % (datos.get('2025-09'),))
        chk(abs(datos.get('2025-10', 0) - 40.0) < 1e-6,
            "octubre debia dar 40.0 y dio %r" % (datos.get('2025-10'),))
        chk('2025-08' not in datos, "mes sin movimientos no debe aparecer")

        filas_mes = main._calcular_ganancias_mensuales(filas_crudas)
        chk(len(filas_mes) == 2,
            "se esperaban 2 filas de mes y salieron %d" % len(filas_mes))
        chk(filas_mes[0][0] == 'Oct 2025' and filas_mes[0][2] is not None
            and abs(filas_mes[0][2] - 60.0) < 1e-6,
            "octubre debia subir 60%% y dio %r" % (filas_mes[0][2],))
        chk(filas_mes[1][0] == 'Sep 2025' and filas_mes[1][2] is None,
            "septiembre no tiene mes previo: %r" % (filas_mes[1],))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------------------------------------- la regla KV de Stats ----
    regla = "\n\n".join(t for t in (_extraer_regla('RoundedCard'),
                                    _extraer_regla('StatsScreen')) if t)
    chk('<StatsScreen>:' in regla, "no se pudo extraer la regla <StatsScreen>")
    chk('list_monthly_profits' in regla,
        "el KV de StatsScreen ya no trae la lista de ganancia por mes")
    if regla:
        main.Builder.load_string(regla)

    pantalla = main.StatsScreen(name='stats')
    for clave in ('monthly_profits_card', 'list_monthly_profits',
                  'lbl_monthly_empty', 'chart_canvas', 'chart_months',
                  'lbl_best_month', 'lbl_efficiency'):
        chk(clave in pantalla.ids, "falta la id %r en <StatsScreen>" % clave)
    chk(callable(getattr(pantalla, '_volver_atras', None)),
        "StatsScreen._volver_atras no existe y el boton '< Volver' explota")

    # ---------------------------------------------------- las filas --------
    fila = main.MonthlyProfitItem('Sep 2025', 123.45, -12.5)
    textos = [c.text for c in fila.children]
    chk('Sep 2025' in textos, "la fila no muestra el mes: %r" % (textos,))
    chk('+$123.45' in textos, "la fila no muestra la ganancia: %r" % (textos,))
    chk(u'\u25bc 12.5%' in textos,
        "la fila no muestra la variacion: %r" % (textos,))
    chk(fila.size_hint_y is None, "la fila debe tener altura fija")

    negativa = main.MonthlyProfitItem('Ago 2025', -20.0, None)
    textos = [c.text for c in negativa.children]
    chk('$-20.00' in textos, "la ganancia negativa salio mal: %r" % (textos,))
    chk(u'\u2014' in textos, "sin variacion debe mostrar un guion largo")

    pintadas = _apilar(pantalla, filas_mes)
    chk(pintadas == len(filas_mes),
        "se pintaron %d de %d filas" % (pintadas, len(filas_mes)))

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main_test())
