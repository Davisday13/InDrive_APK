"""Sincronizacion de la BD local (SQLite) con Supabase (PostgreSQL).

Diseno local-first:
  * Todas las lecturas/escrituras de la app van a SQLite (rapido y offline).
  * Tras cada escritura se agenda un push hacia Supabase.
  * Al iniciar, si la BD local esta vacia y hay sesion, se hace pull.

La app NUNCA debe fallar por un problema de red: toda funcion de este
modulo devuelve False en lugar de lanzar excepciones.
"""

import os
import json
import time
import threading
import sqlite3
import urllib.request
import urllib.error
import urllib.parse

# Se usa urllib de la libreria estandar en vez de 'requests': python-for-android
# no tiene receta para 'requests' y el build del APK fallaria.
try:
    from cacerts import CACERT_PEM
except Exception:
    CACERT_PEM = ""

REQUESTS_OK = True

# ---- Configuracion del proyecto Supabase -------------------------------
SUPABASE_URL = "https://lbhsbbwtmljzqoyrkcxj.supabase.co"
SUPABASE_KEY = "sb_publishable_GuSF7A9pz9w0YPxlzOmuhg_Tqa2U9Q4"

TABLAS = [
    "transacciones",
    "clientes",
    "casa_pagos",
    "casa_pagos_usuario",
    "casa_aseo_pagos",
    "casa_ahorro",
    "casa_deuda_pagos",
    "casa_gastos",
]

# ---- Estados que puede leer la UI --------------------------------------
SIN_CONFIG = "SIN_CONFIG"
SIN_SESION = "SIN_SESION"
SIN_CONEXION = "SIN_CONEXION"
PENDIENTE = "PENDIENTE"
SINCRONIZADO = "SINCRONIZADO"
ERROR = "ERROR"

ESTADO = SIN_SESION
DETALLE = ""
ULTIMO_SYNC = None

DB_PATH = ""
SESSION_DIR = ""
SESSION_FILE = ""

_session = {}
_lock = threading.Lock()
_timer = None
# Si la BD local estaba vacia y el primer pull fallo, se bloquea el push
# para no borrar accidentalmente los datos que hay en la nube.
_pendiente_pull = False


# ---- Inicializacion -----------------------------------------------------
def init(db_path, session_dir):
    """Debe llamarse desde main.InDriveApp.build()."""
    global DB_PATH, SESSION_DIR, SESSION_FILE
    DB_PATH = db_path or ""
    SESSION_DIR = session_dir or ""
    SESSION_FILE = os.path.join(SESSION_DIR, "supabase_session.json") if SESSION_DIR else ""
    _cargar_sesion()
    _log("Sesion cargada" if _session.get("access_token") else "Sin sesion guardada")


def _log(msg):
    global DETALLE
    DETALLE = str(msg)[:120]
    print("[cloud] " + str(msg))


def _set_estado(estado, detalle=None):
    global ESTADO
    ESTADO = estado
    if detalle is not None:
        _log(detalle)


def avisar(mensaje):
    """Guarda un mensaje para que lo muestre la interfaz."""
    global DETALLE
    DETALLE = str(mensaje)[:120]
    print("[cloud] " + str(mensaje))


# ---- Sesion -------------------------------------------------------------
def _cargar_sesion():
    global _session
    if not SESSION_FILE or not os.path.exists(SESSION_FILE):
        _session = {}
        return
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            _session = json.load(f) or {}
    except Exception:
        _session = {}


def _guardar_sesion():
    if not SESSION_FILE:
        return
    try:
        if not os.path.isdir(SESSION_DIR):
            os.makedirs(SESSION_DIR, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(_session, f)
    except Exception as e:
        _log("No se pudo guardar la sesion: %s" % e)


def hay_sesion():
    return bool(_session.get("access_token"))


_SSL_CTX = None


def _contexto_ssl():
    """Contexto SSL con el bundle de CA embebido.

    python-for-android compila OpenSSL sin bundle de certificados, asi que
    sin esto las peticiones a Supabase fallarian con CERTIFICATE_VERIFY_FAILED.
    """
    global _SSL_CTX
    if _SSL_CTX is not None:
        return _SSL_CTX
    try:
        import ssl
    except Exception:
        return None
    try:
        ctx = ssl.create_default_context()
    except Exception:
        return None
    if CACERT_PEM:
        try:
            ctx.load_verify_locations(cadata=CACERT_PEM)
        except Exception:
            pass
    _SSL_CTX = ctx
    return _SSL_CTX


def _request(method, path, token=None, body=None, params=None, timeout=20, extra_headers=None):
    """Llamada HTTP basica. Devuelve (status, data) o (None, None)."""
    if not REQUESTS_OK:
        return None, None
    url = SUPABASE_URL + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_contexto_ssl()) as resp:
            status = resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read()
        except Exception:
            raw = b""
    except Exception:
        return None, None

    if not raw:
        return status, None
    texto = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(texto)
    except Exception:
        return status, texto


def sign_in(email, password):
    """Autentica contra Supabase Auth. Devuelve True/False."""
    global _session
    if not REQUESTS_OK:
        _set_estado(ERROR, "Sin conexion a internet")
        return False
    status, data = _request(
        "POST",
        "/auth/v1/token?grant_type=password",
        token=SUPABASE_KEY,
        body={"email": email, "password": password},
        timeout=25,
    )
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        _session = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "email": email,
            "expires_at": time.time() + (data.get("expires_in") or 3600),
        }
        _guardar_sesion()
        _set_estado(PENDIENTE, "Sesion iniciada: " + email)
        return True
    _set_estado(ERROR, "Credenciales incorrectas (%s)" % status)
    return False


def sign_out():
    global _session
    _session = {}
    if SESSION_FILE and os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass
    _set_estado(SIN_SESION, "Sesion cerrada")


def _sesion_invalida(mensaje):
    """Borra una sesion que el servidor ya no acepta."""
    global _session
    _session = {}
    if SESSION_FILE and os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass
    _set_estado(SIN_SESION, mensaje)


def _refrescar():
    """Renueva el access_token.

    True  -> token renovado.
    False -> el servidor rechazo la sesion (ya no sirve).
    None  -> no se pudo comprobar (sin red).
    """
    global _session
    rt = _session.get("refresh_token")
    if not rt:
        _sesion_invalida("La sesion expiro, vuelve a iniciar sesion")
        return False
    status, data = _request(
        "POST",
        "/auth/v1/token?grant_type=refresh_token",
        token=SUPABASE_KEY,
        body={"refresh_token": rt},
        timeout=25,
    )
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        _session["access_token"] = data.get("access_token")
        _session["refresh_token"] = data.get("refresh_token") or rt
        _session["expires_at"] = time.time() + (data.get("expires_in") or 3600)
        _guardar_sesion()
        return True
    if status in (400, 401, 403):
        _sesion_invalida("La sesion expiro, vuelve a iniciar sesion")
        return False
    return None


def sesion_valida():
    """True si la sesion guardada sigue sirviendo (o no se pudo comprobar)."""
    if not hay_sesion():
        return False
    status, _ = _api(
        "GET",
        "/rest/v1/clientes",
        params={"select": "id", "limit": "1"},
        timeout=20,
    )
    if status is None:
        return True
    if status in (401, 403):
        return False
    # 200, o 404 si el esquema aun no se ha creado: la sesion sirve.
    return True


def _api(method, path, body=None, params=None, timeout=20, extra_headers=None, _retried=False):
    """Llamada autenticada al API REST. Renueva el token si expira."""
    if not hay_sesion():
        return None, None
    status, data = _request(
        method,
        path,
        token=_session.get("access_token"),
        body=body,
        params=params,
        timeout=timeout,
        extra_headers=extra_headers,
    )
    if status is None:
        return None, None
    if status in (401, 403) and not _retried:
        renovado = _refrescar()
        if renovado:
            return _api(method, path, body, params, timeout, extra_headers, _retried=True)
        if renovado is False:
            # La sesion ya fue borrada por _refrescar()
            return status, data
        _set_estado(SIN_CONEXION, "No se pudo renovar la sesion")
        return None, None
    return status, data


# ---- Conexiones a la BD local -------------------------------------------
def _conn():
    if not DB_PATH:
        return None
    try:
        c = sqlite3.connect(DB_PATH, timeout=15)
        return c
    except Exception:
        return None


def _filas_como_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _chunks(lista, n):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


def datos_locales_vacios():
    """True si no hay ningun dato en las tablas (posible equipo nuevo)."""
    conn = _conn()
    if not conn:
        return True
    try:
        cur = conn.cursor()
        total = 0
        for t in TABLAS:
            try:
                cur.execute("SELECT COUNT(*) FROM " + t)
                total += cur.fetchone()[0]
            except Exception:
                pass
        # El cliente por defecto no cuenta como dato del usuario
        try:
            cur.execute("SELECT COUNT(*) FROM clientes")
            clientes = cur.fetchone()[0]
            if clientes <= 1:
                total -= clientes
        except Exception:
            pass
        return total <= 0
    except Exception:
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---- PUSH (local -> nube) ------------------------------------------------
def push_all():
    """Sube todo lo local a Supabase. Devuelve True si tuvo exito."""
    global ULTIMO_SYNC
    if not REQUESTS_OK:
        _set_estado(ERROR, "Sin conexion a internet")
        return False
    if not hay_sesion():
        _set_estado(SIN_SESION, "Inicia sesion para sincronizar")
        return False
    if _pendiente_pull:
        # La base local estaba vacia y la primera descarga fallo.
        # Se mezcla con la nube (sin borrar lo local) antes de subir:
        # asi no se borran datos de la nube ni se pierde lo capturado
        # sin conexion.
        if not pull_all(reemplazar=False):
            _set_estado(SIN_CONEXION, "Falta descargar la nube antes de subir")
            return False

    conn = _conn()
    if not conn:
        _set_estado(ERROR, "No se pudo abrir la base de datos")
        return False

    try:
        cur = conn.cursor()
        for tabla in TABLAS:
            try:
                cur.execute("SELECT * FROM " + tabla)
                filas = _filas_como_dicts(cur)
            except Exception as e:
                _log("Push %s: %s" % (tabla, e))
                continue

            ids_locales = [f.get("id") for f in filas if f.get("id") is not None]

            # 1) Upsert de las filas locales
            for lote in _chunks(filas, 500):
                if not lote:
                    continue
                status, _ = _api(
                    "POST",
                    "/rest/v1/" + tabla + "?on_conflict=id",
                    body=lote,
                    timeout=45,
                    extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                )
                if status is None:
                    _set_estado(SIN_CONEXION, "Sin conexion a internet")
                    return False
                if status >= 400:
                    _set_estado(ERROR, "Push %s fallo (%s)" % (tabla, status))
                    return False

            # 2) Borrar de la nube las filas que ya no existen localmente
            status, remoto = _api("GET", "/rest/v1/" + tabla + "?select=id", timeout=30)
            if status is None:
                _set_estado(SIN_CONEXION, "Sin conexion a internet")
                return False
            if status >= 400:
                _set_estado(ERROR, "Push %s fallo (%s)" % (tabla, status))
                return False

            ids_remotos = [r.get("id") for r in (remoto or []) if isinstance(r, dict)]
            borrables = [i for i in ids_remotos if i not in set(ids_locales)]
            for lote in _chunks(borrables, 200):
                if not lote:
                    continue
                q = ",".join(str(int(i)) for i in lote)
                status, _ = _api("DELETE", "/rest/v1/" + tabla + "?id=in.(" + q + ")", timeout=30)
                if status is None or status >= 400:
                    _set_estado(ERROR, "Borrado en %s fallo" % tabla)
                    return False

        ULTIMO_SYNC = time.time()
        _set_estado(SINCRONIZADO, "Sincronizado " + time.strftime("%H:%M:%S"))
        return True
    except Exception as e:
        _set_estado(ERROR, "Push: %s" % e)
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---- PULL (nube -> local) ------------------------------------------------
def pull_all(reemplazar=True):
    """Descarga la nube a la BD local. Devuelve True si tuvo exito."""
    global ULTIMO_SYNC, _pendiente_pull
    if not REQUESTS_OK:
        _set_estado(ERROR, "Sin conexion a internet")
        return False
    if not hay_sesion():
        _set_estado(SIN_SESION, "Inicia sesion para sincronizar")
        return False

    conn = _conn()
    if not conn:
        _set_estado(ERROR, "No se pudo abrir la base de datos")
        return False

    try:
        cur = conn.cursor()
        for tabla in TABLAS:
            status, filas = _api(
                "GET",
                "/rest/v1/" + tabla,
                params={"select": "*", "order": "id.asc"},
                timeout=45,
            )
            if status is None:
                _set_estado(SIN_CONEXION, "Sin conexion a internet")
                return False
            if status >= 400:
                _set_estado(ERROR, "Pull %s fallo (%s)" % (tabla, status))
                return False

            filas = filas or []
            if reemplazar:
                cur.execute("DELETE FROM " + tabla)
            for fila in filas:
                if not isinstance(fila, dict):
                    continue
                cols = list(fila.keys())
                if not cols:
                    continue
                marcadores = ",".join("?" * len(cols))
                sql = "INSERT OR REPLACE INTO %s (%s) VALUES (%s)" % (
                    tabla,
                    ",".join(cols),
                    marcadores,
                )
                try:
                    cur.execute(sql, [fila[c] for c in cols])
                except Exception as e:
                    _log("Insert %s: %s" % (tabla, e))

            _ajustar_secuencia(cur, tabla)

        conn.commit()
        _pendiente_pull = False
        ULTIMO_SYNC = time.time()
        _set_estado(SINCRONIZADO, "Datos descargados " + time.strftime("%H:%M:%S"))
        return True
    except Exception as e:
        _set_estado(ERROR, "Pull: %s" % e)
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _ajustar_secuencia(cur, tabla):
    """Asegura que los IDs nuevos no se solapen con los descargados."""
    try:
        cur.execute("SELECT IFNULL(MAX(id),0) FROM " + tabla)
        maximo = int(cur.fetchone()[0] or 0)
        if maximo <= 0:
            return
        cur.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (tabla,))
        fila = cur.fetchone()
        if fila is None:
            cur.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?,?)", (tabla, maximo)
            )
        elif int(fila[0] or 0) < maximo:
            cur.execute(
                "UPDATE sqlite_sequence SET seq=? WHERE name=?", (maximo, tabla)
            )
    except Exception:
        pass


# ---- Disparo automatico con debounce -------------------------------------
def sync_after_write():
    """Se llama tras cada commit. Agenda un push en 5 segundos."""
    global _timer
    if not REQUESTS_OK or not hay_sesion():
        _set_estado(PENDIENTE if hay_sesion() else SIN_SESION, "Guardado localmente")
        return
    _set_estado(PENDIENTE, "Pendiente de subir")
    with _lock:
        if _timer is not None:
            return
        _timer = threading.Timer(5.0, _push_en_hilo)
        _timer.daemon = True
        _timer.start()


def _push_en_hilo():
    global _timer
    with _lock:
        _timer = None
    push_all()


def push_inmediato(timeout_total=8):
    """Sincroniza ya (on_stop / on_pause). Corta si tarda demasiado."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    resultado = {"ok": False}

    def _trabajo():
        resultado["ok"] = push_all()

    h = threading.Thread(target=_trabajo, daemon=True)
    h.start()
    h.join(timeout_total)
    if h.is_alive():
        _set_estado(PENDIENTE, "Sincronizacion en curso...")
        return False
    return resultado["ok"]


def preparar_pull_si_vacio():
    """Llamar en build(). Devuelve True si hay que bajar datos de la nube."""
    global _pendiente_pull
    if not hay_sesion():
        return False
    if not datos_locales_vacios():
        return False
    _pendiente_pull = True
    _set_estado(PENDIENTE, "Base local vacia, descargando de la nube")
    return True


def forzar_pull():
    """Restauracion manual desde la nube."""
    return pull_all(reemplazar=True)


def pull_tras_login():
    """Llamar al iniciar sesion con la BD local vacia.

    Bloquea el push hasta que la descarga tenga exito, para que un fallo
    de red no convierta un push en el borrado de todo lo de la nube.
    """
    global _pendiente_pull
    _pendiente_pull = True
    return pull_all(reemplazar=True)


def nombre_estado():
    return ESTADO


def detalle_estado():
    return DETALLE


def ultimo_sync():
    return ULTIMO_SYNC
