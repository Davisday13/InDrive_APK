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


def _contexto():
    try:
        from cloud_db import _contexto_ssl
        return _contexto_ssl()
    except Exception:
        return None


def _pedir(url, timeout):
    peticion = urllib.request.Request(url, headers={"User-Agent": CABECERA})
    return urllib.request.urlopen(peticion, timeout=timeout, context=_contexto())


def consultar(timeout=15):
    """latest.json del bucket. Devuelve el dict o None si no hay version nueva."""
    try:
        with _pedir(URL_MANIFIESTO, timeout) as respuesta:
            crudo = respuesta.read()
        info = json.loads(crudo.decode("utf-8"))
    except Exception:
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
    except Exception:
        _borrar(parcial)
        return None
    if recibido <= 0:
        _borrar(parcial)
        return None
    try:
        os.replace(parcial, ruta)
    except Exception:
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
    except Exception:
        return False


def abrir_url(url):
    """Abre una URL en el navegador (camino de respaldo)."""
    autoclass = _autoclass()
    if autoclass is None or not url:
        return False
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        actividad = PythonActivity.mActivity
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        intento = Intent(Intent.ACTION_VIEW)
        intento.setDataAndType(Uri.parse(url), "application/vnd.android.package-archive")
        intento.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        actividad.startActivity(intento)
        return True
    except Exception:
        return False


def actualizar(on_avance=None):
    """De un toque: consulta, descarga e instala. Devuelve (codigo, detalle).

    codigos: 'sin-version' | 'al-dia' | 'sin-conexion' | 'descarga-fallo'
             | 'descarga-invalida' | 'instalando' | 'navegador'
    """
    info = consultar()
    if info is None:
        return "sin-conexion", ""
    if not hay_actualizacion(info):
        return "al-dia", str(info.get("version") or "")

    url = url_apk(info)
    if not url:
        return "descarga-fallo", ""

    ruta = os.path.join(directorio_apk(),
                        "InDrive-%s.apk" % (info.get("version") or "nueva"))
    baja = descargar(url, ruta, on_avance=on_avance)
    if baja is None:
        return "descarga-fallo", ""

    if not _verificar(baja, info.get("sha256")):
        _borrar(baja)
        return "descarga-invalida", ""

    if instalar(baja):
        return "instalando", str(info.get("version") or "")

    if abrir_url(url):
        return "navegador", str(info.get("version") or "")
    return "descarga-fallo", ""
