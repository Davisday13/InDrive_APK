# -*- coding: utf-8 -*-
"""Prueba de geometria del formulario de Ahorros a tamano de celular.

    python test_form_ui.py

Regresion del 13/10 (captura del telefono): el form_container crecia
hacia arriba y se montaba encima de las pestanas Viaje/Otro (la pestana
Otro quedaba tapada por el campo Fecha). La causa: BoxLayout no se
re-mide solo cuando cambia la altura de un hijo, asi que al ajustar el
contenedor hay que pedirle al padre que vuelva a acomodar.

No toca la nube ni la base real: trabaja en un directorio temporal.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(tempfile.gettempdir(), "indrive_form_ui")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)
for f in ["main.py", "cloud_db.py", "actualizador.py", "version.py",
          "widgets.py", "cacerts.py"]:
    shutil.copy(os.path.join(PROJ, f), TMP)

DDL = """
    CREATE TABLE IF NOT EXISTS transacciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
        cuenta TEXT NOT NULL, tipo TEXT NOT NULL, monto REAL NOT NULL,
        comision REAL DEFAULT 0, viajes INTEGER DEFAULT 0,
        km REAL DEFAULT 0, categoria TEXT NOT NULL, descripcion TEXT,
        km_cliente REAL DEFAULT 0)
"""
FILAS = [
    ("2026-10-12", "Ahorro InDrive", "Ingreso", 46.44, 0.0, 18, 95.0,
     "Viaje InDrive", "Sesion", 88.0),
    ("2026-10-12", "Ahorro InDrive", "Gasto", 14.79, 0.0, 0, 0,
     "Combustible", "Gasolina", 0.0),
    ("2026-10-12", "Ahorro InDrive", "Gasto", 5.0, 0.0, 0, 0,
     "Uso del Carro", "Aporte carro", 0.0),
    ("2026-10-11", "Ahorro InDrive", "Gasto", 25.0, 0.0, 0, 0,
     "Retiro", "gastos de la casa", 0.0),
]
conn = sqlite3.connect(os.path.join(TMP, "indrive_finanzas.db"))
conn.execute(DDL)
for fila in FILAS:
    conn.execute(
        "INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision,"
        " viajes, km, categoria, descripcion, km_cliente)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fila)
conn.commit()
conn.close()

os.chdir(TMP)
sys.path.insert(0, TMP)

# Tamano de celular (dp): asi se ve en el telefono del reporte.
from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "915")
Config.set("graphics", "resizable", "0")

from kivy.core.window import Window  # noqa: E402

import main  # noqa: E402

from kivy.clock import Clock  # noqa: E402

# La app en la PC nunca debe tocar la nube ni importar el Excel.
main.cloud_db.push_all = lambda *a, **k: True
main.cloud_db.pull_all = lambda *a, **k: True
main.cloud_db.push_inmediato = lambda *a, **k: True
main.cloud_db.sync_after_write = lambda *a, **k: None
main.cloud_db.hay_sesion = lambda: False
main.cloud_db.preparar_pull_si_vacio = lambda: False
main.cloud_db.init = lambda *a, **k: None

FALLOS = []
RUTAS = []


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


apuntar = chk


def _solapa(a, b, margen=0.5):
    """True si los rectangulos de dos widgets se pisan."""
    return (a.top > b.y + margen and a.y < b.top - margen
            and a.right > b.x + margen and a.x < b.right - margen)


def _raiz(scr):
    """El BoxLayout vertical que acomoda las secciones de la pantalla."""
    return scr.children[0]


def _forzar_layout_viejo(scr):
    """Deja la pantalla como quedaba en el telefono: el padre acomodo
    las secciones con el contenedor en 240dp (el alto del KV)."""
    cont = scr.ids.form_container
    cont.height = 240
    _raiz(scr).do_layout()


def medir(nombre):
    scr = main.App.get_running_app().root.get_screen("ahorro")
    cont = scr.ids.get("form_container")
    chk(cont is not None and len(cont.children) >= 2,
        "%s: form_container vacio o incompleto" % nombre)
    if cont is None or len(cont.children) < 2:
        return
    grid, btn = cont.children[1], cont.children[0]
    tabs = scr.ids.tab_viaje_btn.parent

    # 1) el contenedor NO se puede montar en la fila de pestanas
    chk(not _solapa(cont, tabs),
        "%s: el formulario se monta encima de las pestanas "
        "(cont top=%.0f y=%.0f | tabs top=%.0f y=%.0f)"
        % (nombre, cont.top, cont.y, tabs.top, tabs.y))
    chk(cont.top <= tabs.y + 0.5,
        "%s: el contenedor sube %.0fdp hasta las pestanas "
        "(cont top=%.0f, tabs y=%.0f)"
        % (nombre, cont.top - tabs.y, cont.top, tabs.y))

    # 2) la pestana "Otro" debe quedar libre (no cubierta por nada)
    otrob = scr.ids.tab_gasto_btn
    pisada = [w for w in cont.children if _solapa(w, otrob)]
    chk(not pisada,
        "%s: %d widget(es) del formulario tapan la pestana Otro"
        % (nombre, len(pisada)))

    # 3) internos: grilla y boton Guardar dentro del contenedor
    pad = cont.padding[0] + cont.padding[1]
    chk(grid.height >= (grid.minimum_height or 0) - 1,
        "%s: la grilla esta recortada (%.0f < %.0f)"
        % (nombre, grid.height, grid.minimum_height or 0))
    chk(cont.height >= grid.height + btn.height + pad + cont.spacing - 1,
        "%s: el contenedor no alcanza (%.0f) para grilla %.0f + boton %.0f"
        % (nombre, cont.height, grid.height, btn.height))
    chk(btn.top <= grid.y + 1,
        "%s: el boton Guardar se cruza con el formulario "
        "(boton top=%.0f, grilla y=%.0f)" % (nombre, btn.top, grid.y))
    chk(btn.y >= cont.y + cont.padding[1] - 1,
        "%s: el boton Guardar se sale del contenedor "
        "(boton y=%.0f, contenedor y=%.0f)" % (nombre, btn.y, cont.y))

    filas = list(grid.children)
    chk(len(filas) >= 10,
        "%s: faltan filas en la grilla (%d widgets)" % (nombre, len(filas)))
    malas = [w for w in filas if w.y < grid.y - 1 or w.top > grid.top + 1]
    chk(not malas,
        "%s: %d fila(s) fuera de la grilla" % (nombre, len(malas)))
    pisadas = [w for w in filas if w.top > btn.y + 1 and w.y < btn.top - 1]
    chk(not pisadas,
        "%s: el boton Guardar tapa %d fila(s)" % (nombre, len(pisadas)))

    print("%-18s cont=%.0f..%.0f tabs=%.0f..%.0f grilla=%.0f boton=%.0f "
          "filas=%d" % (nombre, cont.y, cont.top, tabs.y, tabs.top,
                        grid.height, btn.height, len(filas)))


def _foto(nombre):
    RUTAS.append(Window.screenshot(name=os.path.join(TMP, nombre)))


def disparar(dt):
    app = main.App.get_running_app()
    app.root.current = "ahorro"

    def _scr():
        return main.App.get_running_app().root.get_screen("ahorro")

    def paso1():
        # Simula el telefono: el padre acomodo las secciones con el
        # contenedor todavia en 240dp (el alto del KV). Despues
        # load_form_layout lo agranda y, si el padre no se vuelve a
        # medir, el contenedor crece hacia arriba y tapa las pestanas.
        scr = _scr()
        _forzar_layout_viejo(scr)
        scr.load_form_layout()

    def paso2():
        medir("viaje (tras reajuste)")
        _foto("1_viaje.png")

    def paso3():
        _scr().current_form = "otro"

    def paso4():
        medir("otro")
        _foto("2_otro.png")

    def paso5():
        _scr().current_form = "viaje"

    def paso6():
        medir("viaje otra vez")
        _foto("3_viaje_vuelta.png")
        app.stop()

    Clock.schedule_once(lambda dt: paso1(), 2.0)
    Clock.schedule_once(lambda dt: paso2(), 3.0)
    Clock.schedule_once(lambda dt: paso3(), 4.0)
    Clock.schedule_once(lambda dt: paso4(), 5.5)
    Clock.schedule_once(lambda dt: paso5(), 6.5)
    Clock.schedule_once(lambda dt: paso6(), 8.0)


Clock.schedule_once(disparar, 2.5)
main.InDriveApp().run()

print("FALLOS: %d" % len(FALLOS))
for f in FALLOS:
    print("  - " + f)
for r in RUTAS:
    print("foto:", r, os.path.exists(r) if r else None)
