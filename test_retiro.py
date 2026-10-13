# -*- coding: utf-8 -*-
"""Pruebas del Retiro del fondo (dia sin trabajar).

    python test_retiro.py

El retiro es un Gasto con categoria 'Retiro': baja el Saldo de Ahorro
InDrive pero las estadisticas lo dejan afuera, para que un dia sin
trabajar no aparezca en rojo ni arruine el mes. No toca la base real:
usa archivos temporales con el mismo esquema de `transacciones`.
"""
import sqlite3
import sys
import tempfile

import main

FALLOS = []

DDL = """
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

# 10/10: dia trabajado (sesion + gasolina).
# 11/10: dia SIN trabajar, solo un retiro de 25 del fondo.
FILAS = [
    ("2026-10-10", "Ahorro InDrive", "Ingreso", 50.0, 0.0,
     10, 60, "Viaje InDrive", "Sesion", 40.0),
    ("2026-10-10", "Ahorro InDrive", "Gasto", 13.81, 0.0,
     0, 0, "Combustible", "Gasolina", 0.0),
    ("2026-10-11", "Ahorro InDrive", "Gasto", 25.0, 0.0,
     0, 0, "Retiro", "Retiro de fondo", 0.0),
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


def _armar(nombre):
    regla = "\n\n".join(t for t in (_extraer_regla('RoundedCard'),
                                    _extraer_regla(nombre)) if t)
    if regla:
        main.Builder.load_string(regla)
    return main.__dict__[nombre](name=nombre.lower().replace('screen', ''))


def _textos(widget):
    """Todos los textos de un widget, bajando por los hijos."""
    salida = []
    for hijo in widget.children:
        if getattr(hijo, 'text', None):
            salida.append(hijo.text)
        salida.extend(_textos(hijo))
    return salida


def _crear_base():
    tmp = tempfile.mkdtemp(prefix="indrive_retiro_")
    ruta = tmp + "/prueba.db"
    conn = sqlite3.connect(ruta)
    conn.execute(DDL)
    for fila in FILAS:
        conn.execute(
            "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
            " viajes, km, categoria, descripcion, km_cliente)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fila)
    conn.commit()
    conn.close()
    return ruta


def main_test():
    ruta_origen = main.writable_db_path
    ruta = _crear_base()
    main.writable_db_path = ruta
    pantalla_ahorro = None
    pantalla_stats = None
    try:
        conn = sqlite3.connect(ruta)
        cur = conn.cursor()

        # ------------------------------------------------------- saldo ----
        # Misma cuenta que hace la app: ingresa - sale, incluyendo el
        # retiro, porque la plata dejo de estar en el fondo.
        cur.execute("SELECT tipo, categoria, monto, comision"
                    " FROM transacciones WHERE cuenta = 'Ahorro InDrive'")
        ing = eg = 0.0
        for tipo, cat, monto, comision in cur.fetchall():
            if tipo == "Ingreso":
                ing += (monto - comision) if cat == "Viaje InDrive" else monto
            elif tipo == "Gasto":
                eg += monto
        saldo = ing - eg
        chk(_aprox(saldo, 11.19),
            "el saldo debia ser 11.19 (50 - 13.81 de gas - 25 de retiro)"
            " y dio %r" % saldo)

        # ------------------------------------------- ganancia del mes -----
        cur.execute(main.SQL_GANANCIA_MES)
        filas = cur.fetchall()
        chk([f[0] for f in filas] == ['2026-10'],
            "solo debe quedar el mes con actividad: %r" % (filas,))
        chk(_aprox(filas[0][1], 36.19),
            "la ganancia de octubre debia dar 36.19 sin contar el retiro"
            " y dio %r" % filas[0][1])

        # --------------------------------------------- control contable ---
        cur.execute(main.SQL_CONTABLE_MES)
        filas = cur.fetchall()
        chk(len(filas) == 1 and _aprox(filas[0][1], 50.0)
            and _aprox(filas[0][2], 13.81),
            "el contable debia dar (50, 13.81) sin el retiro y dio %r"
            % (filas,))
        chk(_aprox(filas[0][1] - filas[0][2], 36.19),
            "el balance contable debe dar lo mismo que la ganancia del"
            " mes: %r" % (filas[0][1] - filas[0][2],))

        # ------------------------------------------ en que se va la plata -
        cur.execute(main.SQL_EGRESOS_RUBRO)
        rubros = set(f[1] for f in cur.fetchall())
        chk('Retiro' not in rubros,
            "el retiro no es un gasto del negocio: %r" % (rubros,))
        chk('Combustible' in rubros,
            "la gasolina sigue teniendo que aparecer: %r" % (rubros,))

        # ------------------------------------------------ pantalla saldo --
        pantalla_ahorro = _armar('AhorroScreen')
        pantalla_ahorro.refresh_all()
        chk(pantalla_ahorro.balance_ahorro == "$11.19",
            "la pantalla de Ahorros debia mostrar $11.19 y muestra %r"
            % pantalla_ahorro.balance_ahorro)
        textos = _textos(pantalla_ahorro.ids.list_transacciones)
        chk(any('Retiro' in t for t in textos),
            "el retiro tiene que verse en Ultimos Movimientos: %r"
            % (textos,))

        # ------------------------------------------ estadisticas diarias --
        pantalla_stats = _armar('StatsScreen')
        pantalla_stats.ids.chart_canvas.size = (400, 300)
        pantalla_stats.draw_chart()

        filas_diarias = [t for t in _textos(pantalla_stats.ids.list_daily_profits)
                         if ' vj | ' in t]
        chk(filas_diarias == ["10 vj | 40/60 km"],
            "solo debe aparecer el dia trabajado y con sus km, no el del"
            " retiro: %r" % (filas_diarias,))

        chk(pantalla_stats.ids.lbl_efficiency.text == "$0.83/KM",
            "el $/km debia dar $0.83/KM sin contar el retiro y dio %r"
            % pantalla_stats.ids.lbl_efficiency.text)
        chk(pantalla_stats.ids.lbl_ingresos_totales.text == "$50.00",
            "ingresos debia dar $50.00 y dio %r"
            % pantalla_stats.ids.lbl_ingresos_totales.text)
        chk(pantalla_stats.ids.lbl_egresos_totales.text == "$13.81",
            "egresos debia dar $13.81 sin el retiro y dio %r"
            % pantalla_stats.ids.lbl_egresos_totales.text)

        mensuales = _textos(pantalla_stats.ids.list_monthly_profits)
        chk(any('$36.19' in t for t in mensuales),
            "la ganancia del mes debia seguir en 36.19: %r" % (mensuales,))
        chk(not any('$25.00' in t or '$11.19' in t for t in mensuales),
            "el retiro no debe restar en la lista mensual: %r"
            % (mensuales,))
    finally:
        main.writable_db_path = ruta_origen

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main_test())
