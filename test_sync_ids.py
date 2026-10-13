# -*- coding: utf-8 -*-
"""Pruebas del guardado de ids sincronizados (sync_ids).

    python test_sync_ids.py

Simula Supabase con un doble en memoria. El caso que cubre es el que
tiro los pagos de la nube: un equipo con la base local a medio llenar
sube, y sin este guardado borraba todo lo que no estaba en su local,
que era lo que habia subido el telefono.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import cloud_db

FALLOS = []


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


DDL = [
    "CREATE TABLE IF NOT EXISTS transacciones ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cuenta TEXT,"
    " tipo TEXT, monto REAL, comision REAL DEFAULT 0,"
    " viajes INTEGER DEFAULT 0, km REAL DEFAULT 0, categoria TEXT,"
    " descripcion TEXT, km_cliente REAL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY,"
    " nombre TEXT, deuda_total REAL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS casa_pagos (id INTEGER PRIMARY KEY,"
    " fecha TEXT, monto REAL, categoria TEXT)",
]


class NubeFalsa(object):
    """Doble de Supabase en memoria con la interfaz de _api."""

    def __init__(self):
        self.tablas = dict((t, {}) for t in cloud_db.TABLAS)

    def api(self, method, path, body=None, params=None, timeout=20,
            extra_headers=None, _retried=False):
        ruta, _, consulta = path.partition("?")
        tabla = ruta.rstrip("/").rsplit("/", 1)[-1]
        if tabla not in self.tablas:
            return 404, {"error": "tabla desconocida"}
        if method == "GET":
            filas = [dict(v) for v in self.tablas[tabla].values()]
            if "select=id" in consulta:
                filas = [{"id": f["id"]} for f in filas]
            return 200, filas
        if method == "POST":
            for fila in body or []:
                self.tablas[tabla][fila["id"]] = dict(fila)
            return 201, None
        if method == "DELETE" and consulta.startswith("id=in.("):
            ids = consulta[len("id=in.("):].rstrip(")").split(",")
            for i in ids:
                self.tablas[tabla].pop(int(i), None)
            return 204, None
        return 400, {"error": "%s %s" % (method, path)}


def conectar(ruta):
    conn = sqlite3.connect(ruta)
    for sql in DDL:
        conn.execute(sql)
    for tabla in cloud_db.TABLAS:
        if tabla not in ("transacciones", "clientes", "casa_pagos"):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY,"
                " fecha TEXT, monto REAL)" % tabla)
    conn.commit()
    return conn


def main():
    tmp = os.path.join(tempfile.gettempdir(), "indrive_sync_ids")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    db = os.path.join(tmp, "indrive_finanzas.db")

    nube = NubeFalsa()
    orig_api = cloud_db._api
    orig_sesion = cloud_db.hay_sesion
    cloud_db._api = nube.api
    cloud_db.hay_sesion = lambda: True
    cloud_db.DB_PATH = db

    try:
        # la nube trae lo que subio el telefono
        for i in range(1, 46):
            nube.tablas["casa_pagos"][i] = {"id": i, "fecha": "2026-10-01",
                                            "monto": 10.0, "categoria": "Luz"}
        nube.tablas["clientes"][1] = {"id": 1, "nombre": "Jose Luis",
                                      "deuda_total": 0}
        nube.tablas["clientes"][2] = {"id": 2, "nombre": "Maria",
                                      "deuda_total": 0}

        # 1) PC con la base a medio llenar: sube, no debe tocar la nube
        conn = conectar(db)
        for i in range(1, 5):
            conn.execute(
                "INSERT INTO transacciones (fecha, cuenta, tipo, monto,"
                " categoria, descripcion) VALUES ('2026-10-12',"
                " 'Ahorro InDrive', 'Ingreso', 10, 'Viaje InDrive', 'Sesion')")
        conn.commit()
        conn.close()

        chk(cloud_db.push_all(), "push_all fallo: %s" % cloud_db.DETALLE)
        chk(len(nube.tablas["casa_pagos"]) == 45,
            "borro los pagos de la nube: quedaron %d"
            % len(nube.tablas["casa_pagos"]))
        chk(len(nube.tablas["clientes"]) == 2,
            "borro clientes de la nube: quedaron %d"
            % len(nube.tablas["clientes"]))
        chk(len(nube.tablas["transacciones"]) == 4,
            "no subio las 4 transacciones locales: %d"
            % len(nube.tablas["transacciones"]))

        # 2) borra una fila que si subio este equipo
        conn = conectar(db)
        conn.execute("DELETE FROM transacciones WHERE id = 2")
        conn.commit()
        conn.close()
        chk(cloud_db.push_all(), "segundo push fallo: %s" % cloud_db.DETALLE)
        chk(2 not in nube.tablas["transacciones"],
            "no borro de la nube la fila que se borro localmente")
        chk(len(nube.tablas["transacciones"]) == 3,
            "transacciones en la nube: %d (iban 3)"
            % len(nube.tablas["transacciones"]))
        chk(len(nube.tablas["casa_pagos"]) == 45,
            "el segundo push toco los pagos: %d"
            % len(nube.tablas["casa_pagos"]))

        # 3) pull: lo descargado queda registrado como subido por aqui
        os.remove(db)
        conn = conectar(db)
        conn.close()
        nube.tablas["casa_gastos"][7] = {"id": 7, "fecha": "2026-10-05",
                                         "monto": 33.5}
        chk(cloud_db.pull_all(), "pull fallo: %s" % cloud_db.DETALLE)
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT id FROM sync_ids WHERE tabla='casa_gastos'")
        conocidos = set(r[0] for r in cur.fetchall())
        cur.execute("SELECT id FROM casa_gastos")
        locales = set(r[0] for r in cur.fetchall())
        conn.close()
        chk(conocidos == {7}, "pull no registro el id: %s" % conocidos)
        chk(locales == {7}, "pull no dejo la fila local: %s" % locales)

        chk(cloud_db.push_all(), "push tras pull fallo: %s" % cloud_db.DETALLE)
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM casa_gastos WHERE id = 7")
        conn.commit()
        conn.close()
        chk(cloud_db.push_all(), "push con borrado fallo: %s" % cloud_db.DETALLE)
        chk(7 not in nube.tablas["casa_gastos"],
            "no borro de la nube la fila descargada y borrada localmente")
    finally:
        cloud_db._api = orig_api
        cloud_db.hay_sesion = orig_sesion
        cloud_db.DB_PATH = ""
        shutil.rmtree(tmp, ignore_errors=True)

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
