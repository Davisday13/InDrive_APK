# -*- coding: utf-8 -*-
"""Pruebas de la actualizacion automatica de la app.

    python test_version.py

No exige conexion: si Supabase no responde, la prueba lo anota y sigue.
"""
import hashlib
import os
import sys
import tempfile
import urllib.error

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

    # --- jnius falso: permiso de instalacion y respaldo del navegador ---
    intentos = []
    abiertos = []

    class _Intent(object):
        ACTION_VIEW = "android.intent.action.VIEW"
        FLAG_ACTIVITY_NEW_TASK = 0x10000000

        def __init__(self, *args):
            self.args = args
            self.action = None
            self.data = None
            self.mimo = None
            self.flags = 0
            intentos.append(self)

        def setAction(self, accion):
            self.action = accion

        def setData(self, dato):
            self.data = dato

        def setDataAndType(self, dato, mimo):
            self.data, self.mimo = dato, mimo

        def addFlags(self, banderas):
            self.flags |= int(banderas)

    class _Uri(object):
        @staticmethod
        def parse(texto):
            return "uri:" + texto

    class _PackageManager(object):
        def __init__(self, permite):
            self.permite = permite

        def canRequestPackageInstalls(self):
            if self.permite is None:
                raise RuntimeError("API vieja")
            return self.permite

    class _Actividad(object):
        def __init__(self, permite):
            self.permite = permite

        def getPackageManager(self):
            return _PackageManager(self.permite)

        def getPackageName(self):
            return "org.indrive.indrive_finanzas"

        def startActivity(self, intento):
            abiertos.append(intento)

        def getContentResolver(self):
            return object()

    class _PythonActivity(object):
        pass

    class _Settings(object):
        ACTION_MANAGE_UNKNOWN_APP_SOURCES = "android.settings.MANAGE_UNKNOWN_APP_SOURCES"
        ACTION_SECURITY_SETTINGS = "android.settings.SECURITY_SETTINGS"

        class System(object):
            INSTALL_NON_MARKET_APPS = "install_non_market_apps"

            @staticmethod
            def getInt(receptor, nombre, por_defecto=0):
                return 0

    def _falso_autoclass(permite):
        actividad = _Actividad(permite)
        pa = _PythonActivity()
        pa.mActivity = actividad

        def buscar(nombre):
            if nombre == "org.kivy.android.PythonActivity":
                return pa
            if nombre == "android.content.Intent":
                return _Intent
            if nombre == "android.net.Uri":
                return _Uri
            if nombre == "android.provider.Settings":
                return _Settings
            raise KeyError(nombre)

        return buscar

    def _pedir_roto(*args, **kwargs):
        raise urllib.error.URLError("prueba: sin red")

    def _instalar_roto(ruta):
        actualizador.ultimo_error = "SecurityException: prueba de instalacion"
        return False

    manifiesto = {"version": "9.9.9", "version_code": VERSION_CODE + 888,
                  "apk": "InDrive-Finanzas-9.9.9.apk", "sha256": None}

    guardado = (actualizador._autoclass, actualizador.consultar,
                actualizador.descargar, actualizador.instalar,
                actualizador.abrir_url, actualizador._pedir)
    try:
        # sin permiso hay que abrir los ajustes y NO bajar nada
        bajadas = []
        actualizador._autoclass = lambda: _falso_autoclass(False)
        chk(not actualizador.permiso_instalacion(),
            "permiso_instalacion() dio True con canRequestPackageInstalls()==False")
        chk(actualizador.pedir_permiso_instalacion(), "no abrio los ajustes de permiso")
        chk(len(abiertos) == 1, "no lanzo la pantalla de permisos: %r" % (abiertos,))
        chk("unknown" in str(abiertos[-1].args[0]).lower(),
            "abrio una pantalla que no es de apps desconocidas: %r"
            % (abiertos[-1].args,))

        actualizador.consultar = lambda timeout=15: manifiesto
        actualizador.descargar = lambda *a, **k: bajadas.append(1)
        codigo, _ = actualizador.actualizar()
        chk(codigo == "permiso-instalar",
            "actualizar() sin permiso devolvio %r" % (codigo,))
        chk(not bajadas, "descargo el APK antes de pedir el permiso")

        # con permiso no hay que abrir nada raro
        actualizador._autoclass = lambda: _falso_autoclass(True)
        chk(actualizador.permiso_instalacion(),
            "permiso_instalacion() dio False con permiso concedido")

        # el navegador: la url sin tipo MIME (con MIME no acepta ninguna actividad)
        intentos[:] = []
        chk(actualizador.abrir_url("https://x/y.apk"), "abrir_url() fallo")
        chk(intentos and intentos[-1].data is not None,
            "abrir_url no paso la url al Intent")
        chk(intentos[-1].mimo is None,
            "abrir_url mando tipo MIME %r" % (intentos[-1].mimo,))

        # descarga rota -> respaldo en el navegador, con el motivo visible
        actualizador._pedir = _pedir_roto
        actualizador.descargar = guardado[2]
        codigo, detalle = actualizador.actualizar()
        chk(codigo == "navegador", "descarga fallida devolvio %r" % (codigo,))
        chk("URLError" in detalle and "prueba" in detalle,
            "el motivo de la descarga rota no se devolvio: %r" % (detalle,))
        chk(isinstance(actualizador.REINTENTOS, int) and
            actualizador.REINTENTOS > 1,
            "REINTENTOS raro: %r" % (actualizador.REINTENTOS,))

        # descarga intermitente: reintenta y termina bajando
        actualizador._pedir = guardado[5]
        intentos_descarga = []

        def _descarga_flaca(*args, **kwargs):
            intentos_descarga.append(1)
            if len(intentos_descarga) < 3:
                actualizador.ultimo_error = "URLError: red inestable"
                return None
            return destino

        actualizador.descargar = _descarga_flaca
        actualizador.instalar = _instalar_roto
        codigo, detalle = actualizador.actualizar()
        chk(len(intentos_descarga) == 3,
            "la descarga fallo %d veces y debia reintentar" % len(intentos_descarga))
        chk(codigo == "navegador",
            "con la descarga reintentada salio %r" % (codigo,))

        # descarga bien pero instalar falla -> navegador con el motivo
        actualizador._pedir = guardado[5]
        actualizador.descargar = lambda *a, **k: destino
        actualizador.instalar = _instalar_roto
        codigo, detalle = actualizador.actualizar()
        chk(codigo == "navegador", "instalacion fallida devolvio %r" % (codigo,))
        chk("SecurityException" in detalle,
            "el motivo de la instalacion fallida no se devolvio: %r" % (detalle,))

        # ni instalador ni navegador -> codigo propio, no el generico
        actualizador.abrir_url = lambda url: False
        codigo, detalle = actualizador.actualizar()
        chk(codigo == "instalo-fallo",
            "sin instalador ni navegador devolvio %r" % (codigo,))
        chk("SecurityException" in detalle,
            "el motivo de instalo-fallo no se devolvio: %r" % (detalle,))
    finally:
        (actualizador._autoclass, actualizador.consultar,
         actualizador.descargar, actualizador.instalar,
         actualizador.abrir_url, actualizador._pedir) = guardado

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
