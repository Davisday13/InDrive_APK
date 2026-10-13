# -*- coding: utf-8 -*-
"""Pruebas del Retiro del fondo (dia sin trabajar o imprevisto).

    python test_retiro.py

El retiro es un Gasto con categoria 'Retiro' y descripcion obligatoria de
en que se uso, asi queda auditable. Baja el Saldo de Ahorro InDrive y
entra al Control Contable como rubro 'Retiros' (la caja cuadra), pero la
ganancia del dia, del mes y los KPIs no lo tocan. No toca la base real:
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
     0, 0, "Retiro", "gastos de la casa", 0.0),
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


def _buscar(widget, clase):
    """Widgets de una clase dentro del arbol, incluidos los padres."""
    encontrados = []
    if isinstance(widget, clase):
        encontrados.append(widget)
    for hijo in widget.children:
        encontrados.extend(_buscar(hijo, clase))
    return encontrados


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
    # guardar_retiro cierra con close_db, que agenda una subida a la nube.
    # Este test corre sobre una base temporal: si ese temporizador llegara
    # a dispararse borraria los datos reales de Supabase, asi que se apaga.
    sync_original = main.cloud_db.sync_after_write
    main.cloud_db.sync_after_write = lambda: None
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
            and _aprox(filas[0][2], 38.81),
            "el contable debia dar (50, 38.81) con el retiro sumado como"
            " egreso y dio %r" % (filas,))
        chk(_aprox(filas[0][1] - filas[0][2], 11.19),
            "el balance contable tiene que cuadrar con el saldo de la caja"
            " (11.19) y dio %r" % (filas[0][1] - filas[0][2],))
        chk(not _aprox(filas[0][1] - filas[0][2], 36.19),
            "el contable ya no debe repetir la ganancia: el retiro es"
            " plata que salio y la ganancia no lo cuenta")

        # ------------------------------------------ en que se va la plata -
        cur.execute(main.SQL_EGRESOS_RUBRO)
        rubros = set(f[1] for f in cur.fetchall())
        chk('Retiro' in rubros,
            "el retiro tiene que aparecer en 'en que se va la plata': %r"
            % (rubros,))
        chk(main.RUBROS_EGRESO.get('Retiro') == 'Retiros',
            "el rubro del retiro se muestra como 'Retiros' y da %r"
            % (main.RUBROS_EGRESO.get('Retiro'),))
        chk('Combustible' in rubros,
            "la gasolina sigue teniendo que aparecer: %r" % (rubros,))

        mezcla, total = main._desglose_egresos(
            cur.execute(main.SQL_EGRESOS_RUBRO).fetchall(), ['2026-10'])
        nombres = [m[0] for m in mezcla]
        chk('Retiros' in nombres,
            "la tarjeta 'en que se va la plata' debe listar Retiros: %r"
            % (nombres,))
        chk(_aprox(total, 38.81),
            "el total de la tarjeta debia ser 38.81 y dio %r" % total)

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
        chk(pantalla_stats.ids.lbl_egresos_totales.text == "$38.81",
            "egresos debia dar $38.81 (gas + retiro) y dio %r"
            % pantalla_stats.ids.lbl_egresos_totales.text)

        mensuales = _textos(pantalla_stats.ids.list_monthly_profits)
        chk(any('$36.19' in t for t in mensuales),
            "la ganancia del mes debia seguir en 36.19: %r" % (mensuales,))
        chk(not any('$25.00' in t or '$11.19' in t for t in mensuales),
            "el retiro no debe restar en la lista mensual: %r"
            % (mensuales,))

        # ------------------------------------------ popup del retiro ------
        popup = pantalla_ahorro.abrir_retiro()
        try:
            textos_popup = _textos(popup)
            chk(all(et in textos_popup for et in
                    ('Fecha', 'Monto a retirar', 'Descripción')),
                "el popup del retiro debe traer fecha, monto y descripcion:"
                " %r" % (textos_popup,))
            sugerencias = [w for w in _buscar(popup, main.CampoSugerencias)
                           if not isinstance(w, main.DateInput)]
            chk(len(sugerencias) == 1 and sugerencias[0].fuente is not None,
                "la descripcion del retiro debe aprender de las ya escritas")
        finally:
            popup.dismiss()

        # ----------------------------------------- detalle del dia --------
        filas_11, tot_11 = main._dia_detalle('2026-10-11')
        chk(len(filas_11) == 1 and filas_11[0][5]
            and filas_11[0][4] == 'gastos de la casa',
            "el detalle del dia tiene que listar el retiro con su"
            " descripcion: %r" % (filas_11,))
        chk(_aprox(tot_11['retiros'], 25.0) and _aprox(tot_11['gastos'], 0.0),
            "el retiro se cuenta aparte de los gastos: %r" % (tot_11,))
        chk(_aprox(tot_11['bruto'] - tot_11['comision'] - tot_11['gastos'],
                   0.0),
            "el neto del dia de retiro debe seguir en 0 y dio %r"
            % (tot_11['bruto'] - tot_11['comision'] - tot_11['gastos'],))

        filas_10, tot_10 = main._dia_detalle('2026-10-10')
        chk(_aprox(tot_10['gastos'], 13.81) and _aprox(tot_10['retiros'], 0.0),
            "el dia trabajado no debe cargar retiros: %r" % (tot_10,))
        chk(_aprox(tot_10['bruto'] - tot_10['comision'] - tot_10['gastos'],
                   36.19),
            "el neto del dia trabajado debia seguir en 36.19: %r"
            % (tot_10['bruto'] - tot_10['comision'] - tot_10['gastos'],))

        # ------------------------------------------------ calendario -------
        pantalla_cal = _armar('CalendarScreen')
        pantalla_cal._current_year = 2026
        pantalla_cal._current_month = 10
        pantalla_cal._render_calendar()
        botones = {}
        for hijo in pantalla_cal.ids.calendar_grid.children:
            texto = getattr(hijo, 'text', '') or ''
            if texto.split('\n')[0].isdigit():
                botones[texto.split('\n')[0]] = hijo
        dia_retiro = botones.get('11')
        chk(dia_retiro is not None and '$0.00' in dia_retiro.text,
            "el dia del retiro debe marcarse con $0.00: %r"
            % (dia_retiro.text if dia_retiro else None,))
        if dia_retiro is not None:
            col = dia_retiro.background_color
            chk(abs(col[0] - 0.95) < 1e-6 and abs(col[1] - 0.60) < 1e-6
                and abs(col[2] - 0.15) < 1e-6,
                "el dia del retiro debe quedar en ambar: %r" % (list(col),))
        dia_trabajo = botones.get('10')
        chk(dia_trabajo is not None and '$36.19' in dia_trabajo.text,
            "el dia trabajado sigue mostrando su ganancia: %r"
            % (dia_trabajo.text if dia_trabajo else None,))
        chk(dia_trabajo is None or '$0.00' not in dia_trabajo.text,
            "un dia trabajado no debe confundirse con un retiro")

        # ------------------------------------------ guardar_retiro --------
        chk(main.guardar_retiro('', 25, 'gastos') is not None,
            "un retiro sin fecha no debe guardarse")
        chk(main.guardar_retiro('2026-10-11', 0, 'gastos') is not None,
            "un retiro sin monto no debe guardarse")
        chk(main.guardar_retiro('2026-10-11', 25, '   ') is not None,
            "sin descripcion no se guarda: el retiro tiene que quedar"
            " auditable")
        cur.execute("SELECT COUNT(*) FROM transacciones"
                    " WHERE categoria = 'Retiro'")
        chk(cur.fetchone()[0] == 1,
            "los intentos invalidos no deben escribir filas")
        chk(main.guardar_retiro('2026-10-12', 30, 'imprevisto del carro')
            is None,
            "el retiro valido se guarda sin devolver error")
        cur.execute("SELECT descripcion FROM transacciones"
                    " WHERE categoria = 'Retiro' ORDER BY id DESC LIMIT 1")
        fila = cur.fetchone()
        chk(fila is not None and fila[0] == 'imprevisto del carro',
            "hay que guardar lo que se escribio: %r" % (fila,))
    finally:
        main.cloud_db.sync_after_write = sync_original
        main.writable_db_path = ruta_origen

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main_test())
