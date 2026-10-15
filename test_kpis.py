# -*- coding: utf-8 -*-
"""Pruebas de las tarjetas de KPIs de Estadisticas (semáforo del conductor).

    python test_kpis.py

Cubre el campo Km InDrive (cliente): la migracion de la columna, el
semáforo de cada tarjeta (precio, $/km real, km muerto, km por viaje y
la comparativa km cliente vs km reales) y la fila diaria. No toca la
base real: usa archivos temporales con el mismo esquema de
`transacciones`, y no abre la app.
"""
import sqlite3
import sys
import tempfile

import main

FALLOS = []

DDL_VIEJA = """
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

# Misma tabla, ya con la columna nueva. El orden importa: main.py y
# cloud_db.py leen las columnas por posicion en los SELECT *.
DDL = DDL_VIEJA.replace("""        descripcion TEXT
    )
""", """        descripcion TEXT,
        km_cliente REAL DEFAULT 0
    )
""")

VERDE = main.PRIMARY
ROJO = main.NEG
AMBAR = [0.95, 0.65, 0.15, 1]
GRIS = main.TEXT_SECONDARY


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


def _pintar(ruta, pantalla):
    main.writable_db_path = ruta
    pantalla.ids.chart_canvas.size = (300, 200)
    pantalla.draw_chart()


def _crear_base(ddl, filas):
    tmp = tempfile.mkdtemp(prefix="indrive_kpis_")
    ruta = tmp + "/prueba.db"
    conn = sqlite3.connect(ruta)
    conn.execute(ddl)
    for fila in filas:
        conn.execute(
            "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
            " viajes, km, categoria, descripcion, km_cliente)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fila)
    conn.commit()
    conn.close()
    return tmp, ruta


def _textos(widget):
    salida = []
    for hijo in widget.children:
        if getattr(hijo, 'text', None):
            salida.append(hijo.text)
        salida.extend(_textos(hijo))
    return salida


def main_test():
    ruta_origen = main.writable_db_path
    pantalla = None
    try:
        # -------------------------------------------------- migracion -----
        tmp_vieja, ruta_vieja = _crear_base(DDL_VIEJA, [])
        main.writable_db_path = ruta_vieja
        main.init_database()
        conn = sqlite3.connect(ruta_vieja)
        columnas = [c[1] for c in
                    conn.execute("PRAGMA table_info(transacciones)").fetchall()]
        conn.close()
        chk(columnas[-1] == 'km_cliente',
            "km_cliente debe quedar al FINAL de transacciones: %r" % (columnas,))
        chk(columnas[7] == 'km',
            "km debe seguir en la posicion 7 (los SELECT * leen por"
            " posicion): %r" % (columnas,))
        main.writable_db_path = ruta_origen

        # ------------------------------------------- tarjetas verdes ------
        # dos sesiones: una con Km InDrive y otra sin el, para comprobar
        # que los totales solo se arman con lo que el cliente pago.
        tmp_bueno, ruta_bueno = _crear_base(DDL, [
            ("2025-10-01", "Ahorro InDrive", "Ingreso", 50.0, 0.0,
             10, 60, "Viaje InDrive", "Sesión", 40.0),
            ("2025-10-02", "Ahorro InDrive", "Ingreso", 30.0, 5.0,
             10, 80, "Viaje InDrive", "Sesión", 0.0),
        ])
        pantalla = _armar_pantalla()
        for clave in ('lbl_efficiency', 'lbl_kpi_precio', 'lbl_kpi_muerto',
                      'lbl_kpi_kmviaje', 'lbl_kpi_comparativa'):
            chk(clave in pantalla.ids, "falta la id %r en <StatsScreen>" % clave)

        _pintar(ruta_bueno, pantalla)
        ids = pantalla.ids
        chk(ids.lbl_efficiency.text == "$0.54/KM",
            "el $/km real debia dar $0.54/KM y dio %r" % ids.lbl_efficiency.text)
        chk(_mismo_color(ids.lbl_efficiency.color, VERDE),
            "con 0.54 el $/km real debia salir verde: %r" % (ids.lbl_efficiency.color,))
        chk(ids.lbl_kpi_precio.text == "$1.25",
            "el precio debia dar $1.25 y dio %r" % ids.lbl_kpi_precio.text)
        chk(_mismo_color(ids.lbl_kpi_precio.color, VERDE),
            "con 1.25 el precio debia salir verde: %r" % (ids.lbl_kpi_precio.color,))
        chk(ids.lbl_kpi_muerto.text == "33%",
            "el km muerto debia dar 33%% y dio %r" % ids.lbl_kpi_muerto.text)
        chk(_mismo_color(ids.lbl_kpi_muerto.color, VERDE),
            "con 33%% el km muerto debia salir verde: %r"
            % (ids.lbl_kpi_muerto.color,))
        chk(ids.lbl_kpi_kmviaje.text == "7.0",
            "km por viaje debia dar 7.0 y dio %r" % ids.lbl_kpi_kmviaje.text)
        chk(_mismo_color(ids.lbl_kpi_kmviaje.color, AMBAR),
            "con 7.0 km/viaje debia salir ambar: %r"
            % (ids.lbl_kpi_kmviaje.color,))
        chk(ids.lbl_kpi_comparativa.text == "40/60",
            "la comparativa debia dar 40/60 y dio %r"
            % ids.lbl_kpi_comparativa.text)
        chk(_mismo_color(ids.lbl_kpi_comparativa.color, VERDE),
            "con ratio 0.67 la comparativa debia salir verde: %r"
            % (ids.lbl_kpi_comparativa.color,))

        # ------------------------------------------- tarjetas rojas -------
        tmp_malo, ruta_malo = _crear_base(DDL, [
            ("2025-10-05", "Ahorro InDrive", "Ingreso", 10.0, 0.0,
             5, 50, "Viaje InDrive", "Sesión", 40.0),
        ])
        _pintar(ruta_malo, pantalla)
        chk(ids.lbl_efficiency.text == "$0.20/KM",
            "el $/km real debia dar $0.20/KM y dio %r" % ids.lbl_efficiency.text)
        chk(_mismo_color(ids.lbl_efficiency.color, ROJO),
            "con 0.20 el $/km real debia salir rojo: %r"
            % (ids.lbl_efficiency.color,))
        chk(ids.lbl_kpi_precio.text == "$0.25",
            "el precio debia dar $0.25 y dio %r" % ids.lbl_kpi_precio.text)
        chk(_mismo_color(ids.lbl_kpi_precio.color, ROJO),
            "con 0.25 el precio debia salir rojo: %r"
            % (ids.lbl_kpi_precio.color,))
        chk(ids.lbl_kpi_muerto.text == "20%",
            "el km muerto debia dar 20%% y dio %r" % ids.lbl_kpi_muerto.text)
        chk(_mismo_color(ids.lbl_kpi_muerto.color, VERDE),
            "con 20%% el km muerto debia salir verde: %r"
            % (ids.lbl_kpi_muerto.color,))
        chk(ids.lbl_kpi_kmviaje.text == "10.0",
            "km por viaje debia dar 10.0 y dio %r" % ids.lbl_kpi_kmviaje.text)
        chk(_mismo_color(ids.lbl_kpi_kmviaje.color, ROJO),
            "con 10.0 km/viaje debia salir rojo: %r"
            % (ids.lbl_kpi_kmviaje.color,))

        # --------------------------------------------- sin datos ----------
        tmp_vacio, ruta_vacio = _crear_base(DDL, [])
        _pintar(ruta_vacio, pantalla)
        for clave in ('lbl_efficiency', 'lbl_kpi_precio', 'lbl_kpi_muerto',
                      'lbl_kpi_kmviaje', 'lbl_kpi_comparativa'):
            chk(ids[clave].text == "Sin datos",
                "sin datos la tarjeta %r debia decir 'Sin datos' y dice %r"
                % (clave, ids[clave].text))
            chk(_mismo_color(ids[clave].color, GRIS),
                "sin datos la tarjeta %r debia quedar gris: %r"
                % (clave, ids[clave].color))

        # --------------------------------------------- fila diaria --------
        con_kc = main.DailyProfitItem("2025-10-10", 14.84, 13.81, 13,
                                       103.9, 13.81, 0, 44.8)
        fila = [t for t in _textos(con_kc) if " vj | " in t]
        chk(fila == ["13 vj | 44.8/103.9 km"],
            "la fila diaria debia mostrar cliente/real y muestra %r" % (fila,))

        sin_kc = main.DailyProfitItem("2025-10-01", 47.17, 0.0, 22,
                                       180.0, 0.0, 0)
        fila = [t for t in _textos(sin_kc) if " vj | " in t]
        chk(fila == ["22 vj | 180 km"],
            "sin Km InDrive la fila debia quedar como estaba: %r" % (fila,))

        # ------------------------------------ ¿que me queda de verdad? ---
        # Los mismos números de octubre del conductor: bruto 580,
        # comision 59.15, gasolina 255.43, 1401.3 km, 182 viajes, 15 dias.
        # Me quedan 265.42 = 0.19/km -> AJUSTADO (ambar).
        for clave in ('lbl_rent_bruto', 'lbl_rent_com', 'lbl_rent_gas',
                      'lbl_rent_neto', 'lbl_rent_resumen', 'lbl_rent_veredicto'):
            chk(clave in pantalla.ids, "falta la id %r en <StatsScreen>" % clave)

        pantalla._pintar_rentabilidad(580.0, 59.15, 255.43, 1401.3, 182, 15)
        chk(ids.lbl_rent_bruto.text == "$580.00",
            "el bruto debia dar $580.00 y dio %r" % ids.lbl_rent_bruto.text)
        chk(ids.lbl_rent_com.text == "-$59.15",
            "la comision debia dar -$59.15 y dio %r" % ids.lbl_rent_com.text)
        chk(ids.lbl_rent_gas.text == "-$255.43",
            "la gasolina debia dar -$255.43 y dio %r" % ids.lbl_rent_gas.text)
        chk(ids.lbl_rent_neto.text == "$265.42",
            "me quedan $265.42 y la tarjeta dice %r" % ids.lbl_rent_neto.text)
        chk(ids.lbl_rent_resumen.text ==
            "$0.19 por km · $1.46 por viaje · $17.69 por día",
            "el resumen por km/viaje/dia salio %r" % ids.lbl_rent_resumen.text)
        chk(ids.lbl_rent_veredicto.text.startswith("AJUSTADO"),
            "con 0.19/km el veredicto debia ser AJUSTADO y dice %r"
            % ids.lbl_rent_veredicto.text)
        chk(_mismo_color(ids.lbl_rent_veredicto.color, AMBAR),
            "con 0.19/km el veredicto debia salir ambar: %r"
            % (ids.lbl_rent_veredicto.color,))

        # Sin km cargados no se presume nada: gris y "Sin datos".
        pantalla._pintar_rentabilidad(0, 0, 0, 0, 0, 0)
        chk(ids.lbl_rent_resumen.text == "Sin datos",
            "sin km el resumen debia decir 'Sin datos' y dice %r"
            % ids.lbl_rent_resumen.text)
        chk(_mismo_color(ids.lbl_rent_resumen.color, GRIS),
            "sin km el resumen debia quedar gris: %r"
            % (ids.lbl_rent_resumen.color,))

        # Con plata de mas por km: verde RENTABLE.
        pantalla._pintar_rentabilidad(580.0, 59.15, 100.0, 1401.3, 182, 15)
        chk(ids.lbl_rent_veredicto.text.startswith("RENTABLE"),
            "con 0.30/km el veredicto debia ser RENTABLE y dice %r"
            % ids.lbl_rent_veredicto.text)
        chk(_mismo_color(ids.lbl_rent_veredicto.color, VERDE),
            "con 0.30/km el veredicto debia salir verde: %r"
            % (ids.lbl_rent_veredicto.color,))

        # Mas gasolina que plata: rojo PÉRDIDA.
        pantalla._pintar_rentabilidad(100.0, 0.0, 250.0, 500.0, 80, 10)
        chk(ids.lbl_rent_veredicto.text.startswith("PÉRDIDA"),
            "con gasolina de mas el veredicto debia ser PÉRDIDA y dice %r"
            % ids.lbl_rent_veredicto.text)
        chk(_mismo_color(ids.lbl_rent_veredicto.color, ROJO),
            "en perdida el veredicto debia salir rojo: %r"
            % (ids.lbl_rent_veredicto.color,))
    finally:
        main.writable_db_path = ruta_origen
        if pantalla is not None:
            pantalla.clear_widgets()

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main_test())
