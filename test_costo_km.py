# -*- coding: utf-8 -*-
"""Pruebas del "Costo del km: app vs real" de Estadisticas.

    python test_costo_km.py

La formula es la misma en las dos columnas:
    (bruto del viaje - comision de la app) / km
Solo cambia el divisor: los km que reporta inDrive o los km reales del
carro. No toca la base real: usa archivos temporales con el mismo esquema
de `transacciones`.
"""
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
        descripcion TEXT,
        km_cliente REAL DEFAULT 0
    )
"""


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


def _aprox(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


def _mismo_color(a, b, tol=1e-3):
    if a is None or b is None or len(a) != len(b):
        return False
    return all(abs(float(x) - float(y)) < tol for x, y in zip(a, b))


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


def _crear_base(filas):
    tmp = tempfile.mkdtemp(prefix="indrive_costo_km_")
    ruta = tmp + "/prueba.db"
    conn = sqlite3.connect(ruta)
    conn.execute(DDL_TRANSACCIONES)
    for fila in filas:
        conn.execute(
            "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
            " viajes, km, categoria, descripcion, km_cliente)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fila)
    conn.commit()
    conn.close()
    return tmp, ruta


def _pintar(ruta, pantalla, periodo=None):
    main.writable_db_path = ruta
    if periodo is not None:
        pantalla.periodo = periodo
    pantalla.ids.chart_canvas.size = (400, 300)
    pantalla.draw_chart()
    return pantalla.ids


def main_test():
    # ------------------------------------------------ la formula ---------
    chk(_aprox(main._costo_por_km(50.0, 40.0), 1.25),
        "_costo_por_km(50, 40) debia dar 1.25: %r"
        % main._costo_por_km(50.0, 40.0))
    chk(_aprox(main._costo_por_km(50.0, 60.0), 50.0 / 60.0),
        "_costo_por_km(50, 60) debia dar 0.8333: %r"
        % main._costo_por_km(50.0, 60.0))
    chk(main._costo_por_km(0.0, 0.0) is None,
        "sin km no hay costo por km: %r" % main._costo_por_km(0.0, 0.0))
    chk(main._costo_por_km(10.0, -5.0) is None,
        "km negativos no deben dividir: %r" % main._costo_por_km(10.0, -5.0))
    chk(_aprox(main._costo_por_km(None, 60.0), 0.0),
        "sin neto el costo por km debe ser 0: %r"
        % main._costo_por_km(None, 60.0))

    # --------------------------------------------- meses del periodo ----
    chk(main._mes_menos('2025-01', 1) == '2024-12',
        "_mes_menos(2025-01, 1) -> %r" % main._mes_menos('2025-01', 1))
    chk(main._mes_menos('2025-10', 11) == '2024-11',
        "_mes_menos(2025-10, 11) -> %r" % main._mes_menos('2025-10', 11))
    chk(main._mes_menos('malo', 3) is None,
        "_mes_menos con texto no devolvio None")

    ruta_origen = main.writable_db_path
    pantalla = None
    tmp = tmp2 = tmp3 = None
    try:
        # El caso del conductor: la app reporta 40 km, el auto marco 60.
        # Neto 50 / 40 = $1.25 por km de app; 50 / 60 = $0.83 por km real.
        tmp, ruta = _crear_base([
            ("2025-10-01", "Ahorro InDrive", "Ingreso", 50.0, 0.0,
             10, 60, "Viaje InDrive", "Sesión", 40.0),
            ("2025-10-02", "Ahorro InDrive", "Ingreso", 30.0, 5.0,
             10, 80, "Viaje InDrive", "Sesión", 0.0),
        ])
        pantalla = _armar_pantalla()
        ids = _pintar(ruta, pantalla)

        for clave in ('lbl_costo_app', 'lbl_costo_real', 'lbl_costo_dif'):
            chk(clave in pantalla.ids,
                "falta la id %r en <StatsScreen>" % clave)

        chk(ids.lbl_costo_app.text == "$1.25/km",
            "el km de la app debia dar $1.25/km y dio %r"
            % ids.lbl_costo_app.text)
        chk(ids.lbl_costo_real.text == "$0.83/km",
            "el km real debia dar $0.83/km y dio %r"
            % ids.lbl_costo_real.text)
        chk(ids.lbl_costo_dif.text ==
            "El km real deja $0.42 menos por km que el de la app (33%)",
            "la comparacion salio %r" % ids.lbl_costo_dif.text)
        chk(_mismo_color(ids.lbl_costo_real.color, main.PRIMARY),
            "con 0.83/km el km real debia salir verde: %r"
            % (ids.lbl_costo_real.color,))

        # La tarjeta vieja sigue mostrando el $/km real de todo el periodo
        # y coincide con la nueva columna de la app.
        chk(ids.lbl_efficiency.text == "$0.54/KM",
            "el $/km real de todo el periodo cambio: %r"
            % ids.lbl_efficiency.text)
        chk(ids.lbl_kpi_precio.text == "$1.25",
            "la tarjeta Pago app debia seguir en $1.25: %r"
            % ids.lbl_kpi_precio.text)

        # ------------------------------------------- filtro por periodo ----
        # Un viaje viejo (enero 2024) no debe entrar en los ultimos 3 meses.
        tmp2, ruta2 = _crear_base([
            ("2024-01-10", "Ahorro InDrive", "Ingreso", 20.0, 0.0,
             5, 10, "Viaje InDrive", "Viejo", 10.0),
            ("2025-10-01", "Ahorro InDrive", "Ingreso", 50.0, 0.0,
             10, 60, "Viaje InDrive", "Sesión", 40.0),
        ])
        ids = _pintar(ruta2, pantalla, '3m')
        chk(ids.lbl_costo_app.text == "$1.25/km",
            "3M debia ignorar enero 2024 y dar $1.25/km: %r"
            % ids.lbl_costo_app.text)
        chk(ids.lbl_costo_real.text == "$0.83/km",
            "3M debia ignorar enero 2024 y dar $0.83/km: %r"
            % ids.lbl_costo_real.text)
        chk(ids.lbl_ingresos_totales.text == "$50.00",
            "3M debia sumar solo octubre: %r" % ids.lbl_ingresos_totales.text)

        ids = _pintar(ruta2, pantalla, 'todo')
        chk(ids.lbl_costo_app.text == "$1.40/km",
            "Todo debia sumar los dos meses (70/50): %r"
            % ids.lbl_costo_app.text)
        chk(ids.lbl_costo_real.text == "$1.00/km",
            "Todo debia dar 70/70 = $1.00/km: %r"
            % ids.lbl_costo_real.text)
        chk(ids.lbl_ingresos_totales.text == "$70.00",
            "Todo debia sumar los dos meses: %r" % ids.lbl_ingresos_totales.text)

        # ------------------------------------------------ sin datos --------
        tmp3, ruta3 = _crear_base([])
        ids = _pintar(ruta3, pantalla, '12m')
        chk(ids.lbl_costo_app.text == "Sin datos",
            "sin datos la app debia decir 'Sin datos': %r"
            % ids.lbl_costo_app.text)
        chk(ids.lbl_costo_real.text == "Sin datos",
            "sin datos el km real debia decir 'Sin datos': %r"
            % ids.lbl_costo_real.text)
        chk(ids.lbl_costo_dif.text.startswith("Carga viajes"),
            "sin datos debe pedir cargar km: %r" % ids.lbl_costo_dif.text)
        chk(ids.lbl_best_month.text == "-",
            "al quedar sin datos el mejor mes no puede quedar viejo: %r"
            % ids.lbl_best_month.text)
        chk(len(ids.chart_months.children) == 0,
            "al quedar sin datos no pueden quedar meses dibujados")
    finally:
        main.writable_db_path = ruta_origen
        if pantalla is not None:
            pantalla.clear_widgets()
        for carpeta in (tmp, tmp2, tmp3):
            if carpeta:
                shutil.rmtree(carpeta, ignore_errors=True)

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main_test())
