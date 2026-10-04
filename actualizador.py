# -*- coding: utf-8 -*-
"""Actualizaciones de la app publicadas en Supabase Storage.

Flujo de un toque:
  1. consultar()     -> lee latest.json desde el bucket publico
  2. descargar()     -> baja el APK a la cache del telefono
  3. instalar()      -> abre el instalador de Android (PackageInstaller)
     y si eso falla, abrir_url() deja que el navegador lo descargue.

Solo biblioteca estandar (urllib, json, hashlib, os): python-for-android no
incluye requests ni urllib3 y no hay receta para ellos. El contexto SSL con
el bundle de CA embebido lo presta cloud_db.
"""

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from version import VERSION, VERSION_CODE

SUPABASE_URL = "https://lbhsbbwtmljzqoyrkcxj.supabase.co"
BUCKET = "apk"
URL_MANIFIESTO = SUPABASE_URL + "/storage/v1/object/public/" + BUCKET + "/latest.json"
CABECERA = "InDrive/" + str(VERSION)
REINTENTOS = 3


def _contexto():
    try:
        from cloud_db import _contexto_ssl
        return _contexto_ssl()
    except Exception:
        return None


ultimo_error = ""


def _anotar(exc):
    """Guarda el ultimo motivo de fallo para poder mostrarlo en el aviso."""
    global ultimo_error
    try:
        texto = str(exc)
    except Exception:
        texto = repr(exc)
    ultimo_error = ("%s: %s" % (type(exc).__name__, texto))[:140]


def _pedir(url, timeout):
    peticion = urllib.request.Request(url, headers={"User-Agent": CABECERA})
    return urllib.request.urlopen(peticion, timeout=timeout, context=_contexto())


def consultar(timeout=15):
    """latest.json del bucket. Devuelve el dict o None si no hay version nueva."""
    try:
        with _pedir(URL_MANIFIESTO, timeout) as respuesta:
            crudo = respuesta.read()
        info = json.loads(crudo.decode("utf-8"))
    except Exception as exc:
        _anotar(exc)
        return None
    if not isinstance(info, dict):
        return None
    try:
        info["version_code"] = int(info.get("version_code") or 0)
    except Exception:
        info["version_code"] = 0
    return info


def url_apk(info):
    """URL publica del APK que anuncia el manifiesto."""
    if not info:
        return ""
    nombre = str(info.get("apk") or "").strip()
    if not nombre:
        return ""
    return (SUPABASE_URL + "/storage/v1/object/public/" + BUCKET + "/" +
            urllib.parse.quote(nombre))


def hay_actualizacion(info):
    if not info:
        return False
    try:
        return int(info.get("version_code") or 0) > int(VERSION_CODE)
    except Exception:
        return False


def _verificar(ruta, resumen):
    if not resumen:
        return True
    try:
        digesto = hashlib.sha256()
        with open(ruta, "rb") as archivo:
            while True:
                trozo = archivo.read(1 << 20)
                if not trozo:
                    break
                digesto.update(trozo)
        return digesto.hexdigest().lower() == str(resumen).lower()
    except Exception:
        return False


def _borrar(ruta):
    try:
        if ruta and os.path.exists(ruta):
            os.remove(ruta)
    except Exception:
        pass


def descargar(url, ruta, on_avance=None, timeout=300):
    """Baja el APK hasta `ruta`. on_avance(recibido, total) mientras baja.

    Devuelve la ruta si todo salio bien y None si fallo.
    """
    if not url:
        _anotar(ValueError("sin url del APK"))
        return None
    parcial = ruta + ".parcial"
    _borrar(parcial)
    try:
        with _pedir(url, timeout) as respuesta:
            total = 0
            try:
                total = int(respuesta.headers.get("Content-Length") or 0)
            except Exception:
                total = 0
            recibido = 0
            with open(parcial, "wb") as salida:
                while True:
                    trozo = respuesta.read(64 * 1024)
                    if not trozo:
                        break
                    salida.write(trozo)
                    recibido += len(trozo)
                    if on_avance is not None:
                        try:
                            on_avance(recibido, total)
                        except Exception:
                            pass
    except Exception as exc:
        _anotar(exc)
        _borrar(parcial)
        return None
    if recibido <= 0:
        _anotar(ValueError("respuesta vacia del servidor"))
        _borrar(parcial)
        return None
    try:
        os.replace(parcial, ruta)
    except Exception as exc:
        _anotar(exc)
        _borrar(parcial)
        return None
    return ruta


def _autoclass():
    try:
        from jnius import autoclass
        return autoclass
    except Exception:
        return None


def es_android():
    return _autoclass() is not None


def permiso_instalacion():
    """True si Android ya dejo que esta app instale APK.

    Sin eso PackageInstaller.createSession() lanza SecurityException y la
    actualizacion muere. Si no se puede comprobar, seguimos adelante y
    dejamos que el propio sistema decida.
    """
    autoclass = _autoclass()
    if autoclass is None:
        return True
    try:
        actividad = autoclass("org.kivy.android.PythonActivity").mActivity
        try:
            return bool(actividad.getPackageManager().canRequestPackageInstalls())
        except Exception:
            pass
        Settings = autoclass("android.provider.Settings")
        valor = Settings.System.getInt(actividad.getContentResolver(),
                                       Settings.System.INSTALL_NON_MARKET_APPS, 0)
        return int(valor) == 1
    except Exception:
        return True


def pedir_permiso_instalacion():
    """Abre la pantalla de Android para permitir instalar apps de esta fuente."""
    autoclass = _autoclass()
    if autoclass is None:
        return False
    try:
        actividad = autoclass("org.kivy.android.PythonActivity").mActivity
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        Intent = autoclass("android.content.Intent")
        try:
            intento = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                             Uri.parse("package:" + actividad.getPackageName()))
        except Exception:
            intento = Intent(Settings.ACTION_SECURITY_SETTINGS)
        intento.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        actividad.startActivity(intento)
        return True
    except Exception as exc:
        _anotar(exc)
        return False


def directorio_apk():
    """Carpeta donde se deja el APK descargado (cache en Android)."""
    autoclass = _autoclass()
    if autoclass is not None:
        try:
            actividad = autoclass("org.kivy.android.PythonActivity").mActivity
            return actividad.getCacheDir().getAbsolutePath()
        except Exception:
            pass
    try:
        import tempfile
        return tempfile.gettempdir()
    except Exception:
        return os.getcwd()


def instalar(ruta_apk):
    """Lanza la instalacion con PackageInstaller.

    No hace falta FileProvider ni permisos especiales en el manifiesto
    aparte de REQUEST_INSTALL_PACKAGES: el propio sistema muestra el aviso
    y aplica el paquete. Devuelve True si se logro lanzar.
    """
    autoclass = _autoclass()
    if autoclass is None or not ruta_apk or not os.path.exists(ruta_apk):
        return False
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        actividad = PythonActivity.mActivity
        PackageInstaller = autoclass("android.content.pm.PackageInstaller")
        SessionParams = autoclass("android.content.pm.PackageInstaller$SessionParams")

        instalador = actividad.getPackageManager().getPackageInstaller()
        parametros = SessionParams(PackageInstaller.SESSION_MODE_FULL_INSTALL)
        sesion = instalador.createSession(parametros)
        escritura = sesion.openWrite("indrive", 0, -1)
        try:
            with open(ruta_apk, "rb") as origen:
                while True:
                    trozo = origen.read(1024 * 1024)
                    if not trozo:
                        break
                    escritura.write(trozo)
            sesion.fsync(escritura)
        finally:
            escritura.close()

        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        intento = Intent()
        intento.setAction("android.intent.action.INSTALL_SESSION_RESULT")
        intento.setPackage(actividad.getPackageName())
        banderas = int(PendingIntent.FLAG_UPDATE_CURRENT)
        try:
            # Android 12+ exige que el PendingIntent sea mutable para que el
            # sistema pueda rellenar el resultado de la instalacion.
            banderas |= int(PendingIntent.FLAG_MUTABLE)
        except Exception:
            pass
        remitente = PendingIntent.getBroadcast(actividad, 0, intento, banderas)
        sesion.commit(remitente.getIntentSender())
        return True
    except Exception as exc:
        _anotar(exc)
        return False


def abrir_url(url):
    """Abre una URL en el navegador (camino de respaldo).

    Va sin tipo MIME: con "application/vnd.android.package-archive" no hay
    ninguna actividad que la acepte y startActivity lanza ActivityNotFoundException.
    Con la URL a secas el navegador la descarga y el usuario instala desde Descargas.
    """
    autoclass = _autoclass()
    if autoclass is None or not url:
        if not url:
            _anotar(ValueError("sin url para abrir"))
        return False
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        actividad = PythonActivity.mActivity
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        intento = Intent(Intent.ACTION_VIEW)
        intento.setData(Uri.parse(url))
        intento.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        actividad.startActivity(intento)
        return True
    except Exception as exc:
        _anotar(exc)
        return False


def actualizar(on_avance=None):
    """De un toque: consulta, descarga e instala. Devuelve (codigo, detalle).

    codigos: 'sin-version' | 'al-dia' | 'sin-conexion' | 'permiso-instalar'
             | 'descarga-fallo' | 'descarga-invalida' | 'instalando'
             | 'instalo-fallo' | 'navegador'
    """
    global ultimo_error
    ultimo_error = ""
    info = consultar()
    if info is None:
        return "sin-conexion", ultimo_error
    if not hay_actualizacion(info):
        return "al-dia", str(info.get("version") or "")

    # Antes de bajar 20 MB: si Android no dejo instalar, abrimos los ajustes
    # y el usuario repite el toque.
    if es_android() and not permiso_instalacion():
        return "permiso-instalar", ""

    url = url_apk(info)
    if not url:
        _anotar(ValueError("el manifiesto no trae url del APK"))
        return "descarga-fallo", ultimo_error

    ruta = os.path.join(directorio_apk(),
                        "InDrive-%s.apk" % (info.get("version") or "nueva"))
    baja = None
    motivo = ""
    for _intento in range(max(1, int(REINTENTOS))):
        baja = descargar(url, ruta, on_avance=on_avance)
        if baja is not None:
            break
        motivo = ultimo_error
    if baja is None:
        # Bajada rota: el navegador es el respaldo, no el error final.
        if abrir_url(url):
            return "navegador", motivo
        return "descarga-fallo", motivo

    if not _verificar(baja, info.get("sha256")):
        _borrar(baja)
        return "descarga-invalida", ""

    if instalar(baja):
        return "instalando", str(info.get("version") or "")

    motivo = ultimo_error
    if abrir_url(url):
        return "navegador", motivo
    return "instalo-fallo", motivo
