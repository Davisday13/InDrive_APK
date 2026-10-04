import os
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from kivy.uix.popup import Popup
from kivy.uix.label import Label as KivyLabel

import cloud_db
import actualizador
from version import VERSION as VERSION_APP, NOTA as NOTA_APP

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle
from kivy.core.window import Window

from widgets import (DateInput, CampoSugerencias, mostrar_selector_fecha,
                     fecha_iso, mostrar_fecha, hoy_iso, hoy_corto, parse_fecha)

# Que el teclado empuje el campo hacia arriba en vez de taparlo.
Window.softinput_mode = 'below_target'

DB_NAME = "indrive_finanzas.db"
writable_db_path = ""

# Theme colors
PRIMARY = [0.07, 0.65, 0.60, 1]
PRIMARY_DARK = [0.05, 0.55, 0.50, 1]
NEG = [0.90, 0.30, 0.35, 1]
BG = [0.98, 0.60, 0.35, 1]
SURFACE = [1, 1, 1, 1]
SURFACE_ALT = [1, 0.92, 0.82, 1]
TEXT_PRIMARY = [0.08, 0.08, 0.09, 1]
TEXT_SECONDARY = [0.3, 0.3, 0.35, 1]

# Orden de meses para SQLite
MESES_ORDER = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

class RoundedCard(BoxLayout):
    bg_color = ListProperty(SURFACE)

class MenuButton(Button):
    bg_normal = ListProperty(SURFACE_ALT)
    bg_down = ListProperty([0.90, 0.90, 0.92, 1])

class AccentButton(Button):
    bg_normal = ListProperty(PRIMARY)
    bg_down = ListProperty(PRIMARY_DARK)

def get_db_connection():
    global writable_db_path
    if not writable_db_path:
        local_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
        if os.path.exists(local_db):
            writable_db_path = local_db
        else:
            app = App.get_running_app()
            if app:
                writable_db_path = os.path.join(app.user_data_dir, DB_NAME)
            else:
                writable_db_path = os.path.join(".", DB_NAME)
    return sqlite3.connect(writable_db_path)

def close_db(conn):
    """Cierra la conexion y agenda la subida a la nube."""
    try:
        conn.commit()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    cloud_db.sync_after_write()

def mostrar_error(mensaje):
    """Muestra un popup de aviso cuando falta un campo obligatorio."""
    from kivy.uix.boxlayout import BoxLayout as BL
    from kivy.uix.button import Button as Btn
    content = BL(orientation='vertical', spacing=10, padding=15)
    lbl = KivyLabel(
        text=mensaje,
        font_size='14sp',
        halign='center',
        valign='middle',
        color=[0.08, 0.08, 0.09, 1]
    )
    lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
    btn_ok = Btn(
        text='Aceptar',
        size_hint_y=None,
        height='40dp',
        background_normal='',
        background_color=[0.07, 0.65, 0.60, 1],
        color=[1, 1, 1, 1],
        bold=True
    )
    content.add_widget(lbl)
    content.add_widget(btn_ok)
    popup = Popup(
        title='⚠️ Campo requerido',
        content=content,
        size_hint=(0.8, 0.35),
        auto_dismiss=False
    )
    btn_ok.bind(on_press=popup.dismiss)
    popup.open()

def fecha_de_campo(campo, etiqueta="fecha", por_defecto=None):
    """YYYY-MM-DD de un DateInput. Devuelve '' y avisa si no se puede usar.

    Si el campo esta vacio se devuelve `por_defecto` (o se avisa, si es None).
    """
    texto = "" if campo is None else str(getattr(campo, "text", "")).strip()
    if not texto:
        if por_defecto is not None:
            return por_defecto
        mostrar_error("Por favor ingresa la %s." % etiqueta)
        return ""
    iso = fecha_iso(texto)
    if not iso:
        mostrar_error("La %s no es válida.\nEscribe DD/MM/AAAA o usa el calendario." % etiqueta)
        try:
            campo.focus = True
        except Exception:
            pass
        return ""
    return iso

def _num(valor, por_defecto=0.0):
    try:
        return float(valor)
    except Exception:
        return por_defecto

def _entero(valor, por_defecto=0):
    try:
        return int(float(valor))
    except Exception:
        return por_defecto

def _sug_texto(tabla, columna, texto):
    """Sugerencias aprendidas de lo que ya se guardo en esa columna.

    Orden: lo mas usado primero y, a igualdad, lo mas reciente. Despues se
    filtra por lo que se esta escribiendo. `tabla` y `columna` vienen siempre
    del codigo, nunca del usuario.
    """
    if not tabla or not columna:
        return []
    if not all(ch.isalnum() or ch == '_' for ch in tabla + columna):
        return []
    consulta = ("SELECT {c} FROM {t} WHERE {c} IS NOT NULL AND {c} != '' "
                "GROUP BY {c} ORDER BY COUNT(*) DESC, MAX(id) DESC LIMIT 40"
                ).format(c=columna, t=tabla)
    try:
        conn = get_db_connection()
        filas = conn.execute(consulta).fetchall()
        conn.close()
    except Exception:
        return []
    patron = (texto or '').strip().lower()
    salida = []
    for fila in filas:
        valor = '' if fila[0] is None else str(fila[0]).strip()
        if not valor:
            continue
        if not patron or valor.lower().startswith(patron) or patron in valor.lower():
            if valor not in salida:
                salida.append(valor)
        if len(salida) >= 12:
            break
    return salida

def _sug_de(tabla, columna):
    """Fuente lista para CampoSugerencias.fuente."""
    return lambda texto: _sug_texto(tabla, columna, texto)

def _sug_fechas_casa(texto):
    """Fechas ya usadas en las tablas de la pantalla Casa."""
    return _sug_fechas(texto, ('casa_pagos_usuario', 'casa_aseo_pagos',
                               'casa_gastos', 'casa_ahorro', 'casa_deuda_pagos'))

def _sug_fechas(texto, tablas=("transacciones",)):
    """Fechas ya usadas, de la mas reciente a la mas vieja, en DD/MM/AAAA."""
    patron = (texto or '').strip()
    salida = []
    for tabla in tablas:
        if not all(ch.isalnum() or ch == '_' for ch in tabla):
            continue
        try:
            conn = get_db_connection()
            filas = conn.execute(
                "SELECT fecha FROM {t} WHERE fecha IS NOT NULL AND fecha != '' "
                "GROUP BY fecha ORDER BY fecha DESC LIMIT 30".format(t=tabla)).fetchall()
            conn.close()
        except Exception:
            continue
        for fila in filas:
            corta = mostrar_fecha(fila[0])
            if corta == '-':
                continue
            if not patron or corta.startswith(patron) or patron in corta:
                if corta not in salida:
                    salida.append(corta)
            if len(salida) >= 8:
                return salida
    return salida

def _sug_meses(texto):
    """Meses: los que ya se usaron y, despues, los doce del ano."""
    patron = (texto or '').strip().lower()
    usados = _sug_texto('casa_pagos_usuario', 'mes_corresponde', patron)
    usados += [m for m in _sug_texto('casa_pagos', 'mes_corresponde', patron)
               if m not in usados]
    salida = []
    for valor in usados + [m.capitalize() for m in MESES_ORDER]:
        if not valor:
            continue
        if not patron or valor.lower().startswith(patron):
            if valor not in salida:
                salida.append(valor)
        if len(salida) >= 12:
            break
    return salida

def editar_registro(titulo, campos, on_guardar, valores=None, texto_boton="Guardar"):
    """Formulario generico en un popup para corregir un registro ya guardado.

    campos: lista de {"id", "label", "tipo"} con tipo "texto" | "fecha" | "numero".
    valores: dict id -> valor inicial.
    on_guardar: recibe un dict id -> texto; las fechas llegan ya en AAAA-MM-DD.
    Devuelve el Popup abierto (o None si no hay campos).
    """
    if not campos:
        return None
    valores = valores or {}
    entradas = {}

    scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, size_hint_y=1)
    rejilla = GridLayout(cols=2, spacing=8, padding=[4, 4], size_hint_y=None)
    rejilla.bind(minimum_height=rejilla.setter('height'))
    scroll.add_widget(rejilla)

    for campo in campos:
        cid = campo['id']
        etiqueta = campo.get('label', cid)
        tipo = campo.get('tipo', 'texto')
        rotulo = Label(text=etiqueta, font_size='12sp', color=list(TEXT_SECONDARY),
                       size_hint_y=None, height='34dp', halign='left', valign='middle')
        rotulo.bind(size=lambda inst, v: setattr(inst, 'text_size', v))
        rejilla.add_widget(rotulo)

        inicial = valores.get(cid, '')
        inicial = '' if inicial is None else str(inicial).strip()
        if tipo == 'fecha' and inicial:
            inicial = mostrar_fecha(inicial)
            if inicial == '-':
                inicial = ''
        if tipo == 'fecha':
            entrada = DateInput(text=inicial, size_hint_y=None, height='36dp', font_size='13sp')
            entrada.fuente = _sug_fechas
        else:
            entrada = TextInput(text=inicial, hint_text=campo.get('hint', ''),
                                multiline=False, size_hint_y=None, height='36dp',
                                font_size='13sp',
                                background_color=[1, 1, 1, 1],
                                foreground_color=list(TEXT_PRIMARY),
                                cursor_color=list(PRIMARY),
                                padding=[8, 8])
        rejilla.add_widget(entrada)
        entradas[cid] = (etiqueta, tipo, entrada)

    contenido = BoxLayout(orientation='vertical', spacing=8, padding=10)
    contenido.add_widget(Label(text=titulo, font_size='15sp', bold=True,
                               color=list(PRIMARY), size_hint_y=None, height='28dp'))
    contenido.add_widget(scroll)

    botones = BoxLayout(size_hint_y=None, height='40dp', spacing=10)
    btn_cancelar = Button(text='Cancelar', background_color=[0.9, 0.3, 0.35, 1],
                          color=[1, 1, 1, 1], font_size='13sp', bold=True)
    btn_guardar = Button(text=texto_boton, background_color=list(PRIMARY),
                         color=[1, 1, 1, 1], font_size='13sp', bold=True)
    botones.add_widget(btn_cancelar)
    botones.add_widget(btn_guardar)
    contenido.add_widget(botones)

    popup = Popup(title='Editar', content=contenido, size_hint=(0.94, 0.86), auto_dismiss=True)
    btn_cancelar.bind(on_press=popup.dismiss)

    def guardar(*args):
        salida = {}
        for cid, (etiqueta, tipo, entrada) in entradas.items():
            texto = entrada.text.strip()
            if tipo == 'fecha' and texto:
                iso = fecha_iso(texto)
                if not iso:
                    mostrar_error("La fecha de «%s» no es válida." % etiqueta)
                    entrada.focus = True
                    return
                salida[cid] = iso
            elif tipo == 'numero':
                if texto:
                    try:
                        float(texto)
                    except Exception:
                        mostrar_error("«%s» debe ser un número.\nEjemplo: 15.00" % etiqueta)
                        entrada.focus = True
                        return
                salida[cid] = texto
            else:
                salida[cid] = texto
        popup.dismiss()
        on_guardar(salida)

    btn_guardar.bind(on_press=guardar)
    popup.open()
    return popup

def init_database():
    """Inicializa la base de datos VACÍA - sin datos automáticos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Crear tablas (solo transacciones ahora)
    cursor.execute("""
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
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            deuda_total REAL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_pago TEXT,
            monto REAL DEFAULT 0,
            mes_corresponde TEXT,
            pendiente REAL DEFAULT 0,
            pago_hasta TEXT,
            saldo_pendiente REAL DEFAULT 0,
            tasa_aseo REAL DEFAULT 0,
            deposito REAL DEFAULT 0,
            luz REAL DEFAULT 0,
            gasto_fecha TEXT,
            gasto_concepto TEXT,
            gasto_monto REAL DEFAULT 0,
            pago_adic_fecha TEXT,
            pago_adic_monto REAL DEFAULT 0,
            ahorro REAL DEFAULT 0,
            mes_pendiente TEXT,
            pendiente_extra REAL DEFAULT 0,
            pendiente_por_pagar REAL DEFAULT 0,
            cliente_id INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_pagos_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            monto REAL DEFAULT 0,
            mes_corresponde TEXT,
            pendiente REAL DEFAULT 0,
            pago_hasta TEXT,
            cliente_id INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_aseo_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            monto_pagado REAL DEFAULT 0,
            cliente_id INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_ahorro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            monto REAL DEFAULT 0,
            concepto TEXT,
            ahorro REAL DEFAULT 0,
            cliente_id INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_deuda_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            monto_pagado REAL DEFAULT 0,
            descripcion TEXT,
            cliente_id INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casa_gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            concepto TEXT,
            monto REAL DEFAULT 0,
            tipo TEXT DEFAULT 'casa',
            cliente_id INTEGER DEFAULT 1
        )
    """)
    
    # Agregar columna cliente_id si no existe en tablas existentes
    for tabla in ['casa_pagos', 'casa_pagos_usuario', 'casa_aseo_pagos', 'casa_ahorro', 'casa_deuda_pagos', 'casa_gastos']:
        try:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN cliente_id INTEGER DEFAULT 1")
        except:
            pass

    # Agregar columna deuda_total si no existe en clientes (BDs antiguas)
    try:
        cursor.execute("ALTER TABLE clientes ADD COLUMN deuda_total REAL DEFAULT 0")
    except:
        pass

    # Insertar cliente por defecto si no existe
    cursor.execute("SELECT count(*) FROM clientes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", ("Jose Luis Cubilla",))
    
    close_db(conn)
    print("Base de datos inicializada")

def importar_casa_pagos():
    import os
    xlsx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Libro1.xlsx")
    if not os.path.exists(xlsx_path):
        print("Libro1.xlsx no encontrado")
        return False
    try:
        import openpyxl
    except ImportError:
        print("openpyxl no instalado")
        return False

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM casa_pagos")
    if cur.fetchone()[0] > 0:
        conn.close()
        return False

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb['Hoja1']

    def pd(val):
        if val is None: return ""
        if isinstance(val, str): return val[:20]
        try: return val.strftime("%Y-%m-%d")
        except: return str(val)[:20]

    def pf(val):
        if val is None: return 0.0
        try: return float(val)
        except: return 0.0

    def ps(val):
        if val is None: return ""
        return str(val).strip()

    for row in range(5, 50):
        fp = pd(ws.cell(row=row, column=1).value)
        monto = pf(ws.cell(row=row, column=2).value)
        mes = ps(ws.cell(row=row, column=3).value)
        pend = pf(ws.cell(row=row, column=4).value)
        hasta = pd(ws.cell(row=row, column=5).value)
        saldo = pf(ws.cell(row=row, column=7).value)
        tasa = pf(ws.cell(row=row, column=9).value)
        depo = pf(ws.cell(row=row, column=11).value)
        luz = pf(ws.cell(row=row, column=13).value)
        gf = pd(ws.cell(row=row, column=15).value)
        gc = ps(ws.cell(row=row, column=16).value)
        gm = pf(ws.cell(row=row, column=17).value)
        af = pd(ws.cell(row=row, column=22).value)
        am = pf(ws.cell(row=row, column=23).value)
        ahorro = pf(ws.cell(row=row, column=25).value)
        mp = ps(ws.cell(row=row, column=32).value)
        pe = pf(ws.cell(row=row, column=34).value)
        pp = pf(ws.cell(row=row, column=37).value)

        has = any([fp, monto, mes, pend, saldo, tasa, depo, luz, gc, gm, am, ahorro, mp, pe, pp])
        if not has:
            continue

        cur.execute("""INSERT INTO casa_pagos (
            cliente_id, fecha_pago, monto, mes_corresponde, pendiente, pago_hasta,
            saldo_pendiente, tasa_aseo, deposito, luz,
            gasto_fecha, gasto_concepto, gasto_monto,
            pago_adic_fecha, pago_adic_monto,
            ahorro, mes_pendiente, pendiente_extra, pendiente_por_pagar
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (1, fp, monto, mes, pend, hasta, saldo, tasa, depo, luz,
             gf, gc, gm, af, am, ahorro, mp, pe, pp))

    close_db(conn)
    print("Pagos de casa importados correctamente")
    return True

# --- KV Language ---
KV = """
#:import datetime datetime.datetime
#:set PRIMARY [0.07, 0.65, 0.60, 1]
#:set NEG [0.90, 0.30, 0.35, 1]

<RoundedCard>:
    orientation: 'vertical'
    padding: [16, 12]
    spacing: 6
    canvas.before:
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            size: self.size
            pos: self.pos
            radius: [12]

<MenuButton>:
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: self.bg_normal if self.state == 'normal' else self.bg_down
        RoundedRectangle:
            size: self.size
            pos: self.pos
            radius: [8]
    color: 0.08, 0.08, 0.09, 1
    font_size: '14sp'
    bold: True

<AccentButton>:
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: self.bg_normal if self.state == 'normal' else self.bg_down
        RoundedRectangle:
            size: self.size
            pos: self.pos
            radius: [8]
    color: 1, 1, 1, 1
    font_size: '15sp'
    bold: True

<CustomTextInput@TextInput>:
    background_color: 1, 1, 1, 1
    foreground_color: 0.08, 0.08, 0.09, 1
    cursor_color: 0.07, 0.65, 0.60, 1
    font_size: '14sp'
    padding: [10, 8]
    multiline: False

<DateInput>:
    background_color: 1, 1, 1, 1
    foreground_color: 0.08, 0.08, 0.09, 1
    cursor_color: 0.07, 0.65, 0.60, 1
    font_size: '14sp'
    multiline: False

<CampoSugerencias>:
    background_color: 1, 1, 1, 1
    foreground_color: 0.08, 0.08, 0.09, 1
    cursor_color: 0.07, 0.65, 0.60, 1
    font_size: '14sp'
    padding: [10, 8]
    multiline: False

<FormLabel@Label>:
    font_size: '12sp'
    color: 0.08, 0.08, 0.09, 1
    halign: 'left'
    valign: 'middle'
    size_hint_y: None
    height: self.texture_size[1]
    text_size: self.width, None

ScreenManager:
    DashboardScreen:
    AhorroScreen:
    CarroScreen:
    CasaScreen:
    CalendarScreen:
    StatsScreen:

<DashboardScreen>:
    name: 'dashboard'
    BoxLayout:
        orientation: 'vertical'
        padding: 16
        spacing: 16
        canvas.before:
            Color:
                rgba: [0.98, 0.60, 0.35, 1]
            Rectangle:
                size: self.size
                pos: self.pos

        BoxLayout:
            size_hint_y: None
            height: '50dp'
            Label:
                text: "INDRIVE FINANZAS"
                font_size: '20sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1
                halign: 'left'
                text_size: self.width, None

        BoxLayout:
            size_hint_y: None
            height: '34dp'
            spacing: 8
            Label:
                text: root.sync_estado
                font_size: '9sp'
                color: 0.3, 0.3, 0.35, 1
                halign: 'left'
                valign: 'middle'
                text_size: self.width, None
            Button:
                text: 'Sincronizar'
                size_hint_x: None
                width: '86dp'
                font_size: '9sp'
                background_normal: ''
                background_color: [1, 1, 1, 1]
                color: 0.07, 0.65, 0.60, 1
                bold: True
                on_press: root._sincronizar_ahora()
            Button:
                text: 'Restaurar'
                size_hint_x: None
                width: '80dp'
                font_size: '9sp'
                background_normal: ''
                background_color: [1, 1, 1, 1]
                color: 0.90, 0.30, 0.35, 1
                bold: True
                on_press: root._restaurar_desde_nube()
            Button:
                text: 'Salir'
                size_hint_x: None
                width: '58dp'
                font_size: '9sp'
                background_normal: ''
                background_color: [1, 1, 1, 1]
                color: 0.3, 0.3, 0.35, 1
                bold: True
                on_press: root._cerrar_sesion()

        ScrollView:
            size_hint_y: 0.60
            do_scroll_x: False
            BoxLayout:
                id: contenido_dashboard
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 12
                padding: [0, 5, 0, 5]

                BoxLayout:
                    id: caja_actualizacion
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: 6

                RoundedCard:
                    size_hint_y: None
                    height: '90dp'
                    bg_color: [1, 1, 1, 1]
                    Label:
                        text: "AHORROS INDRIVE"
                        font_size: '12sp'
                        bold: True
                        color: 0.3, 0.3, 0.35, 1
                        size_hint_y: None
                        height: '20dp'
                    Label:
                        text: root.balance_ahorro
                        font_size: '28sp'
                        bold: True
                        color: 0.07, 0.65, 0.60, 1

                RoundedCard:
                    size_hint_y: None
                    height: '90dp'
                    bg_color: [1, 1, 1, 1]
                    Label:
                        text: "FONDO DEL CARRO"
                        font_size: '12sp'
                        bold: True
                        color: 0.3, 0.3, 0.35, 1
                        size_hint_y: None
                        height: '20dp'
                    Label:
                        text: root.balance_carro
                        font_size: '28sp'
                        bold: True
                        color: root.color_carro

        GridLayout:
            cols: 2
            spacing: 10
            size_hint_y: 0.40
            MenuButton:
                text: "Ahorro\\nInDrive"
                bg_normal: [0.07, 0.65, 0.60, 1]
                color: 1, 1, 1, 1
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                on_press: root.manager.current = 'ahorro'
            MenuButton:
                text: "Uso del\\nCarro"
                bg_normal: [1, 1, 1, 1]
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                on_press: root.manager.current = 'carro'

            MenuButton:
                text: "Alquiler\\nCasa"
                bg_normal: [1, 1, 1, 1]
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                on_press: root.manager.current = 'casa'
            MenuButton:
                text: "Calendario"
                bg_normal: [1, 1, 1, 1]
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                on_press: root.manager.current = 'calendar'

            MenuButton:
                text: "Estadísticas"
                bg_normal: [1, 1, 1, 1]
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                on_press: root.manager.current = 'stats'

<AhorroScreen>:
    name: 'ahorro'
    BoxLayout:
        orientation: 'vertical'
        padding: 12
        spacing: 10
        canvas.before:
            Color:
                rgba: [0.98, 0.60, 0.35, 1]
            Rectangle:
                size: self.size
                pos: self.pos

        BoxLayout:
            size_hint_y: None
            height: '40dp'
            Button:
                text: "< Volver"
                size_hint_x: None
                width: '80dp'
                background_color: 0, 0, 0, 0
                color: 0.08, 0.08, 0.09, 1
                font_size: '14sp'
                bold: True
                on_press: root.manager.current = 'dashboard'
            Label:
                text: "Ahorros InDrive"
                font_size: '16sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1

        RoundedCard:
            size_hint_y: None
            height: '65dp'
            bg_color: [1, 1, 1, 1]
            Label:
                text: "Saldo: " + root.balance_ahorro
                font_size: '18sp'
                bold: True
                color: 0.07, 0.65, 0.60, 1

        BoxLayout:
            size_hint_y: None
            height: '35dp'
            spacing: 5
            Button:
                id: tab_viaje_btn
                text: "Viaje"
                background_color: 0,0,0,0
                color: 0.08, 0.08, 0.09, 1
                bold: True
                canvas.before:
                    Color:
                        rgba: [0.07, 0.65, 0.60, 0.3] if root.current_form == 'viaje' else [0.95, 0.95, 0.96, 1]
                    RoundedRectangle:
                        size: self.size
                        pos: self.pos
                        radius: [5]
                on_press: root.current_form = 'viaje'
            Button:
                id: tab_gasto_btn
                text: "Otro"
                background_color: 0,0,0,0
                color: 0.08, 0.08, 0.09, 1
                bold: True
                canvas.before:
                    Color:
                        rgba: [0.07, 0.65, 0.60, 0.3] if root.current_form == 'otro' else [0.95, 0.95, 0.96, 1]
                    RoundedRectangle:
                        size: self.size
                        pos: self.pos
                        radius: [5]
                on_press: root.current_form = 'otro'

        BoxLayout:
            id: form_container
            orientation: 'vertical'
            size_hint_y: None
            height: '240dp'
            padding: [8, 8]
            spacing: 8
            canvas.before:
                Color:
                    rgba: [1, 1, 1, 1]
                RoundedRectangle:
                    size: self.size
                    pos: self.pos
                    radius: [8]

        Label:
            text: "Últimos Movimientos"
            font_size: '13sp'
            bold: True
            color: 0.08, 0.08, 0.09, 1
            size_hint_y: None
            height: '20dp'

        ScrollView:
            BoxLayout:
                id: list_transacciones
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 6


<CarroScreen>:
    name: 'carro'
    BoxLayout:
        orientation: 'vertical'
        padding: 12
        spacing: 10
        canvas.before:
            Color:
                rgba: [0.98, 0.60, 0.35, 1]
            Rectangle:
                size: self.size
                pos: self.pos

        BoxLayout:
            size_hint_y: None
            height: '40dp'
            Button:
                text: "< Volver"
                size_hint_x: None
                width: '80dp'
                background_color: 0, 0, 0, 0
                color: 0.08, 0.08, 0.09, 1
                font_size: '14sp'
                bold: True
                on_press: root.manager.current = 'dashboard'
            Label:
                text: "Fondo del Carro"
                font_size: '16sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1

        RoundedCard:
            size_hint_y: None
            height: '65dp'
            bg_color: [1, 1, 1, 1]
            Label:
                text: "Saldo: " + root.balance_carro
                font_size: '18sp'
                bold: True
                color: root.color_carro

        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: '260dp'
            padding: [10, 10]
            spacing: 8
            canvas.before:
                Color:
                    rgba: [1, 1, 1, 1]
                RoundedRectangle:
                    size: self.size
                    pos: self.pos
                    radius: [8]

            GridLayout:
                cols: 2
                spacing: 8
                size_hint_y: None
                height: '190dp'

                FormLabel:
                    text: "Fecha:"
                DateInput:
                    id: c_fecha
                    text: datetime.now().strftime("%d/%m/%Y")
                FormLabel:
                    text: "Tipo:"
                BoxLayout:
                    spacing: 5
                    Button:
                        id: btn_c_ingreso
                        text: "Ingreso"
                        font_size: '11sp'
                        bold: True
                        background_color: 0,0,0,0
                        color: 0.08, 0.08, 0.09, 1
                        canvas.before:
                            Color:
                                rgba: [0.07, 0.65, 0.60, 1] if root.var_c_tipo == 'Ingreso' else [0.95, 0.95, 0.96, 1]
                            RoundedRectangle:
                                size: self.size
                                pos: self.pos
                                radius: [4]
                        on_press: root.var_c_tipo = 'Ingreso'
                    Button:
                        id: btn_c_gasto
                        text: "Gasto"
                        font_size: '11sp'
                        bold: True
                        background_color: 0,0,0,0
                        color: 0.08, 0.08, 0.09, 1
                        canvas.before:
                            Color:
                                rgba: [0.90, 0.30, 0.35, 1] if root.var_c_tipo == 'Gasto' else [0.95, 0.95, 0.96, 1]
                            RoundedRectangle:
                                size: self.size
                                pos: self.pos
                                radius: [4]
                        on_press: root.var_c_tipo = 'Gasto'

                FormLabel:
                    text: "Monto:"
                CustomTextInput:
                    id: c_monto
                    hint_text: "0.00"

                FormLabel:
                    text: "Categoría:"
                BoxLayout:
                    Button:
                        id: c_cat_btn
                        text: root.var_c_cat
                        font_size: '11sp'
                        background_color: 0,0,0,0
                        color: 0.08, 0.08, 0.09, 1
                        canvas.before:
                            Color:
                                rgba: [0.3, 0.3, 0.35, 0.15]
                            RoundedRectangle:
                                size: self.size
                                pos: self.pos
                                radius: [4]
                        on_press: root.toggle_c_category()

                FormLabel:
                    text: "Descripción:"
                CampoSugerencias:
                    id: c_desc
                    hint_text: "Nota..."

            AccentButton:
                text: "Guardar"
                bg_normal: [0.07, 0.65, 0.60, 1]
                size_hint_y: None
                height: '40dp'
                on_press: root.save_carro()

        Label:
            text: "Últimos Movimientos"
            font_size: '13sp'
            bold: True
            color: 0.08, 0.08, 0.09, 1
            size_hint_y: None
            height: '20dp'

        ScrollView:
            BoxLayout:
                id: list_carro
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 6


<StatsScreen>:
    name: 'stats'
    ScrollView:
        do_scroll_x: False
        do_scroll_y: True
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            padding: 12
            spacing: 12
            canvas.before:
                Color:
                    rgba: [0.98, 0.60, 0.35, 1]
                Rectangle:
                    size: self.size
                    pos: self.pos

            BoxLayout:
                size_hint_y: None
                height: '45dp'
            Button:
                text: "< Volver"
                size_hint_x: None
                width: '80dp'
                background_color: 0, 0, 0, 0
                color: 0.08, 0.08, 0.09, 1
                font_size: '14sp'
                bold: True
                on_press: root._volver_atras()
                Label:
                    text: "ESTADÍSTICAS"
                    font_size: '16sp'
                    bold: True
                    color: 0.08, 0.08, 0.09, 1
                    halign: 'center'

            BoxLayout:
                size_hint_y: None
                height: '70dp'
                spacing: 10
                RoundedCard:
                    bg_color: [1, 1, 1, 1]
                    Label:
                        text: "Mejor Mes"
                        font_size: '11sp'
                        color: 0.3, 0.3, 0.35, 1
                    Label:
                        id: lbl_best_month
                        text: "-"
                        font_size: '16sp'
                        bold: True
                        color: 0.07, 0.65, 0.60, 1
                RoundedCard:
                    bg_color: [1, 1, 1, 1]
                    Label:
                        text: "Eficiencia"
                        font_size: '11sp'
                        color: 0.3, 0.3, 0.35, 1
                    Label:
                        id: lbl_efficiency
                        text: "0.00/KM"
                        font_size: '16sp'
                        bold: True
                        color: 0.07, 0.65, 0.60, 1

            RoundedCard:
                size_hint_y: None
                height: '240dp'
                bg_color: [1, 1, 1, 1]
                padding: [10, 15, 10, 10]
                BoxLayout:
                    orientation: 'vertical'
                    Label:
                        text: "Comparativa Mensual"
                        font_size: '13sp'
                        bold: True
                        color: 0.08, 0.08, 0.09, 1
                        size_hint_y: None
                        height: '20dp'
                    
                    Widget:
                        id: chart_canvas

                    BoxLayout:
                        id: chart_months
                        orientation: 'horizontal'
                        size_hint_y: None
                        height: '20dp'
                        padding: [40, 0]

                    BoxLayout:
                        size_hint_y: None
                        height: '20dp'
                        spacing: 15
                        padding: [20, 0]
                        BoxLayout:
                            spacing: 5
                            canvas.before:
                                Color:
                                    rgba: [0.07, 0.65, 0.60, 1]
                                RoundedRectangle:
                                    pos: self.x, self.y + 4
                                    size: 10, 10
                                    radius: [2]
                            Label:
                                text: "Ahorro"
                                font_size: '10sp'
                                color: 0.08, 0.08, 0.09, 1
                        BoxLayout:
                            spacing: 5
                            canvas.before:
                                Color:
                                    rgba: [0.90, 0.30, 0.35, 1]
                                RoundedRectangle:
                                    pos: self.x, self.y + 4
                                    size: 10, 10
                                    radius: [2]
                            Label:
                                text: "Carro"
                                font_size: '10sp'
                                color: 0.08, 0.08, 0.09, 1

            RoundedCard:
                id: daily_profits_card
                size_hint_y: None
                height: self.minimum_height
                bg_color: [1, 1, 1, 1]
                padding: [12, 12]
                spacing: 8
                
                Label:
                    text: "Ganancias Diarias"
                    font_size: '14sp'
                    bold: True
                    color: 0.08, 0.08, 0.09, 1
                    size_hint_y: None
                    height: '25dp'
                
                BoxLayout:
                    id: list_daily_profits
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: 6

<CalendarScreen>:
    name: 'calendar'
    BoxLayout:
        orientation: 'vertical'
        padding: 16
        spacing: 12
        canvas.before:
            Color:
                rgba: [0.98, 0.60, 0.35, 1]
            Rectangle:
                size: self.size
                pos: self.pos

        BoxLayout:
            size_hint_y: None
            height: '45dp'
            spacing: 10
            Button:
                text: "< Volver"
                size_hint_x: None
                width: '80dp'
                background_color: 0, 0, 0, 0
                color: 0.08, 0.08, 0.09, 1
                font_size: '14sp'
                bold: True
                on_press: root.manager.current = 'dashboard'
            Label:
                text: "CALENDARIO DE GANANCIAS"
                font_size: '16sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
            Widget:
                size_hint_x: None
                width: '80dp'

        BoxLayout:
            size_hint_y: None
            height: '40dp'
            spacing: 6
            Button:
                text: "◀"
                size_hint_x: None
                width: '44dp'
                background_normal: ''
                background_color: [1, 1, 1, 0.85]
                color: 0.08, 0.08, 0.09, 1
                font_size: '16sp'
                bold: True
                on_press: root.go_prev_month()
            Label:
                id: lbl_mes_anio
                text: root.mes_anio_label
                font_size: '15sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'
                valign: 'middle'
            Button:
                text: "▶"
                size_hint_x: None
                width: '44dp'
                background_normal: ''
                background_color: [1, 1, 1, 0.85]
                color: 0.08, 0.08, 0.09, 1
                font_size: '16sp'
                bold: True
                on_press: root.go_next_month()

        GridLayout:
            cols: 7
            size_hint_y: None
            height: '25dp'
            spacing: 4
            Label:
                text: "Lun"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Mar"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Mié"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Jue"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Vie"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Sáb"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1
            Label:
                text: "Dom"
                bold: True
                font_size: '11sp'
                color: 0.08, 0.08, 0.09, 1

        ScrollView:
            do_scroll_x: False
            GridLayout:
                id: calendar_grid
                cols: 7
                size_hint_y: None
                height: self.minimum_height
                spacing: 6

<CasaScreen>:
    name: 'casa'
    BoxLayout:
        orientation: 'vertical'
        padding: 12
        spacing: 8
        canvas.before:
            Color:
                rgba: [0.98, 0.60, 0.35, 1]
            Rectangle:
                size: self.size
                pos: self.pos

        BoxLayout:
            size_hint_y: None
            height: '45dp'
            spacing: 10
            Button:
                text: "< Volver"
                size_hint_x: None
                width: '80dp'
                background_color: 0, 0, 0, 0
                color: 0.08, 0.08, 0.09, 1
                font_size: '14sp'
                bold: True
                on_press: root._volver_atras()
            Label:
                text: "ALQUILER CASA"
                font_size: '16sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                id: container_contenido
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 8
                padding: [0, 4, 0, 4]
"""

# --- SCREENS ---

class DashboardScreen(Screen):
    balance_ahorro = StringProperty("$0.00")
    balance_carro = StringProperty("$0.00")
    color_carro = ObjectProperty([0.07, 0.65, 0.60, 1])
    sync_estado = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sync_ok = False
        self._aviso_info = None
        self._aviso_consultado = False
        self._aviso_titulo = None
        self._aviso_nota = None
        self._aviso_nota_base = ""
        Clock.schedule_interval(self._actualizar_estado_sync, 2)
        Clock.schedule_once(lambda dt: self._consultar_actualizacion(), 5)

    # ------------------------------------------------ actualizaciones ----
    def _consultar_actualizacion(self, *args):
        if self._aviso_consultado:
            return
        self._aviso_consultado = True

        def _trabajo():
            info = actualizador.consultar()
            if actualizador.hay_actualizacion(info):
                Clock.schedule_once(lambda dt: self._mostrar_aviso(info), 0)

        threading.Thread(target=_trabajo, daemon=True).start()

    def _mostrar_aviso(self, info):
        try:
            caja = self.ids.caja_actualizacion
        except Exception:
            return
        if caja.children or not info:
            return
        self._aviso_info = info
        version = str(info.get('version') or '')
        nota = str(info.get('nota') or NOTA_APP)

        tarjeta = RoundedCard(size_hint_y=None, height='104dp',
                              bg_color=[1, 1, 1, 1])
        tarjeta.padding = [10, 6]
        tarjeta.spacing = 4

        fila_titulo = BoxLayout(size_hint_y=None, height='26dp', spacing=6)
        self._aviso_titulo = Label(
            text="Nueva versión %s" % version, font_size='13sp', bold=True,
            color=list(PRIMARY), halign='left', valign='middle', size_hint_x=1)
        self._aviso_titulo.bind(size=lambda i, v: setattr(i, 'text_size', v))
        btn_cerrar = Button(text="✕", size_hint_x=None, width='26dp',
                            background_color=[0, 0, 0, 0], color=list(TEXT_SECONDARY),
                            font_size='13sp', bold=True)
        btn_cerrar.bind(on_press=lambda b: self._ocultar_aviso())
        fila_titulo.add_widget(self._aviso_titulo)
        fila_titulo.add_widget(btn_cerrar)

        texto_nota = Label(text=nota, font_size='10sp', color=list(TEXT_SECONDARY),
                           halign='left', valign='top', size_hint_y=None, height='34dp')
        texto_nota.bind(size=lambda i, v: setattr(i, 'text_size', v))
        self._aviso_nota = texto_nota
        self._aviso_nota_base = nota

        fila_acciones = BoxLayout(size_hint_y=None, height='34dp', spacing=8)
        btn_actualizar = Button(text="Actualizar ahora", font_size='12sp', bold=True,
                                background_color=list(PRIMARY), color=[1, 1, 1, 1])
        btn_despues = Button(text="Más tarde", font_size='12sp',
                             background_color=[0.95, 0.95, 0.96, 1],
                             color=list(TEXT_SECONDARY))
        btn_despues.bind(on_press=lambda b: self._ocultar_aviso())
        btn_actualizar.bind(on_press=lambda b: self._actualizar_ahora())
        fila_acciones.add_widget(btn_actualizar)
        fila_acciones.add_widget(btn_despues)

        tarjeta.add_widget(fila_titulo)
        tarjeta.add_widget(texto_nota)
        tarjeta.add_widget(fila_acciones)
        caja.add_widget(tarjeta)

    def _ocultar_aviso(self, *args):
        try:
            caja = self.ids.caja_actualizacion
            caja.clear_widgets()
        except Exception:
            pass
        self._aviso_info = None

    def _actualizar_ahora(self, *args):
        if self._aviso_info is None:
            return
        self._aviso_titulo.text = "Descargando la actualización…"
        info = dict(self._aviso_info)

        def avance(recibido, total):
            if total > 0:
                pct = int(recibido * 100 / total)
                Clock.schedule_once(
                    lambda dt: setattr(self._aviso_titulo, 'text',
                                       "Descargando… %d%%" % pct), 0)

        def _trabajo():
            codigo, detalle = actualizador.actualizar(on_avance=avance)
            Clock.schedule_once(lambda dt: self._fin_actualizacion(codigo, detalle), 0)

        threading.Thread(target=_trabajo, daemon=True).start()

    def _fin_actualizacion(self, codigo, detalle):
        if self._aviso_titulo is None:
            return
        mensajes = {
            'sin-conexion': "No se pudo consultar la versión nueva. Revisa la conexión.",
            'sin-version': "No se pudo consultar la versión nueva.",
            'permiso-instalar': "Falta permitir instalar apps de esta fuente.",
            'descarga-fallo': "No se pudo descargar el APK.",
            'descarga-invalida': "El archivo descargado no coincide con el publicado.",
            'instalando': "Abriendo el instalador de Android…",
            'instalo-fallo': "No se pudo instalar el APK descargado.",
            'navegador': "Se abrió el navegador para descargar la actualización.",
            'al-dia': "Ya tienes la última versión.",
        }
        self._aviso_titulo.text = mensajes.get(codigo, codigo)

        if codigo == 'permiso-instalar':
            self._decir_nota("Android pide autorizar esta app. Aceptá y tocá "
                             "«Actualizar ahora» otra vez.")
            actualizador.pedir_permiso_instalacion()
            return
        if codigo in ('instalando', 'al-dia'):
            self._decir_nota(self._aviso_nota_base)
            return
        self._decir_nota(detalle or self._aviso_nota_base)

    def _decir_nota(self, texto):
        """Muestra un mensaje corto en la linea de nota del aviso."""
        if self._aviso_nota is None or not texto:
            return
        self._aviso_nota.text = str(texto)[:150]

    def _actualizar_estado_sync(self, *args):
        try:
            if not cloud_db.hay_sesion():
                self.sync_estado = ("Sin sesion: los datos estan solo en este "
                                    "telefono   · v%s" % VERSION_APP)
            else:
                est = cloud_db.nombre_estado()
                if est == cloud_db.SINCRONIZADO:
                    txt = "Sincronizado"
                elif est == cloud_db.PENDIENTE:
                    txt = "Pendiente de subir"
                elif est == cloud_db.SIN_CONEXION:
                    txt = "Sin conexion"
                elif est == cloud_db.ERROR:
                    txt = "Error: " + cloud_db.detalle_estado()
                else:
                    txt = est
                if cloud_db.ultimo_sync():
                    txt += "  " + time.strftime("%H:%M", time.localtime(cloud_db.ultimo_sync()))
                self.sync_estado = txt + "   · v%s" % VERSION_APP
        except Exception:
            pass

    def _sincronizar_ahora(self):
        def _trabajo():
            cloud_db.push_all()
            Clock.schedule_once(lambda dt: self._actualizar_estado_sync(), 0)
        threading.Thread(target=_trabajo, daemon=True).start()

    def _restaurar_desde_nube(self):
        content = BoxLayout(orientation='vertical', spacing=10, padding=15)
        lbl = KivyLabel(
            text="Se descargaran los datos guardados en la nube y\n"
                 "reemplazaran los de este telefono.\n\nContinuar?",
            font_size='13sp', color=[0.08, 0.08, 0.09, 1]
        )
        lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
        btns = BoxLayout(size_hint_y=None, height='40dp', spacing=10)
        ref = [None]

        def _no(b):
            ref[0].dismiss()

        def _si(b):
            ref[0].dismiss()
            self.sync_estado = "Descargando de la nube..."

            def _trabajo():
                cloud_db.forzar_pull()
                Clock.schedule_once(lambda dt: self._refrescar_tras_pull(), 0)

            threading.Thread(target=_trabajo, daemon=True).start()

        btn_no = Button(text='Cancelar', on_press=_no, size_hint_x=0.5,
                        background_color=[0.90, 0.30, 0.35, 1], color=[1, 1, 1, 1])
        btn_si = Button(text='Restaurar', on_press=_si, size_hint_x=0.5,
                        background_color=[0.07, 0.65, 0.60, 1], color=[1, 1, 1, 1], bold=True)
        btns.add_widget(btn_no)
        btns.add_widget(btn_si)
        content.add_widget(lbl)
        content.add_widget(btns)
        ref[0] = Popup(title='Restaurar desde la nube', content=content, size_hint=(0.8, 0.4))
        ref[0].open()

    def _refrescar_tras_pull(self):
        try:
            self.refresh_data()
            sm = self.manager
            if sm and sm.current == 'casa':
                sm.get_screen('casa')._render_inicio()
        except Exception:
            pass

    def _cerrar_sesion(self):
        content = BoxLayout(orientation='vertical', spacing=10, padding=15)
        lbl = KivyLabel(
            text="Se cerrara la sesion en este dispositivo.\n"
                 "Tus datos se suben a la nube antes de salir\n"
                 "y siguen guardados aqui.\n\nCerrar sesion?",
            font_size='13sp', color=[0.08, 0.08, 0.09, 1]
        )
        lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
        btns = BoxLayout(size_hint_y=None, height='40dp', spacing=10)
        ref = [None]

        def _no(b):
            ref[0].dismiss()

        def _si(b):
            ref[0].dismiss()
            self.sync_estado = "Subiendo datos pendientes..."

            def _trabajo():
                try:
                    cloud_db.push_inmediato(timeout_total=5)
                except Exception:
                    pass
                cloud_db.sign_out()
                Clock.schedule_once(lambda dt: self._ir_a_login(), 0)

            threading.Thread(target=_trabajo, daemon=True).start()

        btn_no = Button(text='Cancelar', on_press=_no, size_hint_x=0.5,
                        background_color=[0.90, 0.30, 0.35, 1], color=[1, 1, 1, 1])
        btn_si = Button(text='Cerrar sesion', on_press=_si, size_hint_x=0.5,
                        background_color=[0.90, 0.30, 0.35, 1], color=[1, 1, 1, 1], bold=True)
        btns.add_widget(btn_no)
        btns.add_widget(btn_si)
        content.add_widget(lbl)
        content.add_widget(btns)
        ref[0] = Popup(title='Cerrar sesion', content=content, size_hint=(0.8, 0.42))
        ref[0].open()

    def _ir_a_login(self):
        sm = self.manager
        if sm is None:
            app = App.get_running_app()
            sm = app.root if app else None
        if sm is not None and sm.has_screen('login'):
            sm.current = 'login'

    def on_enter(self, *args):
        self.refresh_data()

    def refresh_data(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ahorros InDrive
        cursor.execute("SELECT tipo, categoria, monto, comision FROM transacciones WHERE cuenta = 'Ahorro InDrive'")
        ahorro_rows = cursor.fetchall()
        tot_ahorro_ing = 0.0
        tot_ahorro_eg = 0.0
        for tipo, cat, monto, comision in ahorro_rows:
            if tipo == "Ingreso":
                tot_ahorro_ing += (monto - comision) if cat == "Viaje InDrive" else monto
            elif tipo == "Gasto":
                tot_ahorro_eg += monto
        
        saldo_ahorro = tot_ahorro_ing - tot_ahorro_eg
        self.balance_ahorro = f"${saldo_ahorro:,.2f}"

        # Fondo del Carro
        cursor.execute("SELECT tipo, monto FROM transacciones WHERE cuenta = 'Uso del Carro'")
        carro_rows = cursor.fetchall()
        tot_carro_ing = sum(m for t, m in carro_rows if t == "Ingreso")
        tot_carro_eg = sum(m for t, m in carro_rows if t == "Gasto")
        saldo_carro = tot_carro_ing - tot_carro_eg
        self.balance_carro = f"${saldo_carro:,.2f}"
        self.color_carro = [0.07, 0.65, 0.60, 1] if saldo_carro >= 0 else [0.90, 0.30, 0.35, 1]

        conn.close()


class AhorroScreen(Screen):
    balance_ahorro = StringProperty("$0.00")
    current_form = StringProperty("viaje")
    var_o_tipo = StringProperty("Gasto")
    var_o_cat = StringProperty("Recarga")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(current_form=self.load_form_layout)
        self.bind(var_o_tipo=self.update_o_cat_button)

    def on_enter(self, *args):
        self.load_form_layout()
        self.refresh_all()

    def update_o_cat_button(self, *args):
        self.var_o_cat = "Ahorro" if self.var_o_tipo == "Ingreso" else "Recarga"
        self.load_form_layout()

    def toggle_o_category(self):
        cats = ["Ahorro", "Otros"] if self.var_o_tipo == "Ingreso" else ["Recarga", "Salidas", "Otros"]
        try:
            idx = cats.index(self.var_o_cat)
            self.var_o_cat = cats[(idx + 1) % len(cats)]
        except:
            self.var_o_cat = cats[0]
        if hasattr(self, 'btn_cat_sel'):
            self.btn_cat_sel.text = self.var_o_cat

    def load_form_layout(self, *args):
        container = self.ids.form_container
        container.clear_widgets()

        if self.current_form == "viaje":
            layout = GridLayout(cols=2, spacing=6)
            layout.add_widget(Label(text="Fecha:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_fecha = DateInput(text=hoy_corto(), multiline=False, size_hint_y=None, height='28dp')
            self.txt_fecha.fuente = _sug_fechas
            layout.add_widget(self.txt_fecha)
            layout.add_widget(Label(text="Bruto:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_bruto = TextInput(hint_text="0.00", multiline=False, size_hint_y=None, height='28dp')
            layout.add_widget(self.txt_bruto)
            layout.add_widget(Label(text="Comisión:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_comision = TextInput(hint_text="0.00", multiline=False, size_hint_y=None, height='28dp')
            layout.add_widget(self.txt_comision)
            layout.add_widget(Label(text="Gasolina:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_gasolina = TextInput(hint_text="0.00", multiline=False, size_hint_y=None, height='28dp')
            layout.add_widget(self.txt_gasolina)
            layout.add_widget(Label(text="Aporte Carro:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_uso_carro = TextInput(hint_text="0.00", multiline=False, size_hint_y=None, height='28dp')
            layout.add_widget(self.txt_uso_carro)
            layout.add_widget(Label(text="Viajes/KM:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            box = BoxLayout(spacing=4)
            self.txt_viajes = TextInput(hint_text="Vj", multiline=False)
            self.txt_km = TextInput(hint_text="KM", multiline=False)
            box.add_widget(self.txt_viajes)
            box.add_widget(self.txt_km)
            layout.add_widget(box)
            btn_save = AccentButton(text="Guardar Viaje", size_hint_y=None, height='35dp')
            btn_save.bind(on_press=self.save_viaje)
            container.add_widget(layout)
            container.add_widget(btn_save)
        else:
            layout = GridLayout(cols=2, spacing=6)
            layout.add_widget(Label(text="Fecha:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_fecha = DateInput(text=hoy_corto(), multiline=False, size_hint_y=None, height='28dp')
            self.txt_fecha.fuente = _sug_fechas
            layout.add_widget(self.txt_fecha)
            layout.add_widget(Label(text="Tipo:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            box_tipo = BoxLayout(spacing=4, size_hint_y=None, height='28dp')
            btn_gasto = Button(text="Gasto", font_size='11sp', bold=True)
            btn_ingreso = Button(text="Ingreso", font_size='11sp', bold=True)
            btn_gasto.bind(on_press=lambda btn: setattr(self, 'var_o_tipo', 'Gasto'))
            btn_ingreso.bind(on_press=lambda btn: setattr(self, 'var_o_tipo', 'Ingreso'))
            box_tipo.add_widget(btn_gasto)
            box_tipo.add_widget(btn_ingreso)
            layout.add_widget(box_tipo)
            layout.add_widget(Label(text="Monto:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_monto = TextInput(hint_text="0.00", multiline=False, size_hint_y=None, height='28dp')
            layout.add_widget(self.txt_monto)
            layout.add_widget(Label(text="Categoría:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.btn_cat_sel = Button(text=self.var_o_cat, font_size='11sp', size_hint_y=None, height='28dp')
            self.btn_cat_sel.bind(on_press=lambda btn: self.toggle_o_category())
            layout.add_widget(self.btn_cat_sel)
            layout.add_widget(Label(text="Descripción:", font_size='11sp', color=[0.3, 0.3, 0.35, 1], size_hint_y=None, height='28dp'))
            self.txt_desc = CampoSugerencias(hint_text="Nota...", multiline=False, size_hint_y=None, height='28dp')
            self.txt_desc.fuente = _sug_de('transacciones', 'descripcion')
            layout.add_widget(self.txt_desc)
            btn_save = AccentButton(text="Guardar", size_hint_y=None, height='35dp')
            btn_save.bind(on_press=self.save_otro)
            container.add_widget(layout)
            container.add_widget(btn_save)

    def refresh_all(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tipo, categoria, monto, comision FROM transacciones WHERE cuenta = 'Ahorro InDrive'")
        rows = cursor.fetchall()
        tot_ing, tot_eg = 0.0, 0.0
        for tipo, cat, monto, com in rows:
            if tipo == "Ingreso":
                tot_ing += (monto - com) if cat == "Viaje InDrive" else monto
            else:
                tot_eg += monto
        
        self.balance_ahorro = f"${tot_ing - tot_eg:,.2f}"

        self.ids.list_transacciones.clear_widgets()
        cursor.execute("SELECT id, fecha, tipo, categoria, monto, comision, viajes, km, descripcion FROM transacciones WHERE cuenta = 'Ahorro InDrive' ORDER BY fecha DESC LIMIT 50")
        rows = cursor.fetchall()
        for r in rows:
            tid, fd, tp, cat, monto, com, vj, km, desc = r
            try:
                fecha_v = datetime.strptime(fd, "%Y-%m-%d").strftime("%d/%m")
            except:
                fecha_v = fd
            display_monto = (monto - com) if cat == "Viaje InDrive" else monto
            display_desc = f"{desc} (Viajes: {vj})" if cat == "Viaje InDrive" else desc
            item = TransactionItem(tid, fecha_v, tp, cat, display_monto, display_desc,
                                   self.delete_item, edit_callback=self.edit_item)
            self.ids.list_transacciones.add_widget(item)
        conn.close()

    def save_viaje(self, *args):
        fecha_db = fecha_de_campo(self.txt_fecha, "fecha del viaje")
        if not fecha_db:
            return

        try:
            bruto = float(self.txt_bruto.text.strip() or 0)
            comision = float(self.txt_comision.text.strip() or 0)
            gasolina = float(self.txt_gasolina.text.strip() or 0)
            uso_carro = float(self.txt_uso_carro.text.strip() or 0)
            viajes = int(self.txt_viajes.text.strip() or 0)
            km = float(self.txt_km.text.strip() or 0)
        except:
            mostrar_error("Los campos numéricos deben ser números válidos.\nEjemplo: 25.50")
            return

        if bruto == 0 and gasolina == 0 and uso_carro == 0:
            mostrar_error("Ingresa al menos uno de estos campos:\n- Bruto del viaje\n- Gasolina\n- Aporte Carro")
            return

        conn = get_db_connection()
        cur = conn.cursor()

        if bruto > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision, viajes, km, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Ingreso', ?, ?, ?, ?, 'Viaje InDrive', 'Sesión')", (fecha_db, bruto, comision, viajes, km))
        if gasolina > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Gasto', ?, 'Combustible', 'Gasolina')", (fecha_db, gasolina))
        if uso_carro > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Gasto', ?, 'Uso del Carro', 'Aporte carro')", (fecha_db, uso_carro))
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Uso del Carro', 'Ingreso', ?, 'Aporte', 'Ingreso diario')", (fecha_db, uso_carro))

        close_db(conn)
        self.refresh_all()
        for attr in ['txt_bruto', 'txt_comision', 'txt_gasolina', 'txt_uso_carro', 'txt_viajes', 'txt_km']:
            getattr(self, attr).text = ""

    def save_otro(self, *args):
        fecha_db = fecha_de_campo(self.txt_fecha, "fecha")
        if not fecha_db:
            return
        monto_s = self.txt_monto.text.strip()
        if not monto_s:
            mostrar_error("Por favor ingresa el monto.")
            return
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 10.00")
            return
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', ?, ?, ?, ?)", (fecha_db, self.var_o_tipo, monto, self.var_o_cat, self.txt_desc.text.strip() or ""))
        close_db(conn)
        self.refresh_all()
        self.txt_monto.text = ""
        self.txt_desc.text = ""

    def delete_item(self, tid):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT fecha, categoria FROM transacciones WHERE id = ?", (tid,))
        row = cur.fetchone()
        if row and row[1] == "Viaje InDrive":
            fecha = row[0]
            cur.execute("DELETE FROM transacciones WHERE id = ?", (tid,))
            cur.execute("DELETE FROM transacciones WHERE fecha = ? AND cuenta = 'Ahorro InDrive' AND categoria IN ('Combustible', 'Uso del Carro')", (fecha,))
            cur.execute("DELETE FROM transacciones WHERE fecha = ? AND cuenta = 'Uso del Carro'", (fecha,))
        else:
            cur.execute("DELETE FROM transacciones WHERE id = ?", (tid,))
        close_db(conn)
        self.refresh_all()

    def edit_item(self, tid):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT fecha, tipo, categoria, monto, comision, viajes, km, descripcion "
                    "FROM transacciones WHERE id = ?", (tid,))
        row = cur.fetchone()
        conn.close()
        if not row:
            self.refresh_all()
            return
        fd, tp, cat, monto, com, vj, km, desc = row
        campos = [
            {'id': 'fecha', 'label': 'Fecha', 'tipo': 'fecha'},
            {'id': 'tipo', 'label': 'Tipo', 'tipo': 'texto'},
            {'id': 'categoria', 'label': 'Categoría', 'tipo': 'texto'},
            {'id': 'monto', 'label': 'Monto', 'tipo': 'numero'},
            {'id': 'comision', 'label': 'Comisión', 'tipo': 'numero'},
            {'id': 'viajes', 'label': 'Viajes', 'tipo': 'numero'},
            {'id': 'km', 'label': 'Kilómetros', 'tipo': 'numero'},
            {'id': 'descripcion', 'label': 'Descripción', 'tipo': 'texto'},
        ]
        valores = {'fecha': fd, 'tipo': tp, 'categoria': cat, 'monto': monto,
                   'comision': com, 'viajes': vj, 'km': km, 'descripcion': desc}

        def guardar(v):
            conn = get_db_connection()
            conn.execute(
                "UPDATE transacciones SET fecha=?, tipo=?, categoria=?, monto=?, "
                "comision=?, viajes=?, km=?, descripcion=? WHERE id=?",
                (v['fecha'] or fd, v['tipo'], v['categoria'], _num(v['monto'], monto),
                 _num(v['comision'], com), _entero(v['viajes'], vj), _num(v['km'], km),
                 v['descripcion'], tid))
            close_db(conn)
            self.refresh_all()

        editar_registro("Editar movimiento", campos, guardar, valores)


class CarroScreen(Screen):
    balance_carro = StringProperty("$0.00")
    color_carro = ObjectProperty([0.07, 0.65, 0.60, 1])
    var_c_tipo = StringProperty("Gasto")
    var_c_cat = StringProperty("Combustible")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(var_c_tipo=self.update_c_category_on_type)
        # Los ids pueden llegar despues de __init__ cuando la pantalla la
        # construye Kivy desde el KV, así que se cablean al tener padre.
        self.bind(parent=self._cablear_sugerencias)

    def on_kv_post(self, base_widget):
        # Tambien aqui: la pantalla se crea desde Python en build(), donde
        # parent aun no existe y no se dispararia el bind de arriba.
        self._cablear()

    def _cablear_sugerencias(self, instancia, padre):
        if padre is None:
            return
        self._cablear()

    def _cablear(self):
        desc = self.ids.get('c_desc')
        if desc is not None and desc.fuente is None:
            desc.fuente = _sug_de('transacciones', 'descripcion')
        fecha = self.ids.get('c_fecha')
        if fecha is not None and fecha.fuente is None:
            fecha.fuente = _sug_fechas

    def on_enter(self, *args):
        self.refresh_all()

    def update_c_category_on_type(self, *args):
        self.var_c_cat = "Aporte" if self.var_c_tipo == "Ingreso" else "Combustible"

    def toggle_c_category(self):
        cats = ["Aporte", "Otros"] if self.var_c_tipo == "Ingreso" else ["Combustible", "Repuestos", "Mantenimiento", "Lavado", "Otros"]
        try:
            idx = cats.index(self.var_c_cat)
            self.var_c_cat = cats[(idx + 1) % len(cats)]
        except:
            self.var_c_cat = cats[0]

    def refresh_all(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tipo, monto FROM transacciones WHERE cuenta = 'Uso del Carro'")
        rows = cur.fetchall()
        tot_ing = sum(m for t, m in rows if t == "Ingreso")
        tot_eg = sum(m for t, m in rows if t == "Gasto")
        saldo = tot_ing - tot_eg
        self.balance_carro = f"${saldo:,.2f}"
        self.color_carro = [0.07, 0.65, 0.60, 1] if saldo >= 0 else [0.90, 0.30, 0.35, 1]

        self.ids.list_carro.clear_widgets()
        cur.execute("SELECT id, fecha, tipo, categoria, monto, descripcion FROM transacciones WHERE cuenta = 'Uso del Carro' ORDER BY fecha DESC LIMIT 50")
        rows = cur.fetchall()
        for r in rows:
            tid, fd, tp, cat, monto, desc = r
            try:
                fecha_v = datetime.strptime(fd, "%Y-%m-%d").strftime("%d/%m")
            except:
                fecha_v = fd
            item = TransactionItem(tid, fecha_v, tp, cat, monto, desc, self.delete_item,
                                   edit_callback=self.edit_item)
            self.ids.list_carro.add_widget(item)
        conn.close()

    def save_carro(self):
        monto_s = self.ids.c_monto.text.strip()
        if not monto_s:
            mostrar_error("Por favor ingresa el monto.")
            return
        fecha_db = fecha_de_campo(self.ids.c_fecha, "fecha")
        if not fecha_db:
            return
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 15.00")
            return
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Uso del Carro', ?, ?, ?, ?)", (fecha_db, self.var_c_tipo, monto, self.var_c_cat, self.ids.c_desc.text.strip() or ""))
        close_db(conn)
        self.refresh_all()
        self.ids.c_monto.text = ""
        self.ids.c_desc.text = ""

    def delete_item(self, tid):
        conn = get_db_connection()
        conn.execute("DELETE FROM transacciones WHERE id = ?", (tid,))
        close_db(conn)
        self.refresh_all()

    def edit_item(self, tid):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT fecha, tipo, categoria, monto, descripcion "
                    "FROM transacciones WHERE id = ?", (tid,))
        row = cur.fetchone()
        conn.close()
        if not row:
            self.refresh_all()
            return
        fd, tp, cat, monto, desc = row
        campos = [
            {'id': 'fecha', 'label': 'Fecha', 'tipo': 'fecha'},
            {'id': 'tipo', 'label': 'Tipo', 'tipo': 'texto'},
            {'id': 'categoria', 'label': 'Categoría', 'tipo': 'texto'},
            {'id': 'monto', 'label': 'Monto', 'tipo': 'numero'},
            {'id': 'descripcion', 'label': 'Descripción', 'tipo': 'texto'},
        ]
        valores = {'fecha': fd, 'tipo': tp, 'categoria': cat, 'monto': monto,
                   'descripcion': desc}

        def guardar(v):
            conn = get_db_connection()
            conn.execute(
                "UPDATE transacciones SET fecha=?, tipo=?, categoria=?, monto=?, "
                "descripcion=? WHERE id=?",
                (v['fecha'] or fd, v['tipo'], v['categoria'],
                 _num(v['monto'], monto), v['descripcion'], tid))
            close_db(conn)
            self.refresh_all()

        editar_registro("Editar movimiento del carro", campos, guardar, valores)


class StatsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self.trigger_draw)

    def trigger_draw(self, *args):
        Clock.schedule_once(self.draw_chart, 0.05)

    def on_enter(self, *args):
        Clock.schedule_once(self.draw_chart, 0.1)

    def draw_chart(self, *args):
        holder = self.ids.chart_canvas
        holder.canvas.clear()
        
        w, h = holder.width, holder.height
        if w < 50 or h < 50:
            return
            
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT mes,
                   SUM(CASE WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' AND categoria = 'Viaje InDrive' THEN monto - comision 
                            WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' THEN monto 
                            WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Gasto' THEN -monto ELSE 0 END) as ahorro,
                   SUM(CASE WHEN cuenta = 'Uso del Carro' AND tipo = 'Ingreso' THEN monto 
                            WHEN cuenta = 'Uso del Carro' AND tipo = 'Gasto' THEN -monto ELSE 0 END) as carro
            FROM (SELECT strftime('%Y-%m', fecha) as mes, cuenta, tipo, monto, comision, categoria FROM transacciones)
            GROUP BY mes ORDER BY mes DESC LIMIT 6
        """)
        rows = cur.fetchall()
        
        cur.execute("SELECT SUM(CASE WHEN categoria = 'Viaje InDrive' THEN monto - comision ELSE 0 END), SUM(CASE WHEN categoria = 'Viaje InDrive' THEN km ELSE 0 END) FROM transacciones WHERE cuenta = 'Ahorro InDrive'")
        neto, km = cur.fetchone()
        self.ids.lbl_efficiency.text = f"${neto/km:.2f}/KM" if neto and km and km > 0 else "$0.00/KM"
        
        daily = self.ids.list_daily_profits
        daily.clear_widgets()
        cur.execute("""
            SELECT fecha,
                   SUM(CASE WHEN tipo = 'Ingreso' AND categoria = 'Viaje InDrive' THEN monto - comision WHEN tipo = 'Ingreso' THEN monto ELSE 0 END) as ingresos,
                   SUM(CASE WHEN tipo = 'Gasto' THEN monto ELSE 0 END) as gastos,
                   SUM(CASE WHEN categoria = 'Viaje InDrive' THEN viajes ELSE 0 END) as viajes,
                   SUM(CASE WHEN categoria = 'Viaje InDrive' THEN km ELSE 0 END) as km,
                   SUM(CASE WHEN categoria = 'Combustible' THEN monto ELSE 0 END) as gas,
                   SUM(CASE WHEN categoria = 'Uso del Carro' THEN monto ELSE 0 END) as uso
            FROM transacciones WHERE cuenta = 'Ahorro InDrive' GROUP BY fecha ORDER BY fecha DESC LIMIT 15
        """)
        for row in cur.fetchall():
            daily.add_widget(DailyProfitItem(*row))
        conn.close()
        
        if not rows:
            return
        
        stats = {}
        for mes, ahorro, carro in rows:
            try:
                mes_legible = datetime.strptime(mes, "%Y-%m").strftime("%b")
            except:
                mes_legible = mes
            stats[mes_legible] = {"Ahorro": ahorro or 0, "Carro": carro or 0}
        
        meses = list(reversed(list(stats.keys())))
        
        if meses:
            best = max(meses, key=lambda m: stats[m]["Ahorro"])
            self.ids.lbl_best_month.text = best
        
        months_container = self.ids.chart_months
        months_container.clear_widgets()
        for mes in meses:
            months_container.add_widget(Label(text=mes, font_size='11sp', bold=True, color=[0.08, 0.08, 0.09, 1], halign='center'))
        
        px, py = 40, 30
        cw, ch = w - 80, h - 60
        ox, oy = px, py
        
        max_val = 1.0
        for mes in meses:
            max_val = max(max_val, stats[mes]["Ahorro"], stats[mes]["Carro"])
        max_val = max_val * 1.1 if max_val > 0 else 1
        
        n = len(meses)
        if n == 0:
            return
        group_w = cw / n
        bar_w = (group_w * 0.4) / 2
        
        with holder.canvas:
            Color(rgba=[0.8, 0.7, 0.6, 0.3])
            Line(points=[ox, oy, ox + cw, oy], width=1)
            
            for idx, mes in enumerate(meses):
                ahorro = stats[mes]["Ahorro"]
                carro = stats[mes]["Carro"]
                gx = ox + (idx * group_w) + (group_w / 2)
                
                h_ah = (ahorro / max_val) * ch
                Color(rgba=[0.07, 0.65, 0.60, 1])
                RoundedRectangle(pos=(gx - bar_w - 4, oy), size=(bar_w, h_ah), radius=[2])
                
                h_ca = (carro / max_val) * ch
                Color(rgba=[0.90, 0.30, 0.35, 1] if carro < 0 else [0.07, 0.65, 0.60, 0.5])
                RoundedRectangle(pos=(gx + 4, oy), size=(bar_w, h_ca), radius=[2])


MESES_NOMBRES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
]

class CalendarScreen(Screen):
    mes_anio_label = StringProperty('')

    def on_enter(self, *args):
        today = datetime.today()
        if not hasattr(self, '_current_year') or self._current_year is None:
            self._current_year = today.year
            self._current_month = today.month
        self._render_calendar()

    def go_prev_month(self):
        if self._current_month == 1:
            self._current_month = 12
            self._current_year -= 1
        else:
            self._current_month -= 1
        self._render_calendar()

    def go_next_month(self):
        if self._current_month == 12:
            self._current_month = 1
            self._current_year += 1
        else:
            self._current_month += 1
        self._render_calendar()

    def _render_calendar(self):
        self.ids.calendar_grid.clear_widgets()

        year = self._current_year
        month = self._current_month

        self.mes_anio_label = f"{MESES_NOMBRES[month - 1].upper()} {year}"

        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = 31
        else:
            last_day = (datetime(year, month + 1, 1) - timedelta(days=1)).day

        conn = get_db_connection()
        cur = conn.cursor()
        mes_str = f"{year}-{month:02d}"
        cur.execute("""
            SELECT fecha,
                   SUM(CASE
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' AND categoria = 'Viaje InDrive' THEN monto - comision
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' AND categoria != 'Viaje InDrive' THEN monto
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Gasto' THEN -monto
                        ELSE 0
                   END) as profit
            FROM transacciones
            WHERE fecha LIKE ?
            GROUP BY fecha
        """, (mes_str + '%',))
        profit_map = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()

        first_weekday = first_day.weekday()
        for _ in range(first_weekday):
            self.ids.calendar_grid.add_widget(Label(text=''))

        today = datetime.today()

        for day in range(1, last_day + 1):
            date_obj = first_day.replace(day=day)
            date_str = date_obj.strftime('%Y-%m-%d')
            is_today = (date_obj.date() == today.date())

            if date_str not in profit_map:
                bg = [0.07, 0.65, 0.60, 0.25] if is_today else [0.98, 0.98, 0.99, 0.9]
                fc = [0.07, 0.45, 0.40, 1] if is_today else [0.08, 0.08, 0.09, 0.9]
                btn = Button(
                    text=f"{day}",
                    size_hint_y=None,
                    height='60dp',
                    background_normal='',
                    background_color=bg,
                    color=fc,
                    font_size='14sp',
                    bold=is_today
                )
            else:
                profit = profit_map[date_str]
                if profit >= 0:
                    bg_col = [0.07, 0.65, 0.60, 0.85]
                else:
                    bg_col = [0.90, 0.30, 0.35, 0.85]
                btn = Button(
                    text=f"{day}\n${profit:,.2f}",
                    size_hint_y=None,
                    height='60dp',
                    background_normal='',
                    background_color=bg_col,
                    color=[1, 1, 1, 1],
                    font_size='11sp',
                    bold=True,
                    halign='center',
                    valign='middle'
                )
                btn.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

            btn.bind(on_release=lambda inst, ds=date_str: self.show_day(ds))
            self.ids.calendar_grid.add_widget(btn)

    def show_day(self, date_str):
        show_day_details(date_str)


class TransactionItem(BoxLayout):
    def __init__(self, tid, fecha, tipo, cat, monto, desc, delete_callback,
                 edit_callback=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = '48dp'
        self.padding = [10, 6]
        self.spacing = 8
        
        with self.canvas.before:
            Color(rgba=[1, 1, 1, 1])
            self.k_rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[6])
        self.bind(size=self._update_rect, pos=self._update_rect)

        color_text = [0.07, 0.65, 0.60, 1] if tipo == "Ingreso" else [0.90, 0.30, 0.35, 1]
        monto_sign = "+" if tipo == "Ingreso" else "-"
        
        info_layout = BoxLayout(orientation='vertical', size_hint_x=0.7)
        lbl_date_cat = Label(text=f"{fecha} - {cat}", font_size='11sp', bold=True, color=[0.3, 0.3, 0.35, 1], halign='left', valign='middle')
        lbl_date_cat.bind(size=lbl_date_cat.setter('text_size'))
        lbl_desc = Label(text=str(desc) if desc else "", font_size='12sp', color=[0.08, 0.08, 0.09, 1], halign='left', valign='middle')
        lbl_desc.bind(size=lbl_desc.setter('text_size'))
        info_layout.add_widget(lbl_date_cat)
        info_layout.add_widget(lbl_desc)
        
        lbl_monto = Label(text=f"{monto_sign}${monto:,.2f}", font_size='14sp', bold=True, color=color_text, size_hint_x=0.22, halign='right', valign='middle')
        lbl_monto.bind(size=lbl_monto.setter('text_size'))
        
        btn_del = Button(text="X", size_hint_x=None, width='24dp', background_color=[0,0,0,0], color=[0.7,0.3,0.3,1], bold=True, font_size='14sp')
        btn_del.bind(on_press=lambda btn: delete_callback(tid))

        self.add_widget(info_layout)
        self.add_widget(lbl_monto)
        if edit_callback is not None:
            btn_edit = Button(text="✎", size_hint_x=None, width='26dp',
                              background_color=[0, 0, 0, 0], color=[0.07, 0.65, 0.60, 1],
                              bold=True, font_size='15sp')
            btn_edit.bind(on_press=lambda btn: edit_callback(tid))
            self.add_widget(btn_edit)
        self.add_widget(btn_del)

    def _update_rect(self, instance, value):
        self.k_rect.size = self.size
        self.k_rect.pos = self.pos


class DailyProfitItem(BoxLayout):
    def __init__(self, fecha, ingresos, gastos, viajes, km, gasolina, uso_carro, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = '56dp'
        self.padding = [10, 6]
        self.spacing = 8
        
        with self.canvas.before:
            Color(rgba=[1, 1, 1, 1])
            self.k_rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[8])
        self.bind(size=self._update_rect, pos=self._update_rect)

        try:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
            dia_sem = dias[dt.weekday()]
            fecha_str = f"{dia_sem} {dt.strftime('%d/%m')}"
        except:
            fecha_str = fecha

        left_layout = BoxLayout(orientation='vertical', size_hint_x=0.45, spacing=2)
        lbl_fecha = Label(text=fecha_str, font_size='13sp', bold=True, color=[0.08, 0.08, 0.09, 1], halign='left', valign='middle')
        lbl_fecha.bind(size=lbl_fecha.setter('text_size'))
        sub_text = f"{viajes} vj | {km:,.0f} km" if viajes > 0 else "Manual"
        lbl_sub = Label(text=sub_text, font_size='11sp', color=[0.3, 0.3, 0.35, 1], halign='left', valign='middle')
        lbl_sub.bind(size=lbl_sub.setter('text_size'))
        left_layout.add_widget(lbl_fecha)
        left_layout.add_widget(lbl_sub)

        center_layout = BoxLayout(orientation='vertical', size_hint_x=0.35, spacing=1)
        gas_text = f"-${gasolina:,.2f}" if gasolina > 0 else ""
        car_text = f"-${uso_carro:,.2f}" if uso_carro > 0 else ""
        lbl_gas = Label(text=gas_text, font_size='10sp', color=[0.90, 0.30, 0.35, 1], halign='left', valign='middle')
        lbl_gas.bind(size=lbl_gas.setter('text_size'))
        lbl_car = Label(text=car_text, font_size='10sp', color=[0.95, 0.50, 0.20, 1], halign='left', valign='middle')
        lbl_car.bind(size=lbl_car.setter('text_size'))
        center_layout.add_widget(lbl_gas)
        center_layout.add_widget(lbl_car)

        neto = ingresos - gastos
        color_neto = [0.07, 0.65, 0.60, 1] if neto >= 0 else [0.90, 0.30, 0.35, 1]
        neto_sign = "+" if neto >= 0 else ""
        right_layout = BoxLayout(orientation='vertical', size_hint_x=0.2, spacing=2)
        lbl_neto = Label(text=f"{neto_sign}${neto:,.2f}", font_size='14sp', bold=True, color=color_neto, halign='right', valign='middle')
        lbl_neto.bind(size=lbl_neto.setter('text_size'))
        right_layout.add_widget(lbl_neto)

        self.add_widget(left_layout)
        self.add_widget(center_layout)
        self.add_widget(right_layout)

    def _update_rect(self, instance, value):
        self.k_rect.size = self.size
        self.k_rect.pos = self.pos


def show_day_details(date_str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT tipo, categoria, monto, comision, descripcion
        FROM transacciones 
        WHERE fecha=? AND cuenta='Ahorro InDrive' 
        ORDER BY id DESC
    """, (date_str,))
    rows = cur.fetchall()
    conn.close()

    total_ingresos_brutos = 0.0
    total_comision = 0.0
    total_gastos = 0.0
    
    detail_layout = BoxLayout(orientation='vertical', spacing=10, padding=12)
    
    scroll = ScrollView(size_hint=(1, 0.7))
    list_layout = BoxLayout(orientation='vertical', spacing=6, size_hint_y=None)
    list_layout.bind(minimum_height=list_layout.setter('height'))
    
    if not rows:
        lbl_empty = Label(
            text="No hay transacciones registradas para este día.",
            color=[0.3, 0.3, 0.35, 1],
            font_size='14sp',
            halign='center',
            valign='middle',
            size_hint_y=None,
            height='80dp'
        )
        lbl_empty.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        list_layout.add_widget(lbl_empty)
    else:
        for tipo, cat, monto, com, desc in rows:
            if tipo == 'Ingreso':
                if cat == 'Viaje InDrive':
                    total_ingresos_brutos += monto
                    total_comision += com
                    net_trip = monto - com
                    text = f"  [b]Viaje InDrive:[/b]\n      Neto: [color=12806C]+${net_trip:,.2f}[/color] (Bruto: ${monto:,.2f} | Com: -${com:,.2f})"
                else:
                    total_ingresos_brutos += monto
                    text = f"  [b]{cat}:[/b]\n      +${monto:,.2f} - {desc}"
            else:
                total_gastos += monto
                text = f"  [b]{cat}:[/b]\n      [color=E6484B]-${monto:,.2f}[/color] - {desc}"
                
            lbl = Label(
                text=text,
                markup=True,
                size_hint_y=None,
                height='40dp',
                halign='left',
                valign='middle',
                color=[0.08, 0.08, 0.09, 1],
                font_size='12sp'
            )
            lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
            
            card = RoundedCard(size_hint_y=None, height='52dp', bg_color=[1, 1, 1, 1], padding=[8, 4])
            card.add_widget(lbl)
            list_layout.add_widget(card)
        
    scroll.add_widget(list_layout)
    detail_layout.add_widget(scroll)
    
    neto_dia = (total_ingresos_brutos - total_comision) - total_gastos
    color_neto = "12806C" if neto_dia >= 0 else "E6484B"
    
    summary_text = (
        f"[b]RESUMEN DEL DÍA[/b]\n"
        f"Ingresos Brutos: ${total_ingresos_brutos:,.2f}\n"
        f"Comisiones InDrive: -${total_comision:,.2f}\n"
        f"Gastos / Egresos: -${total_gastos:,.2f}\n"
        f"-----------------------------------------\n"
        f"AHORRO NETO: [color={color_neto}][b]${neto_dia:,.2f}[/b][/color]"
    )
    
    summary_card = RoundedCard(
        size_hint_y=None,
        height='120dp',
        bg_color=[1, 1, 1, 1],
        padding=[12, 10]
    )
    summary_lbl = Label(
        text=summary_text,
        markup=True,
        halign='left',
        valign='middle',
        color=[0.08, 0.08, 0.09, 1],
        font_size='13sp'
    )
    summary_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
    summary_card.add_widget(summary_lbl)
    detail_layout.add_widget(summary_card)
    
    popup = Popup(
        title=f"Detalle {date_str}",
        content=detail_layout,
        size_hint=(0.9, 0.85)
    )
    popup.open()


class CasaScreen(Screen):
    tab_actual = StringProperty("pagos")
    cliente_actual = StringProperty("")
    cliente_actual_id = NumericProperty(0)
    vista_actual = StringProperty("inicio")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(tab_actual=self._on_tab_change)
        self.bind(vista_actual=self._on_vista_change)

    def _on_tab_change(self, *args):
        if self.vista_actual == 'cliente':
            self._render_cliente()

    def _on_vista_change(self, *args):
        if self.vista_actual == 'inicio':
            self._render_inicio()
        elif self.vista_actual == 'clientes':
            self._render_lista_clientes()
        elif self.vista_actual == 'cliente':
            self._render_cliente()

    def on_enter(self, *args):
        self._render_inicio()

    def _ir_clientes(self):
        self.vista_actual = 'clientes'

    def _seleccionar_cliente(self, cid, nombre):
        self.cliente_actual_id = cid
        self.cliente_actual = nombre
        self.vista_actual = 'cliente'
        self.tab_actual = 'pagos'

    def _volver_inicio(self):
        self.vista_actual = 'inicio'

    def _volver_clientes(self):
        self.vista_actual = 'clientes'

    def _volver_atras(self):
        if self.vista_actual == 'inicio':
            self.manager.current = 'dashboard'
        elif self.vista_actual == 'clientes' or self.vista_actual == 'gastos' or self.vista_actual == 'ahorro':
            self.vista_actual = 'inicio'
            self._render_inicio()
        elif self.vista_actual == 'cliente':
            self.vista_actual = 'clientes'
            self._render_lista_clientes()

    def _render_tab(self):
        if self.vista_actual == 'cliente':
            self._render_cliente()
        elif self.vista_actual == 'gastos':
            c = self.ids.container_contenido
            c.clear_widgets()
            btn_volver = Button(text="< Volver", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
            btn_volver.bind(on_press=lambda b: self._volver_inicio())
            c.add_widget(btn_volver)
            self._render_gastos(c)
        elif self.vista_actual == 'ahorro':
            c = self.ids.container_contenido
            c.clear_widgets()
            btn_volver = Button(text="< Volver", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
            btn_volver.bind(on_press=lambda b: self._volver_inicio())
            c.add_widget(btn_volver)
            self._render_ahorro(c)

    def _agregar_cliente(self, nombre):
        if not nombre.strip(): return
        conn = get_db_connection()
        conn.execute("INSERT INTO clientes (nombre) VALUES (?)", (nombre.strip(),))
        close_db(conn)
        self._render_lista_clientes()

    def _popup_add_cliente(self):
        content = BoxLayout(orientation='vertical', spacing=10, padding=15)
        lbl = Label(text="Nombre del nuevo cliente:", font_size='13sp', color=[0.08,0.08,0.09,1])
        txt = TextInput(hint_text="Nombre...", multiline=False, font_size='13sp', size_hint_y=None, height='35dp')
        btns = BoxLayout(size_hint_y=None, height='35dp', spacing=10)
        btn_cancel = Button(text='Cancelar', size_hint_x=0.5, background_color=[0.9,0.3,0.35,1], color=[1,1,1,1])
        btn_ok = Button(text='Agregar', size_hint_x=0.5, background_color=[0.07,0.65,0.60,1], color=[1,1,1,1])
        btns.add_widget(btn_cancel)
        btns.add_widget(btn_ok)
        content.add_widget(lbl)
        content.add_widget(txt)
        content.add_widget(btns)
        popup = Popup(title='Nuevo Cliente', content=content, size_hint=(0.7, 0.4), auto_dismiss=False)
        btn_cancel.bind(on_press=popup.dismiss)
        btn_ok.bind(on_press=lambda b: (self._agregar_cliente(txt.text), popup.dismiss()))
        popup.open()

    def _render_inicio(self):
        c = self.ids.container_contenido
        c.clear_widgets()

        c.add_widget(Label(text="Gastos y Ahorro personal", font_size='11sp', bold=True, color=[0.3,0.3,0.35,1], size_hint_y=None, height='25dp'))

        btn_gastos = AccentButton(text="Gastos", size_hint_y=None, height='45dp')
        btn_gastos.bind(on_press=lambda b: self._ver_gastos())
        c.add_widget(btn_gastos)

        btn_ahorro = AccentButton(text="Ahorro", size_hint_y=None, height='45dp')
        btn_ahorro.bind(on_press=lambda b: self._ver_ahorro())
        c.add_widget(btn_ahorro)

        c.add_widget(Label(text="", size_hint_y=None, height='10dp'))

        btn_clientes = AccentButton(text="Clientes", size_hint_y=None, height='45dp')
        btn_clientes.bg_normal = [0.95, 0.70, 0.20, 1]
        btn_clientes.bind(on_press=lambda b: self._ir_clientes())
        c.add_widget(btn_clientes)

    def _ver_gastos(self):
        self.vista_actual = 'gastos'
        c = self.ids.container_contenido
        c.clear_widgets()
        btn_volver = Button(text="< Volver", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
        btn_volver.bind(on_press=lambda b: self._volver_inicio())
        c.add_widget(btn_volver)
        self._render_gastos(c)

    def _ver_ahorro(self):
        self.vista_actual = 'ahorro'
        c = self.ids.container_contenido
        c.clear_widgets()
        btn_volver = Button(text="< Volver", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
        btn_volver.bind(on_press=lambda b: self._volver_inicio())
        c.add_widget(btn_volver)
        self._render_ahorro(c)

    def _render_lista_clientes(self):
        c = self.ids.container_contenido
        c.clear_widgets()

        btn_volver = Button(text="< Volver", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
        btn_volver.bind(on_press=lambda b: self._volver_inicio())
        c.add_widget(btn_volver)

        c.add_widget(Label(text="Selecciona un cliente", font_size='12sp', bold=True, color=[0.08,0.08,0.09,1], size_hint_y=None, height='25dp'))

        conn = get_db_connection()
        clientes = conn.execute("SELECT id, nombre FROM clientes ORDER BY id").fetchall()
        conn.close()

        for cid, cnombre in clientes:
            btn = Button(text=cnombre, font_size='12sp', bold=True, size_hint_y=None, height='42dp',
                        background_color=[0.07,0.65,0.60,1], color=[1,1,1,1])
            btn.bind(on_press=lambda b, i=cid, n=cnombre: self._seleccionar_cliente(i, n))
            c.add_widget(btn)

        c.add_widget(Label(text="", size_hint_y=None, height='10dp'))

        btn_add = AccentButton(text="+ Nuevo Cliente", size_hint_y=None, height='40dp')
        btn_add.bind(on_press=lambda b: self._popup_add_cliente())
        c.add_widget(btn_add)

    def _render_cliente(self):
        c = self.ids.container_contenido
        c.clear_widgets()

        btn_volver = Button(text="< Clientes", size_hint_y=None, height='30dp', background_color=[0,0,0,0], color=[0.08,0.08,0.09,1], font_size='12sp', bold=True)
        btn_volver.bind(on_press=lambda b: self._volver_clientes())
        c.add_widget(btn_volver)

        c.add_widget(Label(text=self.cliente_actual, font_size='13sp', bold=True, color=[0.08,0.08,0.09,1], size_hint_y=None, height='25dp'))

        tabs = BoxLayout(size_hint_y=None, height='34dp', spacing=6)
        for tab_name in ['pagos', 'aseo', 'deuda']:
            btn = MenuButton(text=tab_name.capitalize(), font_size='11sp',
                bg_normal=[0.07,0.65,0.60,1] if self.tab_actual == tab_name else [1,1,1,1],
                color=[1,1,1,1] if self.tab_actual == tab_name else [0.08,0.08,0.09,1])
            btn.bind(on_press=lambda b, t=tab_name: setattr(self, 'tab_actual', t))
            tabs.add_widget(btn)
        c.add_widget(tabs)

        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8, padding=[0,4,0,4])
        content.bind(minimum_height=content.setter('height'))
        if self.tab_actual == 'pagos': self._render_pagos(content)
        elif self.tab_actual == 'aseo': self._render_aseo(content)
        elif self.tab_actual == 'deuda': self._render_deuda(content)
        c.add_widget(content)

    def _now_str(self):
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    def _row(self, cells, colors=None, on_edit=None):
        r = BoxLayout(orientation='horizontal', size_hint_y=None, height='30dp', spacing=2, padding=[2, 1])
        with r.canvas.before:
            Color(rgba=[1, 1, 1, 1])
            r.k = RoundedRectangle(size=r.size, pos=r.pos, radius=[3])
        r.bind(size=lambda i, v: setattr(i.k, 'size', i.size))
        r.bind(pos=lambda i, v: setattr(i.k, 'pos', i.pos))
        for i, (txt, w) in enumerate(cells):
            c = (colors[i] if colors and i < len(colors) and colors[i] else [0.08, 0.08, 0.09, 1])
            l = Label(text=str(txt) if txt else '-', font_size='9sp', color=c, size_hint_x=w, halign='left', valign='middle')
            l.bind(size=lambda i, v: setattr(i, 'text_size', v))
            r.add_widget(l)
        if on_edit is not None:
            b = Button(text="✎", size_hint_x=None, width='26dp', font_size='13sp',
                       background_color=[0, 0, 0, 0], color=[0.07, 0.65, 0.60, 1], bold=True)
            b.bind(on_press=lambda inst, cb=on_edit: cb())
            r.add_widget(b)
        return r

    def _editar_casa(self, tabla, fila_id, campos, valores, refrescar=None):
        """campos: [(columna, etiqueta, tipo)] con tipo texto|fecha|numero."""
        filas = [{'id': c[0], 'label': c[1], 'tipo': c[2]} for c in campos]
        columnas = [c[0] for c in campos]
        tipos = dict((c[0], c[2]) for c in campos)

        def guardar(v):
            sets = []
            args = []
            for columna in columnas:
                valor = v.get(columna, '')
                if tipos[columna] == 'numero':
                    args.append(_num(valor, 0.0))
                else:
                    args.append(valor)
                sets.append('%s = ?' % columna)
            if tabla == 'casa_ahorro' and 'monto' in columnas:
                sets.append('ahorro = ?')
                args.append(_num(v.get('monto', 0), 0.0))
            args.append(fila_id)
            conn = get_db_connection()
            conn.execute('UPDATE %s SET %s WHERE id = ?' % (tabla, ', '.join(sets)), args)
            close_db(conn)
            if refrescar is not None:
                refrescar()
            else:
                self._render_tab()

        editar_registro('Editar registro', filas, guardar, valores)

    # -------- editores de cada lista de la pantalla Casa --------
    def _editar_pago_casa(self, r):
        self._editar_casa('casa_pagos', r[0], [
            ('fecha_pago', 'Fecha', 'fecha'), ('monto', 'Monto', 'numero'),
            ('mes_corresponde', 'Mes', 'texto'), ('pendiente', 'Pendiente', 'numero'),
            ('pago_hasta', 'Pago hasta', 'fecha'),
        ], {'fecha_pago': r[1], 'monto': r[2], 'mes_corresponde': r[3],
            'pendiente': r[4], 'pago_hasta': r[5]})

    def _editar_pago_usuario(self, r):
        self._editar_casa('casa_pagos_usuario', r[0], [
            ('fecha', 'Fecha', 'fecha'), ('monto', 'Monto', 'numero'),
            ('mes_corresponde', 'Mes', 'texto'), ('pendiente', 'Pendiente', 'numero'),
            ('pago_hasta', 'Pago hasta', 'fecha'),
        ], {'fecha': r[1], 'monto': r[2], 'mes_corresponde': r[3],
            'pendiente': r[4], 'pago_hasta': r[5]})

    def _editar_aseo_casa(self, r):
        self._editar_casa('casa_pagos', r[0], [
            ('mes_corresponde', 'Mes', 'texto'), ('tasa_aseo', 'Tasa', 'numero'),
        ], {'mes_corresponde': r[3], 'tasa_aseo': r[7]})

    def _editar_aseo_pago(self, r):
        self._editar_casa('casa_aseo_pagos', r[0], [
            ('fecha', 'Fecha', 'fecha'), ('monto_pagado', 'Pagado', 'numero'),
        ], {'fecha': r[1], 'monto_pagado': r[2]})

    def _editar_gasto_casa(self, r):
        self._editar_casa('casa_pagos', r[0], [
            ('gasto_fecha', 'Fecha', 'fecha'), ('gasto_concepto', 'Concepto', 'texto'),
            ('gasto_monto', 'Monto', 'numero'),
        ], {'gasto_fecha': r[10], 'gasto_concepto': r[11], 'gasto_monto': r[12]})

    def _editar_gasto(self, r):
        self._editar_casa('casa_gastos', r[0], [
            ('fecha', 'Fecha', 'fecha'), ('concepto', 'Concepto', 'texto'),
            ('monto', 'Monto', 'numero'), ('tipo', 'Tipo', 'texto'),
        ], {'fecha': r[1], 'concepto': r[2], 'monto': r[3], 'tipo': r[4]})

    def _editar_adic_casa(self, r):
        self._editar_casa('casa_pagos', r[0], [
            ('pago_adic_fecha', 'Fecha', 'fecha'),
            ('pago_adic_monto', 'Monto', 'numero'), ('ahorro', 'Ahorro', 'numero'),
        ], {'pago_adic_fecha': r[13], 'pago_adic_monto': r[14], 'ahorro': r[15]})

    def _editar_ahorro(self, r):
        self._editar_casa('casa_ahorro', r[0], [
            ('fecha', 'Fecha', 'fecha'), ('monto', 'Monto', 'numero'),
            ('concepto', 'Concepto', 'texto'),
        ], {'fecha': r[1], 'monto': r[2], 'concepto': r[3]})

    def _editar_deuda(self, p):
        self._editar_casa('casa_deuda_pagos', p[0], [
            ('fecha', 'Fecha', 'fecha'), ('monto_pagado', 'Monto', 'numero'),
            ('descripcion', 'Descripcion', 'texto'),
        ], {'fecha': p[1], 'monto_pagado': p[2], 'descripcion': p[3]})

    def _hdr(self, cols):
        h = BoxLayout(orientation='horizontal', size_hint_y=None, height='24dp', spacing=2, padding=[2, 1])
        with h.canvas.before:
            Color(rgba=[0.07, 0.65, 0.60, 1])
            h.k = RoundedRectangle(size=h.size, pos=h.pos, radius=[3])
        h.bind(size=lambda i, v: setattr(i.k, 'size', i.size))
        h.bind(pos=lambda i, v: setattr(i.k, 'pos', i.pos))
        for txt, w in cols:
            l = Label(text=txt, font_size='9sp', bold=True, color=[1,1,1,1], size_hint_x=w, halign='left', valign='middle')
            l.bind(size=lambda i, v: setattr(i, 'text_size', v))
            h.add_widget(l)
        return h

    # ===================== PAGOS ALQUILER =====================
    def _render_pagos(self, c):
        cid = self.cliente_actual_id
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM casa_pagos WHERE cliente_id=? AND fecha_pago IS NOT NULL AND fecha_pago != '' ORDER BY id DESC", (cid,))
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(monto),0) FROM casa_pagos_usuario WHERE cliente_id=?", (cid,))
        tot_user = cur.fetchone()[0]
        conn.close()

        tot_monto = sum(float(r[2] or 0) for r in rows)
        tot_pend = sum(float(r[4] or 0) for r in rows)
        total = tot_monto + tot_user

        form = RoundedCard(size_hint_y=None, height='200dp', bg_color=[1,1,1,1], padding=[10,6], spacing=4)
        form.add_widget(Label(text="Nuevo pago alquiler", font_size='10sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='16dp'))
        f0 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f0.add_widget(Label(text="Fecha:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_pf = DateInput(text=hoy_corto(), multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_pf.fuente = _sug_fechas_casa
        f0.add_widget(self.txt_pf)
        form.add_widget(f0)
        f1 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f1.add_widget(Label(text="Monto:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_pm = TextInput(hint_text="0.00", multiline=False, font_size='11sp', size_hint_x=0.7)
        f1.add_widget(self.txt_pm)
        form.add_widget(f1)
        f2 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f2.add_widget(Label(text="Mes:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_pd = CampoSugerencias(hint_text="ej: agosto", multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_pd.fuente = _sug_meses
        f2.add_widget(self.txt_pd)
        form.add_widget(f2)
        f3 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f3.add_widget(Label(text="Pendiente:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_pp = TextInput(hint_text="0.00", multiline=False, font_size='11sp', size_hint_x=0.7)
        f3.add_widget(self.txt_pp)
        form.add_widget(f3)
        f4 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f4.add_widget(Label(text="Pago Hasta:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_ph = DateInput(hint_text="DD/MM/AAAA", multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_ph.fuente = _sug_fechas_casa
        f4.add_widget(self.txt_ph)
        form.add_widget(f4)
        btn = AccentButton(text="Guardar", size_hint_y=None, height='28dp')
        btn.bind(on_press=self._save_pago)
        form.add_widget(btn)
        c.add_widget(form)

        if rows:
            c.add_widget(self._hdr([("Fecha",0.18),("Monto",0.13),("Mes",0.22),("Pend",0.12),("Hasta",0.17)]))
            for r in rows:
                pc = [0.90,0.30,0.35,1] if float(r[4] or 0)>0 else None
                c.add_widget(self._row([
                    (mostrar_fecha(r[1]), 0.18),
                    (f"${float(r[2] or 0):,.2f}", 0.13),
                    (str(r[3])[:20] if r[3] else '-', 0.22),
                    (f"${float(r[4] or 0):,.2f}", 0.12),
                    (mostrar_fecha(r[5]), 0.17),
                ], [None,None,None,pc,None],
                    on_edit=lambda rr=r: self._editar_pago_casa(rr)))

        if tot_user > 0:
            c.add_widget(Label(text="Tus pagos", font_size='9sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='18dp'))
            conn = get_db_connection()
            for fid,f,m,ms,p,ph in conn.execute("SELECT id, fecha, monto, mes_corresponde, pendiente, pago_hasta FROM casa_pagos_usuario WHERE cliente_id=? ORDER BY id DESC LIMIT 10", (cid,)):
                c.add_widget(self._row([
                    (mostrar_fecha(f),0.18),
                    (f"${float(m or 0):,.2f}",0.13),
                    (str(ms)[:20] if ms else '-',0.22),
                    (f"${float(p or 0):,.2f}",0.12),
                    (mostrar_fecha(ph),0.17),
                ],[None,[0.07,0.65,0.60,1],None,None,None],
                    on_edit=lambda rr=(fid,f,m,ms,p,ph): self._editar_pago_usuario(rr)))
            conn.close()

    def _save_pago(self, *args):
        v = self.txt_pm.text.strip()
        if not v: mostrar_error("Ingresa el monto."); return
        try: v = float(v)
        except: mostrar_error("Monto invalido."); return
        ms = self.txt_pd.text.strip()
        pp = self.txt_pp.text.strip()
        try: pp = float(pp) if pp else 0
        except: mostrar_error("Pendiente invalido."); return
        ph = self.txt_ph.text.strip()
        if ph:
            ph = fecha_iso(ph)
            if not ph:
                mostrar_error("\"Pago hasta\" no es una fecha válida.")
                return
        conn = get_db_connection()
        fe = fecha_de_campo(self.txt_pf, "fecha", self._now_str())
        if not fe:
            conn.close()
            return
        conn.execute("INSERT INTO casa_pagos_usuario (cliente_id, fecha, monto, mes_corresponde, pendiente, pago_hasta) VALUES (?,?,?,?,?,?)", (self.cliente_actual_id, fe, v, ms, pp, ph))
        close_db(conn)
        self.txt_pm.text = ""; self.txt_pd.text = ""; self.txt_pp.text = ""; self.txt_ph.text = ""
        self.txt_pf.text = hoy_corto()
        self._render_tab()

    # ===================== ASEO =====================
    def _render_aseo(self, c):
        cid = self.cliente_actual_id
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM casa_pagos WHERE cliente_id=? AND tasa_aseo > 0 ORDER BY id DESC", (cid,))
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(monto_pagado),0) FROM casa_aseo_pagos WHERE cliente_id=?", (cid,))
        pagado = cur.fetchone()[0]
        conn.close()

        tot_tasa = sum(float(r[7] or 0) for r in rows)
        pend = tot_tasa - pagado

        card = RoundedCard(size_hint_y=None, height='40dp', bg_color=[1,1,1,1], padding=[10,2])
        card.add_widget(Label(text=f"Adeudado: ${pend:,.2f}  |  Tasa: ${tot_tasa:,.2f}  |  Pagado: ${pagado:,.2f}", font_size='10sp', bold=True, color=[0.90,0.30,0.35,1] if pend>0 else [0.07,0.65,0.60,1]))
        c.add_widget(card)

        form = RoundedCard(size_hint_y=None, height='140dp', bg_color=[1,1,1,1], padding=[8,4], spacing=2)
        form.add_widget(Label(text="Agregar aseo", font_size='10sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='18dp'))
        f0 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f0.add_widget(Label(text="Fecha:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_a_fec = DateInput(multiline=False, font_size='10sp', size_hint_x=0.7)
        self.txt_a_fec.fuente = _sug_fechas_casa
        f0.add_widget(self.txt_a_fec)
        form.add_widget(f0)
        f1 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f1.add_widget(Label(text="Mes:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_a_mes = CampoSugerencias(hint_text="ej: marzo", multiline=False, font_size='10sp', size_hint_x=0.7)
        self.txt_a_mes.fuente = _sug_meses
        f1.add_widget(self.txt_a_mes)
        form.add_widget(f1)
        f2 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f2.add_widget(Label(text="Tasa:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_a_tasa = TextInput(hint_text="5.28", multiline=False, font_size='10sp', size_hint_x=0.7)
        f2.add_widget(self.txt_a_tasa)
        form.add_widget(f2)
        f3 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f3.add_widget(Label(text="Pagado:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_a_pagado = TextInput(hint_text="0.00", multiline=False, font_size='10sp', size_hint_x=0.7)
        f3.add_widget(self.txt_a_pagado)
        form.add_widget(f3)
        btn = AccentButton(text="Guardar", size_hint_y=None, height='26dp')
        btn.bind(on_press=self._save_aseo)
        form.add_widget(btn)
        c.add_widget(form)

        if rows:
            c.add_widget(self._hdr([("Mes",0.3),("Tasa",0.25),("Pagado",0.25)]))
            for r in rows:
                tase = float(r[7] or 0)
                c.add_widget(self._row([
                    (str(r[3])[:22] if r[3] else '-', 0.3),
                    (f"${tase:,.2f}" if tase else '-', 0.25),
                    (f"${pagado:,.2f}", 0.25),
                ], [None,None,None],
                    on_edit=lambda rr=r: self._editar_aseo_casa(rr)))

        if pagado > 0:
            c.add_widget(Label(text="Pagos realizados", font_size='9sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='16dp'))
            conn = get_db_connection()
            for fid,f,m in conn.execute("SELECT id, fecha, monto_pagado FROM casa_aseo_pagos WHERE cliente_id=? ORDER BY id DESC LIMIT 10", (cid,)):
                c.add_widget(self._row([(mostrar_fecha(f),0.4),(f"${float(m or 0):,.2f}",0.3)],
                                       [None,[0.07,0.65,0.60,1]],
                                       on_edit=lambda rr=(fid,f,m): self._editar_aseo_pago(rr)))
            conn.close()

    def _save_aseo(self, *args):
        tasa = self.txt_a_tasa.text.strip()
        if not tasa: mostrar_error("Ingresa la tasa."); return
        try: tasa = float(tasa)
        except: mostrar_error("Tasa invalida."); return
        pagado = self.txt_a_pagado.text.strip()
        try: pagado = float(pagado) if pagado else 0
        except: mostrar_error("Monto invalido."); return
        mes = self.txt_a_mes.text.strip()
        fe = fecha_de_campo(self.txt_a_fec, "fecha", self._now_str())
        if not fe:
            return
        conn = get_db_connection()
        conn.execute("INSERT INTO casa_pagos (cliente_id, fecha_pago, monto, mes_corresponde, tasa_aseo) VALUES (?,?,?,?,?)", (self.cliente_actual_id, fe, pagado, mes, tasa))
        if pagado > 0:
            conn.execute("INSERT INTO casa_aseo_pagos (cliente_id, fecha, monto_pagado) VALUES (?,?,?)", (self.cliente_actual_id, fe, pagado))
        close_db(conn)
        self.txt_a_mes.text = ""; self.txt_a_tasa.text = ""; self.txt_a_pagado.text = ""
        self.txt_a_fec.text = hoy_corto()
        self._render_tab()

    # ===================== GASTOS =====================
    def _render_gastos(self, c):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM casa_pagos WHERE gasto_monto > 0 OR gasto_concepto IS NOT NULL ORDER BY id DESC")
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(monto),0) FROM casa_gastos")
        ug = cur.fetchone()[0]
        conn.close()

        tot_pagos_gasto = sum(float(r[12] or 0) for r in rows)
        total = tot_pagos_gasto + ug

        form = RoundedCard(size_hint_y=None, height='180dp', bg_color=[1,1,1,1], padding=[10,6], spacing=4)
        form.add_widget(Label(text="Nuevo gasto", font_size='10sp', bold=True, color=[0.95,0.50,0.20,1], size_hint_y=None, height='16dp'))
        f0 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f0.add_widget(Label(text="Fecha:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_gf = DateInput(text=hoy_corto(), multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_gf.fuente = _sug_fechas_casa
        f0.add_widget(self.txt_gf)
        form.add_widget(f0)
        f1 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f1.add_widget(Label(text="Monto:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_gm = TextInput(hint_text="0.00", multiline=False, font_size='11sp', size_hint_x=0.7)
        f1.add_widget(self.txt_gm)
        form.add_widget(f1)
        f2 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f2.add_widget(Label(text="Concepto:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_gc = CampoSugerencias(hint_text="ej: pago seguro, universidad...", multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_gc.fuente = _sug_de('casa_gastos', 'concepto')
        f2.add_widget(self.txt_gc)
        form.add_widget(f2)
        f3 = BoxLayout(size_hint_y=None, height='24dp', spacing=4)
        f3.add_widget(Label(text="Tipo:", font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_gt = CampoSugerencias(hint_text="casa, prestamo, otro", text="casa", multiline=False, font_size='11sp', size_hint_x=0.7)
        self.txt_gt.fuente = _sug_de('casa_gastos', 'tipo')
        f3.add_widget(self.txt_gt)
        form.add_widget(f3)
        btn = AccentButton(text="Guardar", size_hint_y=None, height='28dp')
        btn.bind(on_press=self._save_gasto)
        form.add_widget(btn)
        c.add_widget(form)

        if rows:
            c.add_widget(self._hdr([("Fecha",0.25),("Concepto",0.45),("Monto",0.20)]))
            for r in rows:
                c.add_widget(self._row([
                    (mostrar_fecha(r[10]), 0.25),
                    (str(r[11])[:30] if r[11] else '-', 0.45),
                    (f"${float(r[12] or 0):,.2f}", 0.20),
                ], [None,None,[0.95,0.50,0.20,1]],
                    on_edit=lambda rr=r: self._editar_gasto_casa(rr)))

        if ug > 0:
            c.add_widget(Label(text="Tus gastos", font_size='9sp', bold=True, color=[0.95,0.50,0.20,1], size_hint_y=None, height='18dp'))
            conn = get_db_connection()
            for fid,f,con,m,tp in conn.execute("SELECT id, fecha, concepto, monto, tipo FROM casa_gastos ORDER BY id DESC LIMIT 10"):
                tipo_txt = str(tp)[:8] if tp else 'casa'
                c.add_widget(self._row([
                    (mostrar_fecha(f),0.2),
                    (str(con)[:30] if con else '-',0.35),
                    (f"${float(m or 0):,.2f}",0.15),
                    (tipo_txt,0.15),
                ],[None,None,[0.95,0.50,0.20,1],[0.95,0.70,0.20,1] if tp=='prestamo' else None],
                    on_edit=lambda rr=(fid,f,con,m,tp): self._editar_gasto(rr)))
            conn.close()

    def _save_gasto(self, *args):
        v = self.txt_gm.text.strip()
        if not v: mostrar_error("Ingresa el monto."); return
        try: v = float(v)
        except: mostrar_error("Monto invalido."); return
        con = self.txt_gc.text.strip()
        tp = self.txt_gt.text.strip() or 'casa'
        fe = fecha_de_campo(self.txt_gf, "fecha", self._now_str())
        if not fe:
            return
        conn = get_db_connection()
        conn.execute("INSERT INTO casa_gastos (fecha, concepto, monto, tipo) VALUES (?,?,?,?)", (fe, con, v, tp))
        close_db(conn)
        self.txt_gm.text = ""; self.txt_gc.text = ""; self.txt_gt.text = "casa"
        self.txt_gf.text = hoy_corto()
        self._render_tab()

    # ===================== AHORRO =====================
    def _render_ahorro(self, c):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM casa_pagos WHERE pago_adic_monto > 0 ORDER BY id DESC")
        pagos_adic = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(ahorro),0) FROM casa_ahorro")
        total_user = cur.fetchone()[0]
        cur.execute("SELECT * FROM casa_ahorro ORDER BY id DESC")
        user_rows = cur.fetchall()
        conn.close()

        tot_pagos_adic = sum(float(r[15] or 0) for r in pagos_adic)
        total = tot_pagos_adic + total_user

        card = RoundedCard(size_hint_y=None, height='40dp', bg_color=[1,1,1,1], padding=[10,2])
        card.add_widget(Label(text=f"Ahorrado: ${total:,.2f}", font_size='11sp', bold=True, color=[0.07,0.65,0.60,1]))
        c.add_widget(card)

        form = RoundedCard(size_hint_y=None, height='110dp', bg_color=[1,1,1,1], padding=[8,4], spacing=2)
        form.add_widget(Label(text="Agregar ahorro", font_size='10sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='16dp'))
        f0 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f0.add_widget(Label(text="Fecha:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_af = DateInput(text=hoy_corto(), multiline=False, font_size='10sp', size_hint_x=0.7)
        self.txt_af.fuente = _sug_fechas_casa
        f0.add_widget(self.txt_af)
        form.add_widget(f0)
        f1 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f1.add_widget(Label(text="Monto:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_am = TextInput(hint_text="0.00", multiline=False, font_size='10sp', size_hint_x=0.7)
        f1.add_widget(self.txt_am)
        form.add_widget(f1)
        f2 = BoxLayout(size_hint_y=None, height='22dp', spacing=4)
        f2.add_widget(Label(text="Concepto:", font_size='9sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_acon = CampoSugerencias(hint_text="ej: abono prestamo...", multiline=False, font_size='10sp', size_hint_x=0.7)
        self.txt_acon.fuente = _sug_de('casa_ahorro', 'concepto')
        f2.add_widget(self.txt_acon)
        form.add_widget(f2)
        btn = AccentButton(text="Guardar", size_hint_y=None, height='24dp')
        btn.bind(on_press=self._save_ahorro)
        form.add_widget(btn)
        c.add_widget(form)

        if pagos_adic:
            c.add_widget(Label(text="Pagos adicionales", font_size='9sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='18dp'))
            c.add_widget(self._hdr([("Fecha",0.3),("Monto",0.25),("Ahorro",0.25)]))
            for r in pagos_adic:
                ah = float(r[15] or 0)
                c.add_widget(self._row([
                    (mostrar_fecha(r[13]), 0.3),
                    (f"${float(r[14] or 0):,.2f}", 0.25),
                    (f"${ah:,.2f}" if ah > 0 else '-', 0.25),
                ], [None,None,[0.07,0.65,0.60,1] if ah > 0 else None],
                    on_edit=lambda rr=r: self._editar_adic_casa(rr)))

        if user_rows:
            c.add_widget(Label(text="Tus ahorros", font_size='9sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='18dp'))
            c.add_widget(self._hdr([("Fecha",0.3),("Monto",0.25),("Concepto",0.3)]))
            for r in user_rows:
                c.add_widget(self._row([
                    (mostrar_fecha(r[1]), 0.3),
                    (f"${float(r[2] or 0):,.2f}", 0.25),
                    (str(r[3])[:22] if r[3] else '-', 0.3),
                ], [None,[0.07,0.65,0.60,1],None],
                    on_edit=lambda rr=r: self._editar_ahorro(rr)))

    def _save_ahorro(self, *args):
        m = self.txt_am.text.strip()
        if not m: mostrar_error("Ingresa el monto."); return
        try: m = float(m)
        except: mostrar_error("Monto invalido."); return
        con = self.txt_acon.text.strip()
        fe = fecha_de_campo(self.txt_af, "fecha", self._now_str())
        if not fe:
            return
        conn = get_db_connection()
        conn.execute("INSERT INTO casa_ahorro (fecha, monto, concepto, ahorro) VALUES (?,?,?,?)", (fe, m, con, m))
        close_db(conn)
        self.txt_af.text = hoy_corto(); self.txt_am.text = ""; self.txt_acon.text = ""
        self._render_tab()

    # ===================== DEUDA =====================
    def _render_deuda(self, c):
        cid = self.cliente_actual_id
        conn = get_db_connection()
        cur = conn.cursor()
        row_deuda = cur.execute("SELECT deuda_total FROM clientes WHERE id=?", (cid,)).fetchone()
        tot_deuda = row_deuda[0] if row_deuda and row_deuda[0] else 0.0
        cur.execute("SELECT COALESCE(SUM(monto_pagado),0) FROM casa_deuda_pagos WHERE cliente_id=?", (cid,))
        pagado = cur.fetchone()[0]
        cur.execute("SELECT * FROM casa_deuda_pagos WHERE cliente_id=? ORDER BY id DESC", (cid,))
        pagos = cur.fetchall()
        conn.close()
        pend = tot_deuda - pagado

        form = RoundedCard(size_hint_y=None, height='160dp', bg_color=[1,1,1,1], padding=[12,8], spacing=6)
        form.add_widget(Label(text="Registrar pago de deuda", font_size='11sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='20dp'))

        f0 = BoxLayout(size_hint_y=None, height='32dp', spacing=6)
        f0.add_widget(Label(text="Fecha:", font_size='11sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_df = DateInput(text=hoy_corto(), multiline=False, font_size='12sp', size_hint_x=0.7)
        self.txt_df.fuente = _sug_fechas_casa
        f0.add_widget(self.txt_df)
        form.add_widget(f0)

        f1 = BoxLayout(size_hint_y=None, height='32dp', spacing=6)
        f1.add_widget(Label(text="Monto:", font_size='11sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_dp = TextInput(hint_text="0.00", multiline=False, font_size='12sp', size_hint_x=0.7)
        f1.add_widget(self.txt_dp)
        form.add_widget(f1)

        f2 = BoxLayout(size_hint_y=None, height='32dp', spacing=6)
        f2.add_widget(Label(text="Descripcion:", font_size='11sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3))
        self.txt_ddesc = CampoSugerencias(hint_text="ej: abono a deuda...", multiline=False, font_size='12sp', size_hint_x=0.7)
        self.txt_ddesc.fuente = _sug_de('casa_deuda_pagos', 'descripcion')
        f2.add_widget(self.txt_ddesc)
        form.add_widget(f2)

        btn = AccentButton(text="Guardar", size_hint_y=None, height='30dp')
        btn.bind(on_press=self._save_deuda)
        form.add_widget(btn)
        c.add_widget(form)

        card = RoundedCard(size_hint_y=None, height='40dp', bg_color=[1,1,1,1], padding=[10,4])
        card.add_widget(Label(text=f"Deuda: ${tot_deuda:,.2f}  |  Pagado: ${pagado:,.2f}  |  Pendiente: ${pend:,.2f}", font_size='10sp', bold=True, color=[0.90,0.30,0.35,1] if pend>0 else [0.07,0.65,0.60,1]))
        c.add_widget(card)

        c.add_widget(self._hdr([("Fecha",0.20),("Monto",0.18),("Descripcion",0.52)]))
        c.add_widget(self._row([
            ("31/03/2025", 0.20), ("$370.00", 0.18), ("Saldo pendiente hasta marzo", 0.52),
        ], [None,None,None]))
        c.add_widget(self._row([
            ("31/03/2025", 0.20), ("$95.04", 0.18), ("Saldo de basura", 0.52),
        ], [None,None,None]))
        c.add_widget(self._row([
            ("31/03/2025", 0.20), ("$10.00", 0.18), ("Saldos pendientes de pago de mes", 0.52),
        ], [None,None,None]))

        if pagos:
            c.add_widget(Label(text="Pagos realizados", font_size='10sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_y=None, height='20dp'))
            c.add_widget(self._hdr([("Fecha",0.25),("Monto",0.20),("Descripcion",0.45)]))
            for p in pagos:
                c.add_widget(self._row([
                    (mostrar_fecha(p[1]), 0.25),
                    (f"${float(p[2] or 0):,.2f}", 0.20),
                    (str(p[3])[:28] if p[3] else '-', 0.45),
                ], [None,[0.07,0.65,0.60,1],None],
                    on_edit=lambda rr=p: self._editar_deuda(rr)))

    def _save_deuda(self, *args):
        v = self.txt_dp.text.strip()
        if not v: mostrar_error("Ingresa el monto."); return
        try: v = float(v)
        except: mostrar_error("Monto invalido."); return
        fe = fecha_de_campo(self.txt_df, "fecha", self._now_str())
        if not fe:
            return
        desc = self.txt_ddesc.text.strip()
        conn = get_db_connection()
        conn.execute("INSERT INTO casa_deuda_pagos (cliente_id, fecha, monto_pagado, descripcion) VALUES (?,?,?,?)", (self.cliente_actual_id, fe, v, desc))
        conn.execute("INSERT INTO casa_ahorro (cliente_id, fecha, monto, concepto, ahorro) VALUES (?,?,?,?,?)", (self.cliente_actual_id, fe, v, "Abono de deuda", v))
        close_db(conn)
        self.txt_dp.text = ""
        self.txt_ddesc.text = ""
        self.txt_df.text = hoy_corto()
        self._render_tab()


class LoginScreen(Screen):
    """Pantalla de inicio de sesion contra Supabase Auth."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', padding=[26, 46], spacing=12)
        with root.canvas.before:
            Color(*SURFACE_ALT)
            self._fondo = Rectangle(size=root.size, pos=root.pos)
        root.bind(size=lambda w, s: setattr(self._fondo, 'size', s))
        root.bind(pos=lambda w, p: setattr(self._fondo, 'pos', p))

        titulo = KivyLabel(text='InDrive Finanzas', font_size='25sp', bold=True,
                           color=list(TEXT_PRIMARY), size_hint_y=None, height='46dp')
        sub = KivyLabel(text='Inicia sesion para guardar tus datos\nen la nube y no perderlos si se daña el telefono',
                        font_size='12sp', color=list(TEXT_SECONDARY),
                        size_hint_y=None, height='46dp')
        sub.bind(size=lambda i, v: setattr(i, 'text_size', v))
        sub.bind(size=lambda i, v: setattr(i, 'halign', 'center'))
        root.add_widget(titulo)
        root.add_widget(sub)

        self.txt_email = TextInput(hint_text='Correo electronico', multiline=False,
                                   size_hint_y=None, height='44dp', font_size='14sp',
                                   padding=[10, 12])
        self.txt_pass = TextInput(hint_text='Contrasena', password=True, multiline=False,
                                  size_hint_y=None, height='44dp', font_size='14sp',
                                  padding=[10, 12])
        root.add_widget(self.txt_email)
        root.add_widget(self.txt_pass)

        self.lbl_estado = KivyLabel(text='', font_size='11sp', color=list(NEG),
                                    size_hint_y=None, height='40dp')
        self.lbl_estado.bind(size=lambda i, v: setattr(i, 'text_size', v))
        self.lbl_estado.bind(size=lambda i, v: setattr(i, 'halign', 'center'))
        root.add_widget(self.lbl_estado)

        btn_entrar = AccentButton(text='Entrar', size_hint_y=None, height='46dp',
                                  font_size='15sp', bold=True)
        btn_entrar.bind(on_press=self._entrar)
        root.add_widget(btn_entrar)

        btn_off = Button(text='Continuar sin conexion', size_hint_y=None, height='42dp',
                         font_size='12sp', background_normal='',
                         background_color=SURFACE, color=list(TEXT_SECONDARY))
        btn_off.bind(on_press=self._sin_sesion)
        root.add_widget(btn_off)

        nota = KivyLabel(text='Si no tienes conexion ahora, podras iniciar\nsesion mas tarde desde este mismo telefono.',
                         font_size='10sp', color=list(TEXT_SECONDARY),
                         size_hint_y=None, height='36dp')
        nota.bind(size=lambda i, v: setattr(i, 'text_size', v))
        nota.bind(size=lambda i, v: setattr(i, 'halign', 'center'))
        root.add_widget(nota)

        self.add_widget(root)

    def _entrar(self, *args):
        email = self.txt_email.text.strip()
        password = self.txt_pass.text
        if not email or not password:
            self.lbl_estado.text = 'Correo y contrasena requeridos'
            return
        self.lbl_estado.text = 'Iniciando sesion...'
        self.lbl_estado.color = list(TEXT_SECONDARY)

        def _trabajo():
            ok = cloud_db.sign_in(email, password)
            Clock.schedule_once(lambda dt: self._tras_inicio(ok), 0)

        threading.Thread(target=_trabajo, daemon=True).start()

    def _tras_inicio(self, ok):
        if not ok:
            self.lbl_estado.color = list(NEG)
            self.lbl_estado.text = cloud_db.detalle_estado() or 'No se pudo iniciar sesion'
            return
        self.lbl_estado.color = [0.07, 0.65, 0.60, 1]
        if cloud_db.datos_locales_vacios():
            self.lbl_estado.text = 'Descargando tus datos...'

            def _trabajo():
                cloud_db.pull_tras_login()
                Clock.schedule_once(lambda dt: self._ir_a_app(), 0)

            threading.Thread(target=_trabajo, daemon=True).start()
        else:
            self.lbl_estado.text = 'Subiendo tus datos...'
            cloud_db.push_all()
            self._ir_a_app()

    def _ir_a_app(self):
        if self.manager:
            self.manager.current = 'dashboard'

    def _sin_sesion(self, *args):
        cloud_db.avisar('Sin sesion: los datos se guardan solo en este telefono')
        if self.manager:
            self.manager.current = 'dashboard'


class InDriveApp(App):
    def build(self):
        global writable_db_path
        from kivy.utils import platform
        
        local_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
        
        if platform == 'android':
            writable_dir = self.user_data_dir
            if not os.path.exists(writable_dir):
                os.makedirs(writable_dir)
            writable_db_path = os.path.join(writable_dir, DB_NAME)
            
            db_is_empty = True
            if os.path.exists(writable_db_path):
                try:
                    conn = sqlite3.connect(writable_db_path)
                    cur = conn.cursor()
                    cur.execute("SELECT count(*) FROM transacciones")
                    count = cur.fetchone()[0]
                    if count > 0:
                        db_is_empty = False
                    conn.close()
                except Exception as e:
                    pass
            
            if os.path.exists(local_db) and (not os.path.exists(writable_db_path) or db_is_empty):
                try:
                    import shutil
                    shutil.copy(local_db, writable_db_path)
                except Exception as e:
                    pass
        else:
            writable_db_path = local_db

        # --- Sincronizacion con Supabase ---
        descargar = False
        try:
            cloud_db.init(writable_db_path, self.user_data_dir)
            descargar = cloud_db.preparar_pull_si_vacio()
        except Exception:
            descargar = False

        init_database()
        # Si hay que bajar datos de la nube, no sembramos la BD local:
        # la nube manda. Si no, se mantiene el importado del Excel.
        if not descargar:
            importar_casa_pagos()
        
        Builder.load_string(KV)
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(DashboardScreen(name='dashboard'))
        sm.add_widget(AhorroScreen(name='ahorro'))
        sm.add_widget(CarroScreen(name='carro'))
        sm.add_widget(CasaScreen(name='casa'))
        sm.add_widget(StatsScreen(name='stats'))
        sm.add_widget(CalendarScreen(name='calendar'))
        sm.current = 'dashboard' if cloud_db.hay_sesion() else 'login'

        if descargar:
            Clock.schedule_once(lambda dt: self._descargar_al_iniciar(), 1.0)
        elif cloud_db.hay_sesion():
            # Sube cambios que hayan quedado pendientes de la sesion anterior
            Clock.schedule_once(lambda dt: cloud_db.sync_after_write(), 4.0)

        if cloud_db.hay_sesion():
            Clock.schedule_once(lambda dt: self._validar_sesion(), 1.5)

        return sm

    def _validar_sesion(self):
        """Si el token guardado ya no sirve, vuelve a la pantalla de login."""
        def _trabajo():
            if cloud_db.sesion_valida():
                return
            Clock.schedule_once(lambda dt: self._ir_a_login(), 0)
        threading.Thread(target=_trabajo, daemon=True).start()

    def _ir_a_login(self):
        try:
            sm = self.root
            if sm is not None and sm.has_screen('login'):
                sm.current = 'login'
        except Exception:
            pass

    def _descargar_al_iniciar(self):
        def _trabajo():
            if cloud_db.pull_all():
                Clock.schedule_once(lambda dt: self._refrescar_pantalla(), 0)
        threading.Thread(target=_trabajo, daemon=True).start()

    def _refrescar_pantalla(self):
        try:
            sm = self.root
            scr = sm.current_screen if sm else None
            if scr is None:
                return
            if hasattr(scr, 'refresh_data'):
                scr.refresh_data()
            elif hasattr(scr, '_render_inicio'):
                scr._render_inicio()
            elif hasattr(scr, 'on_enter'):
                scr.on_enter()
        except Exception:
            pass

    def on_start(self):
        Window.bind(on_keyboard=self._on_key_down)
        super().on_start()

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        if key != 27:
            return False
        # Atras en tres pasos: primero cierra el teclado, luego cualquier
        # ventana superpuesta y solo al final navega. Sin esto, escribir en
        # un campo salia de la pantalla en cuanto se tocaba Atras.
        widget = getattr(window, 'focus', None)
        if widget is not None and getattr(widget, 'focus', False):
            try:
                widget.focus = False
            except Exception:
                pass
            return True
        try:
            superiores = list(getattr(window, 'children', []) or [])
        except Exception:
            superiores = []
        for hijo in reversed(superiores):
            nombre = hijo.__class__.__name__
            if nombre in ('Popup', 'DropDown', 'ModalView'):
                try:
                    hijo.dismiss()
                except Exception:
                    pass
                return True
        self._handle_back()
        return True

    def _handle_back(self):
        from kivy.uix.popup import Popup
        from kivy.uix.label import Label as KivyLabel
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button

        sm = self.root
        current = sm.current

        if current in ('dashboard', 'login'):
            content = BoxLayout(orientation='vertical', spacing=10, padding=10)
            lbl = KivyLabel(text="¿Salir de la app?", font_size='16sp', color=[0.08, 0.08, 0.09, 1])
            btns = BoxLayout(size_hint_y=None, height='40dp', spacing=10)
            popup_ref = [None]

            def on_no(instance):
                popup_ref[0].dismiss()

            def on_yes(instance):
                popup_ref[0].dismiss()
                App.get_running_app().stop()

            btn_no = Button(text='No', on_press=on_no, size_hint_x=0.5)
            btn_yes = Button(text='Si', on_press=on_yes, size_hint_x=0.5)
            btns.add_widget(btn_no)
            btns.add_widget(btn_yes)
            content.add_widget(lbl)
            content.add_widget(btns)
            popup_ref[0] = Popup(title='Confirmar', content=content, size_hint=(0.6, 0.3))
            popup_ref[0].open()
        else:
            if current == 'casa':
                casa_screen = sm.get_screen('casa')
                casa_screen._volver_atras()
            else:
                screen_names = ['calendar', 'stats', 'carro', 'ahorro', 'casa']
                if current in screen_names:
                    idx = screen_names.index(current)
                    if idx > 0:
                        sm.current = screen_names[idx - 1]
                    else:
                        sm.current = 'dashboard'
                else:
                    sm.current = 'dashboard'

    def on_pause(self):
        # El telefono se va a segundo plano: sube lo pendiente ya.
        # Se limita el tiempo para no congelar la interfaz de Android.
        try:
            cloud_db.push_inmediato(timeout_total=4)
        except Exception:
            pass
        return True

    def on_stop(self):
        try:
            cloud_db.push_inmediato(timeout_total=3)
        except Exception:
            pass
        super().on_stop()


if __name__ == '__main__':
    InDriveApp().run()