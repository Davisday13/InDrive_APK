# -*- coding: utf-8 -*-
"""Pruebas de la actualizacion automatica de la app.

    python test_version.py

No exige conexion: si Supabase no responde, la prueba lo anota y sigue.
"""
import hashlib
import os
import sys
import tempfile

import actualizador
from version import NOTA, VERSION, VERSION_CODE

FALLOS = []
AVISOS = []


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


def main():
    # --- version y manifiesto coherentes -------------------------------
    chk(VERSION and "." in VERSION, "VERSION vacia o rara: %r" % VERSION)
    chk(isinstance(VERSION_CODE, int) and VERSION_CODE > 0,
        "VERSION_CODE raro: %r" % (VERSION_CODE,))
    chk(NOTA, "NOTA vacia")

    # --- buildozer.spec debe seguir a version.py -----------------------
    spec = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'buildozer.spec')
    if os.path.exists(spec):
        texto = open(spec, encoding='utf-8').read().splitlines()
        version_spec = None
        codigo_spec = None
        for linea in texto:
            clave, _, valor = linea.partition('=')
            clave = clave.strip()
            valor = valor.strip()
            if clave == 'version':
                version_spec = valor
            elif clave == 'android.numeric_version':
                codigo_spec = valor
        chk(version_spec == VERSION,
            "buildozer.spec version=%r pero version.py dice %r "
            "(ejecuta scripts/sync_version.sh)" % (version_spec, VERSION))
        chk(codigo_spec == str(VERSION_CODE),
            "buildozer.spec numeric_version=%r pero VERSION_CODE es %d "
            "(ejecuta scripts/sync_version.sh)" % (codigo_spec, VERSION_CODE))
        permisos = [l.split('=', 1)[1].strip() for l in texto
                    if l.strip().startswith('android.permissions')]
        chk(permisos and 'REQUEST_INSTALL_PACKAGES' in permisos[0],
            "falta REQUEST_INSTALL_PACKAGES en buildozer.spec: %r" % (permisos,))
    else:
        AVISOS.append("no hay buildozer.spec junto al test")

    # --- URL del APK publicado -----------------------------------------
    esperada = (actualizador.SUPABASE_URL +
                "/storage/v1/object/public/apk/InDrive-Finanzas-1.2.0.apk")
    chk(actualizador.url_apk({"apk": "InDrive-Finanzas-1.2.0.apk"}) == esperada,
        "url_apk -> %r" % actualizador.url_apk({"apk": "x.apk"}))
    chk(actualizador.url_apk({}) == "", "url_apk sin nombre")
    chk(actualizador.url_apk(None) == "", "url_apk(None)")

    # --- deteccion de version nueva ------------------------------------
    chk(actualizador.hay_actualizacion({"version_code": VERSION_CODE + 1}),
        "no detecta una version mas nueva")
    chk(not actualizador.hay_actualizacion({"version_code": VERSION_CODE}),
        "detecta una version igual")
    chk(not actualizador.hay_actualizacion({"version_code": VERSION_CODE - 1}),
        "detecta una version mas vieja")
    chk(not actualizador.hay_actualizacion(None),
        "hay_actualizacion(None)")
    chk(not actualizador.hay_actualizacion({"version_code": "no-numero"}),
        "hay_actualizacion con texto no lanza")

    # --- consulta del manifiesto (tolerante a falta de red) -----------
    try:
        info = actualizador.consultar(timeout=8)
    except Exception as e:
        FALLOS.append("consultar lanzo %r" % e)
        info = None
    if info is None:
        AVISOS.append("latest.json no disponible (sin red o sin publicar)")
    else:
        chk(isinstance(info, dict), "consultar devolvio %r" % type(info))
        chk("apk" in info, "latest.json sin 'apk'")
        chk(isinstance(info.get("version_code"), int),
            "version_code no es entero: %r" % (info.get("version_code"),))
        if actualizador.hay_actualizacion(info):
            AVISOS.append("hay una version publicada mas nueva que %s" % VERSION)

    # --- descarga con progreso ----------------------------------------
    origen = os.path.join(tempfile.gettempdir(), "indrive_t_origen.bin")
    destino = os.path.join(tempfile.gettempdir(), "indrive_t_destino.bin")
    datos = os.urandom(512 * 1024)
    with open(origen, "wb") as f:
        f.write(datos)

    llamadas = []
    ruta = actualizador.descargar(
        "file:///" + origen.replace("\\", "/"), destino,
        on_avance=lambda a, b: llamadas.append((a, b)))
    chk(ruta == destino, "descargar -> %r" % ruta)
    if ruta:
        chk(open(destino, "rb").read() == datos, "el archivo llego incompleto")
        chk(bool(llamadas), "no se informo el avance")
        chk(llamadas[-1][0] == len(datos), "ultimo avance %r" % (llamadas[-1],))
        chk(llamadas[-1][1] == len(datos), "total %r" % (llamadas[-1],))

    chk(actualizador.descargar("file:///no/existe/apk.bin", destino) is None,
        "descargar de una ruta inexistente no devolvio None")
    chk(actualizador.descargar("", destino) is None,
        "descargar('') no devolvio None")
    chk(actualizador.descargar("http://", destino) is None,
        "descargar de una URL rota no devolvio None")

    # --- verificacion sha256 ------------------------------------------
    real = hashlib.sha256(datos).hexdigest()
    chk(actualizador._verificar(destino, real), "sha256 correcto rechazado")
    chk(not actualizador._verificar(destino, "0" * 64), "sha256 malo aceptado")
    chk(actualizador._verificar(destino, None), "sin sha256 debe pasar")

    # --- en el escritorio no se instala ni se abre el navegador --------
    chk(not actualizador.instalar(""), "instalar('') devolvio True")
    chk(not actualizador.instalar(destino),
        "instalar() devolvio True fuera de Android")
    chk(not actualizador.abrir_url("https://example.com/a.apk"),
        "abrir_url() devolvio True fuera de Android")
    chk(not actualizador.es_android(), "es_android() True en escritorio")

    for f in (origen, destino, destino + ".parcial"):
        try:
            os.remove(f)
        except OSError:
            pass

    print("FALLOS: %d" % len(FALLOS))
    for f in FALLOS:
        print("  - " + f)
    for a in AVISOS:
        print("  * aviso: " + a)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
