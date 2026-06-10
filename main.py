import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from kivy.uix.popup import Popup
from kivy.uix.label import Label as KivyLabel

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

def init_database():
    """Inicializa la base de datos VACÍA - sin datos automáticos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Crear tablas
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
        CREATE TABLE IF NOT EXISTS alquiler_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_pago TEXT,
            monto REAL,
            mes_corresponde TEXT,
            pendiente REAL DEFAULT 0,
            pago_hasta TEXT,
            descripcion TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos_adicionales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            concepto TEXT,
            monto REAL,
            descripcion TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasa_aseo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT,
            anio INTEGER,
            monto REAL,
            pagado BOOLEAN DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    print("Base de datos inicializada VACÍA")

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

        ScrollView:
            size_hint_y: 0.60
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 12
                padding: [0, 5, 0, 5]

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

                RoundedCard:
                    size_hint_y: None
                    height: '90dp'
                    bg_color: [1, 1, 1, 1]
                    Label:
                        text: "ALQUILER CASA"
                        font_size: '12sp'
                        bold: True
                        color: 0.3, 0.3, 0.35, 1
                        size_hint_y: None
                        height: '20dp'
                    Label:
                        text: root.balance_casa
                        font_size: '28sp'
                        bold: True
                        color: root.color_casa

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
                CustomTextInput:
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
                CustomTextInput:
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


<CasaScreen>:
    name: 'casa'
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
            height: '50dp'
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
                text: "ALQUILER CASA"
                font_size: '18sp'
                bold: True
                color: 0.08, 0.08, 0.09, 1
                halign: 'center'

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 10
                padding: [5, 5, 5, 5]

                RoundedCard:
                    size_hint_y: None
                    height: '240dp'
                    bg_color: [1, 1, 1, 1]
                    BoxLayout:
                        orientation: 'vertical'
                        padding: [12, 10]
                        spacing: 12
                        
                        BoxLayout:
                            size_hint_y: None
                            height: '40dp'
                            Label:
                                text: "TOTAL DE AHORRO"
                                font_size: '14sp'
                                bold: True
                                color: 0.3, 0.3, 0.35, 1
                            Label:
                                text: root.total_ahorro
                                font_size: '22sp'
                                bold: True
                                color: 0.07, 0.65, 0.60, 1
                                halign: 'right'
                                size_hint_x: 0.45
                        
                        BoxLayout:
                            size_hint_y: None
                            height: '40dp'
                            Label:
                                text: "DEUDA PENDIENTE"
                                font_size: '14sp'
                                bold: True
                                color: 0.3, 0.3, 0.35, 1
                            Label:
                                text: root.deuda_pendiente
                                font_size: '22sp'
                                bold: True
                                color: 0.90, 0.30, 0.35, 1
                                halign: 'right'
                                size_hint_x: 0.45
                        
                        BoxLayout:
                            size_hint_y: None
                            height: '40dp'
                            Label:
                                text: "PENDIENTE POR PAGAR"
                                font_size: '14sp'
                                bold: True
                                color: 0.3, 0.3, 0.35, 1
                            Label:
                                text: root.pendiente_por_pagar
                                font_size: '22sp'
                                bold: True
                                color: 0.90, 0.30, 0.35, 1
                                halign: 'right'
                                size_hint_x: 0.45
                        
                        BoxLayout:
                            size_hint_y: None
                            height: '40dp'
                            Label:
                                text: "SALDO PENDIENTE"
                                font_size: '14sp'
                                bold: True
                                color: 0.3, 0.3, 0.35, 1
                            Label:
                                text: root.saldo_pendiente
                                font_size: '22sp'
                                bold: True
                                color: 0.90, 0.30, 0.35, 1
                                halign: 'right'
                                size_hint_x: 0.45

                RoundedCard:
                    size_hint_y: None
                    height: '220dp'
                    bg_color: [1, 1, 1, 1]
                    BoxLayout:
                        orientation: 'vertical'
                        padding: [8, 8]
                        spacing: 6
                        Label:
                            text: "TASAS DE ASEO ($5.28/mes)"
                            font_size: '14sp'
                            bold: True
                            color: 0.08, 0.08, 0.09, 1
                            size_hint_y: None
                            height: '30dp'
                        ScrollView:
                            do_scroll_x: True
                            do_scroll_y: True
                            GridLayout:
                                id: tasa_aseo_grid
                                cols: 4
                                spacing: 8
                                size_hint_x: None
                                width: self.minimum_width
                                padding: [4, 4]
                                row_default_height: '70dp'

                RoundedCard:
                    size_hint_y: None
                    height: '340dp'
                    bg_color: [1, 1, 1, 1]
                    BoxLayout:
                        orientation: 'vertical'
                        spacing: 10
                        padding: [12, 10]
                        Label:
                            text: "REGISTRAR NUEVO PAGO"
                            font_size: '14sp'
                            bold: True
                            color: 0.08, 0.08, 0.09, 1
                            size_hint_y: None
                            height: '30dp'
                        GridLayout:
                            cols: 2
                            spacing: 10
                            size_hint_y: None
                            height: '220dp'
                            Label:
                                text: "Fecha de Pago:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: casa_fecha
                                text: datetime.now().strftime("%d/%m/%Y")
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Monto:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: casa_monto
                                hint_text: "0.00"
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Mes que corresponde:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: casa_mes
                                hint_text: "Ej: enero 2025"
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Monto Pendiente:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: casa_pendiente
                                hint_text: "0.00"
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Descripción:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: casa_desc
                                hint_text: "Nota"
                                size_hint_y: None
                                height: '35dp'
                        AccentButton:
                            text: "GUARDAR PAGO"
                            bg_normal: [0.07, 0.65, 0.60, 1]
                            size_hint_y: None
                            height: '45dp'
                            on_press: root.save_pago()

                RoundedCard:
                    size_hint_y: None
                    height: '320dp'
                    bg_color: [1, 1, 1, 1]
                    BoxLayout:
                        orientation: 'vertical'
                        spacing: 10
                        padding: [12, 10]
                        Label:
                            text: "GASTOS ADICIONALES"
                            font_size: '14sp'
                            bold: True
                            color: 0.08, 0.08, 0.09, 1
                            size_hint_y: None
                            height: '30dp'
                        GridLayout:
                            cols: 2
                            spacing: 10
                            size_hint_y: None
                            height: '200dp'
                            Label:
                                text: "Fecha:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: gasto_fecha
                                text: datetime.now().strftime("%d/%m/%Y")
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Concepto:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: gasto_concepto
                                hint_text: "Ej: seguro"
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Monto:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: gasto_monto
                                hint_text: "0.00"
                                size_hint_y: None
                                height: '35dp'
                            Label:
                                text: "Descripción:"
                                font_size: '12sp'
                                bold: True
                                color: 0.08, 0.08, 0.09, 1
                                size_hint_y: None
                                height: '35dp'
                            CustomTextInput:
                                id: gasto_desc
                                hint_text: "Nota"
                                size_hint_y: None
                                height: '35dp'
                        AccentButton:
                            text: "GUARDAR GASTO"
                            bg_normal: [0.07, 0.65, 0.60, 1]
                            size_hint_y: None
                            height: '45dp'
                            on_press: root.save_gasto()

                Label:
                    text: "HISTORIAL DE PAGOS"
                    font_size: '14sp'
                    bold: True
                    color: 0.08, 0.08, 0.09, 1
                    size_hint_y: None
                    height: '30dp'

                RoundedCard:
                    size_hint_y: None
                    height: '250dp'
                    bg_color: [1, 1, 1, 1]
                    ScrollView:
                        BoxLayout:
                            id: list_pagos
                            orientation: 'vertical'
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: 6
                            padding: [8, 8]

                Label:
                    text: "HISTORIAL DE GASTOS"
                    font_size: '14sp'
                    bold: True
                    color: 0.08, 0.08, 0.09, 1
                    size_hint_y: None
                    height: '30dp'

                RoundedCard:
                    size_hint_y: None
                    height: '250dp'
                    bg_color: [1, 1, 1, 1]
                    ScrollView:
                        BoxLayout:
                            id: list_gastos
                            orientation: 'vertical'
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: 6
                            padding: [8, 8]


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
                    on_press: root.manager.current = 'dashboard'
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
"""

# --- SCREENS ---

class DashboardScreen(Screen):
    balance_ahorro = StringProperty("$0.00")
    balance_carro = StringProperty("$0.00")
    balance_casa = StringProperty("$0.00")
    color_carro = ObjectProperty([0.07, 0.65, 0.60, 1])
    color_casa = ObjectProperty([0.07, 0.65, 0.60, 1])

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

        # Alquiler Casa
        cursor.execute("SELECT SUM(monto) FROM alquiler_pagos")
        total_pagado = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(monto) FROM gastos_adicionales")
        total_gastos = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(monto) FROM tasa_aseo WHERE pagado = 0")
        tasa_pendiente = cursor.fetchone()[0] or 0.0
        
        # FÓRMULA CORRECTA SEGÚN EXCEL
        saldo_casa = total_pagado - (total_gastos + tasa_pendiente)
        self.balance_casa = f"${saldo_casa:,.2f}"
        self.color_casa = [0.07, 0.65, 0.60, 1] if saldo_casa >= 0 else [0.90, 0.30, 0.35, 1]

        conn.close()


class CasaScreen(Screen):
    total_ahorro = StringProperty("$0.00")
    deuda_pendiente = StringProperty("$0.00")
    pendiente_por_pagar = StringProperty("$0.00")
    saldo_pendiente = StringProperty("$0.00")
    
    def on_enter(self, *args):
        Clock.schedule_once(lambda dt: self.refresh_all(), 0.1)
    
    def refresh_all(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total pagado de alquiler
        cursor.execute("SELECT SUM(monto) FROM alquiler_pagos")
        total_pagado = cursor.fetchone()[0] or 0.0
        
        # Total gastos adicionales
        cursor.execute("SELECT SUM(monto) FROM gastos_adicionales")
        total_gastos = cursor.fetchone()[0] or 0.0
        
        # Tasa de aseo pendiente
        cursor.execute("SELECT SUM(monto) FROM tasa_aseo WHERE pagado = 0")
        tasa_pendiente = cursor.fetchone()[0] or 0.0
        
        # Pendiente de pagos de alquiler
        cursor.execute("SELECT SUM(pendiente) FROM alquiler_pagos")
        pendiente_pagos = cursor.fetchone()[0] or 0.0
        
        # ✅ FÓRMULAS SEGÚN EL EXCEL
        total_ahorro_calc = total_pagado - total_gastos - tasa_pendiente
        deuda_total = total_gastos + tasa_pendiente
        pendiente_total = deuda_total + pendiente_pagos
        saldo_pendiente_total = pendiente_pagos + tasa_pendiente
        
        self.total_ahorro = f"${total_ahorro_calc:,.2f}"
        self.deuda_pendiente = f"${deuda_total:,.2f}"
        self.pendiente_por_pagar = f"${pendiente_total:,.2f}"
        self.saldo_pendiente = f"${saldo_pendiente_total:,.2f}"
        
        print(f"\n=== VALORES CALCULADOS ===")
        print(f"total_pagado: {total_pagado}")
        print(f"total_gastos: {total_gastos}")
        print(f"tasa_pendiente: {tasa_pendiente}")
        print(f"pendiente_pagos: {pendiente_pagos}")
        print(f"TOTAL AHORRO: {total_ahorro_calc}")
        print(f"DEUDA PENDIENTE: {deuda_total}")
        print(f"PENDIENTE POR PAGAR: {pendiente_total}")
        print(f"SALDO PENDIENTE: {saldo_pendiente_total}")
        print(f"========================\n")
        
        # Cargar Grid de Tasas de Aseo
        tasa_grid = self.ids.tasa_aseo_grid
        tasa_grid.clear_widgets()
        
        cursor.execute("SELECT id, mes, anio, monto, pagado FROM tasa_aseo ORDER BY anio, " +
                      "CASE mes " +
                      "WHEN 'enero' THEN 1 WHEN 'febrero' THEN 2 WHEN 'marzo' THEN 3 " +
                      "WHEN 'abril' THEN 4 WHEN 'mayo' THEN 5 WHEN 'junio' THEN 6 " +
                      "WHEN 'julio' THEN 7 WHEN 'agosto' THEN 8 WHEN 'septiembre' THEN 9 " +
                      "WHEN 'octubre' THEN 10 WHEN 'noviembre' THEN 11 WHEN 'diciembre' THEN 12 END")
        tasas = cursor.fetchall()
        
        # Botón para agregar nueva tasa
        btn_agregar = Button(
            text="+ AGREGAR TASA",
            size_hint_y=None,
            height='70dp',
            size_hint_x=None,
            width='95dp',
            background_normal='',
            background_color=[0.3, 0.3, 0.35, 0.7],
            color=[1, 1, 1, 1],
            font_size='11sp',
            bold=True
        )
        btn_agregar.bind(on_press=lambda btn: self.agregar_tasa())
        tasa_grid.add_widget(btn_agregar)
        
        for tasa in tasas:
            tid = tasa[0]
            mes = tasa[1]
            anio = tasa[2]
            monto = tasa[3]
            pagado = tasa[4]
            
            estado = "✓" if pagado else "⭕"
            bg_color = [0.07, 0.65, 0.60, 1] if pagado else [0.90, 0.30, 0.35, 1]
            
            btn = Button(
                text=f"{mes} {anio}\n${monto:,.2f}\n{estado}",
                size_hint_y=None,
                height='70dp',
                size_hint_x=None,
                width='95dp',
                background_normal='',
                background_color=bg_color,
                color=[1, 1, 1, 1],
                font_size='11sp',
                bold=True,
                halign='center',
                valign='middle'
            )
            btn.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
            
            if not pagado:
                btn.bind(on_press=lambda btn, iid=tid: self.pagar_tasa(iid))
            
            tasa_grid.add_widget(btn)
        
        # Cargar lista de pagos
        pagos_container = self.ids.list_pagos
        pagos_container.clear_widgets()
        cursor.execute("SELECT id, fecha_pago, monto, mes_corresponde, pendiente, descripcion FROM alquiler_pagos ORDER BY fecha_pago DESC LIMIT 30")
        pagos = cursor.fetchall()
        
        if not pagos:
            pagos_container.add_widget(Label(text="No hay pagos registrados", size_hint_y=None, height='40dp', color=[0.5,0.5,0.5,1]))
        else:
            for p in pagos:
                pid = p[0]
                fecha = p[1] if p[1] else ""
                monto = p[2] if p[2] else 0
                mes = p[3] if p[3] else ""
                pendiente = p[4] if p[4] else 0
                
                item = BoxLayout(orientation='horizontal', size_hint_y=None, height='50dp', spacing=8, padding=[10, 8])
                with item.canvas.before:
                    Color(rgba=[0.95, 0.95, 0.96, 1])
                    RoundedRectangle(size=item.size, pos=item.pos, radius=[8])
                
                lbl_fecha = Label(text=fecha[:10] if len(fecha) > 10 else fecha, font_size='11sp', color=[0.08,0.08,0.09,1], size_hint_x=0.22)
                lbl_monto = Label(text=f"${monto:,.2f}", font_size='12sp', bold=True, color=[0.07,0.65,0.60,1], size_hint_x=0.18)
                lbl_mes = Label(text=(mes[:15] if mes else "-"), font_size='10sp', color=[0.3,0.3,0.35,1], size_hint_x=0.3)
                lbl_pend = Label(text=f"${pendiente:,.2f}", font_size='11sp', color=[0.90,0.30,0.35,1] if pendiente > 0 else [0.07,0.65,0.60,1], size_hint_x=0.15)
                btn_del = Button(text="✗", size_hint_x=None, width='35dp', background_color=[0,0,0,0], color=[0.9,0.3,0.3,1], font_size='14sp', bold=True)
                btn_del.bind(on_press=lambda btn, iid=pid: self.delete_pago(iid))
                
                item.add_widget(lbl_fecha)
                item.add_widget(lbl_monto)
                item.add_widget(lbl_mes)
                item.add_widget(lbl_pend)
                item.add_widget(btn_del)
                pagos_container.add_widget(item)
        
        # Cargar lista de gastos
        gastos_container = self.ids.list_gastos
        gastos_container.clear_widgets()
        cursor.execute("SELECT id, fecha, concepto, monto, descripcion FROM gastos_adicionales ORDER BY fecha DESC LIMIT 30")
        gastos = cursor.fetchall()
        
        if not gastos:
            gastos_container.add_widget(Label(text="No hay gastos registrados", size_hint_y=None, height='40dp', color=[0.5,0.5,0.5,1]))
        else:
            for g in gastos:
                gid = g[0]
                fecha = g[1] if g[1] else ""
                concepto = g[2] if g[2] else ""
                monto = g[3] if g[3] else 0
                
                item = BoxLayout(orientation='horizontal', size_hint_y=None, height='50dp', spacing=8, padding=[10, 8])
                with item.canvas.before:
                    Color(rgba=[0.95, 0.95, 0.96, 1])
                    RoundedRectangle(size=item.size, pos=item.pos, radius=[8])
                
                lbl_fecha = Label(text=fecha[:10] if len(fecha) > 10 else fecha, font_size='11sp', color=[0.08,0.08,0.09,1], size_hint_x=0.22)
                lbl_concepto = Label(text=(concepto[:20] if concepto else "-"), font_size='11sp', color=[0.08,0.08,0.09,1], size_hint_x=0.45)
                lbl_monto = Label(text=f"${monto:,.2f}", font_size='12sp', bold=True, color=[0.90,0.30,0.35,1], size_hint_x=0.2)
                btn_del = Button(text="✗", size_hint_x=None, width='35dp', background_color=[0,0,0,0], color=[0.9,0.3,0.3,1], font_size='14sp', bold=True)
                btn_del.bind(on_press=lambda btn, iid=gid: self.delete_gasto(iid))
                
                item.add_widget(lbl_fecha)
                item.add_widget(lbl_concepto)
                item.add_widget(lbl_monto)
                item.add_widget(btn_del)
                gastos_container.add_widget(item)
        
        conn.close()
    
    def agregar_tasa(self):
        from kivy.uix.spinner import Spinner
        
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        spinner_mes = Spinner(text='Seleccione mes', values=meses, size_hint_y=None, height='40dp')
        txt_anio = TextInput(text=str(datetime.now().year), hint_text='Año', multiline=False, size_hint_y=None, height='40dp')
        txt_monto = TextInput(text='5.28', hint_text='Monto', multiline=False, size_hint_y=None, height='40dp')
        
        btn_guardar = Button(text='Guardar Tasa', size_hint_y=None, height='45dp', 
                            background_color=[0.07, 0.65, 0.60, 1], color=[1,1,1,1])
        
        content.add_widget(Label(text='Mes:', size_hint_y=None, height='30dp'))
        content.add_widget(spinner_mes)
        content.add_widget(Label(text='Año:', size_hint_y=None, height='30dp'))
        content.add_widget(txt_anio)
        content.add_widget(Label(text='Monto:', size_hint_y=None, height='30dp'))
        content.add_widget(txt_monto)
        content.add_widget(btn_guardar)
        
        popup = Popup(title='Agregar Tasa de Aseo', content=content, size_hint=(0.8, 0.5))
        
        def guardar_tasa(instance):
            mes = spinner_mes.text
            anio = txt_anio.text
            monto = float(txt_monto.text) if txt_monto.text else 5.28
            
            if mes != 'Seleccione mes' and anio:
                conn = get_db_connection()
                conn.execute("INSERT INTO tasa_aseo (mes, anio, monto, pagado) VALUES (?, ?, ?, ?)",
                            (mes, int(anio), monto, 0))
                conn.commit()
                conn.close()
                popup.dismiss()
                self.refresh_all()
                App.get_running_app().root.get_screen('dashboard').refresh_data()
        
        btn_guardar.bind(on_press=guardar_tasa)
        popup.open()
    
    def pagar_tasa(self, tasa_id):
        conn = get_db_connection()
        conn.execute("UPDATE tasa_aseo SET pagado = 1 WHERE id = ?", (tasa_id,))
        conn.commit()
        conn.close()
        self.refresh_all()
        App.get_running_app().root.get_screen('dashboard').refresh_data()
    
    def save_pago(self):
        fecha = self.ids.casa_fecha.text.strip()
        monto_s = self.ids.casa_monto.text.strip()
        mes = self.ids.casa_mes.text.strip()
        pendiente_s = self.ids.casa_pendiente.text.strip()
        desc = self.ids.casa_desc.text.strip()
        
        if not fecha:
            mostrar_error("Por favor ingresa la fecha del pago.")
            return
        if not monto_s:
            mostrar_error("Por favor ingresa el monto del pago.")
            return
        
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 150.00")
            return
        
        pendiente = 0.0
        if pendiente_s:
            try:
                pendiente = float(pendiente_s)
            except:
                mostrar_error("El monto pendiente debe ser un número válido.\nEjemplo: 50.00")
                return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alquiler_pagos (fecha_pago, monto, mes_corresponde, pendiente, descripcion)
            VALUES (?, ?, ?, ?, ?)
        """, (fecha, monto, mes, pendiente, desc))
        conn.commit()
        conn.close()
        
        self.ids.casa_monto.text = ""
        self.ids.casa_mes.text = ""
        self.ids.casa_pendiente.text = ""
        self.ids.casa_desc.text = ""
        
        self.refresh_all()
        App.get_running_app().root.get_screen('dashboard').refresh_data()
    
    def save_gasto(self):
        fecha = self.ids.gasto_fecha.text.strip()
        concepto = self.ids.gasto_concepto.text.strip()
        monto_s = self.ids.gasto_monto.text.strip()
        desc = self.ids.gasto_desc.text.strip()
        
        if not fecha:
            mostrar_error("Por favor ingresa la fecha del gasto.")
            return
        if not concepto:
            mostrar_error("Por favor ingresa el concepto del gasto.")
            return
        if not monto_s:
            mostrar_error("Por favor ingresa el monto del gasto.")
            return
        
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 25.50")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gastos_adicionales (fecha, concepto, monto, descripcion)
            VALUES (?, ?, ?, ?)
        """, (fecha, concepto, monto, desc))
        conn.commit()
        conn.close()
        
        self.ids.gasto_concepto.text = ""
        self.ids.gasto_monto.text = ""
        self.ids.gasto_desc.text = ""
        
        self.refresh_all()
        App.get_running_app().root.get_screen('dashboard').refresh_data()
    
    def delete_pago(self, pid):
        conn = get_db_connection()
        conn.execute("DELETE FROM alquiler_pagos WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        self.refresh_all()
        App.get_running_app().root.get_screen('dashboard').refresh_data()
    
    def delete_gasto(self, gid):
        conn = get_db_connection()
        conn.execute("DELETE FROM gastos_adicionales WHERE id = ?", (gid,))
        conn.commit()
        conn.close()
        self.refresh_all()
        App.get_running_app().root.get_screen('dashboard').refresh_data()


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
            self.txt_fecha = TextInput(text=datetime.now().strftime("%d/%m/%Y"), multiline=False, size_hint_y=None, height='28dp')
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
            self.txt_fecha = TextInput(text=datetime.now().strftime("%d/%m/%Y"), multiline=False, size_hint_y=None, height='28dp')
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
            self.txt_desc = TextInput(hint_text="Nota...", multiline=False, size_hint_y=None, height='28dp')
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
            item = TransactionItem(tid, fecha_v, tp, cat, display_monto, display_desc, self.delete_item)
            self.ids.list_transacciones.add_widget(item)
        conn.close()

    def save_viaje(self, *args):
        fecha_s = self.txt_fecha.text.strip()
        if not fecha_s:
            mostrar_error("Por favor ingresa la fecha del viaje.")
            return
        try:
            dt = datetime.strptime(fecha_s, "%d/%m/%Y")
            fecha_db = dt.strftime("%Y-%m-%d")
        except:
            mostrar_error("Formato de fecha incorrecto.\nUsa el formato: DD/MM/AAAA\nEjemplo: 01/06/2026")
            return

        # Leer todos los campos con valor 0 por defecto
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

        # Verificar que al menos un valor fue ingresado
        if bruto == 0 and gasolina == 0 and uso_carro == 0:
            mostrar_error("Ingresa al menos uno de estos campos:\n- Bruto del viaje\n- Gasolina\n- Aporte Carro")
            return

        conn = get_db_connection()
        cur = conn.cursor()

        # Solo guarda el viaje InDrive si hay bruto
        if bruto > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, comision, viajes, km, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Ingreso', ?, ?, ?, ?, 'Viaje InDrive', 'Sesión')", (fecha_db, bruto, comision, viajes, km))
        # Solo guarda gasolina si hay valor
        if gasolina > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Gasto', ?, 'Combustible', 'Gasolina')", (fecha_db, gasolina))
        # Solo guarda aporte carro si hay valor
        if uso_carro > 0:
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', 'Gasto', ?, 'Uso del Carro', 'Aporte carro')", (fecha_db, uso_carro))
            cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Uso del Carro', 'Ingreso', ?, 'Aporte', 'Ingreso diario')", (fecha_db, uso_carro))

        conn.commit()
        conn.close()
        self.refresh_all()
        for attr in ['txt_bruto', 'txt_comision', 'txt_gasolina', 'txt_uso_carro', 'txt_viajes', 'txt_km']:
            getattr(self, attr).text = ""

    def save_otro(self, *args):
        fecha_s = self.txt_fecha.text.strip()
        monto_s = self.txt_monto.text.strip()
        if not fecha_s:
            mostrar_error("Por favor ingresa la fecha.")
            return
        if not monto_s:
            mostrar_error("Por favor ingresa el monto.")
            return
        try:
            dt = datetime.strptime(fecha_s, "%d/%m/%Y")
            fecha_db = dt.strftime("%Y-%m-%d")
        except:
            mostrar_error("Formato de fecha incorrecto.\nUsa el formato: DD/MM/AAAA\nEjemplo: 01/06/2026")
            return
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 10.00")
            return
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Ahorro InDrive', ?, ?, ?, ?)", (fecha_db, self.var_o_tipo, monto, self.var_o_cat, self.txt_desc.text.strip() or ""))
        conn.commit()
        conn.close()
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
        conn.commit()
        conn.close()
        self.refresh_all()


class CarroScreen(Screen):
    balance_carro = StringProperty("$0.00")
    color_carro = ObjectProperty([0.07, 0.65, 0.60, 1])
    var_c_tipo = StringProperty("Gasto")
    var_c_cat = StringProperty("Combustible")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(var_c_tipo=self.update_c_category_on_type)

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
            item = TransactionItem(tid, fecha_v, tp, cat, monto, desc, self.delete_item)
            self.ids.list_carro.add_widget(item)
        conn.close()

    def save_carro(self):
        fecha_s = self.ids.c_fecha.text.strip()
        monto_s = self.ids.c_monto.text.strip()
        if not fecha_s:
            mostrar_error("Por favor ingresa la fecha.")
            return
        if not monto_s:
            mostrar_error("Por favor ingresa el monto.")
            return
        try:
            dt = datetime.strptime(fecha_s, "%d/%m/%Y")
            fecha_db = dt.strftime("%Y-%m-%d")
        except:
            mostrar_error("Formato de fecha incorrecto.\nUsa el formato: DD/MM/AAAA\nEjemplo: 01/06/2025")
            return
        try:
            monto = float(monto_s)
        except:
            mostrar_error("El monto debe ser un número válido.\nEjemplo: 15.00")
            return
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion) VALUES (?, 'Uso del Carro', ?, ?, ?, ?)", (fecha_db, self.var_c_tipo, monto, self.var_c_cat, self.ids.c_desc.text.strip() or ""))
        conn.commit()
        conn.close()
        self.refresh_all()
        self.ids.c_monto.text = ""
        self.ids.c_desc.text = ""

    def delete_item(self, tid):
        conn = get_db_connection()
        conn.execute("DELETE FROM transacciones WHERE id = ?", (tid,))
        conn.commit()
        conn.close()
        self.refresh_all()


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


class CalendarScreen(Screen):
    def on_enter(self, *args):
        self.ids.calendar_grid.clear_widgets()
        today = datetime.today()
        first_day = today.replace(day=1)
        next_month = first_day + timedelta(days=32)
        last_day = (next_month.replace(day=1) - timedelta(days=1)).day
        
        first_weekday = first_day.weekday()
        for _ in range(first_weekday):
            self.ids.calendar_grid.add_widget(Label(text=""))
            
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT fecha,
                   SUM(CASE 
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' AND categoria = 'Viaje InDrive' THEN monto - comision
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Ingreso' AND categoria != 'Viaje InDrive' THEN monto
                        WHEN cuenta = 'Ahorro InDrive' AND tipo = 'Gasto' THEN -monto 
                        ELSE 0 
                   END) as profit
            FROM transacciones 
            GROUP BY fecha
        """)
        profit_map = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        
        for day in range(1, last_day + 1):
            date_obj = first_day.replace(day=day)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            if date_str not in profit_map:
                btn = Button(
                    text=f"{day}",
                    size_hint_y=None,
                    height='60dp',
                    background_normal='',
                    background_color=[0.98, 0.98, 0.99, 0.9],
                    color=[0.08, 0.08, 0.09, 0.9],
                    font_size='14sp'
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
    def __init__(self, tid, fecha, tipo, cat, monto, desc, delete_callback, **kwargs):
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


class InDriveApp(App):
    def build(self):
        global writable_db_path
        from kivy.utils import platform
        
        # Cargar base de datos existente o inicializar si no existe
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
                    shutil.copy(local_db, writable_db_path)
                except Exception as e:
                    pass
        else:
            writable_db_path = local_db
        
        # Inicializar base de datos VACÍA
        init_database()
        
        Builder.load_string(KV)
        sm = ScreenManager()
        sm.add_widget(DashboardScreen(name='dashboard'))
        sm.add_widget(AhorroScreen(name='ahorro'))
        sm.add_widget(CarroScreen(name='carro'))
        sm.add_widget(CasaScreen(name='casa'))
        sm.add_widget(StatsScreen(name='stats'))
        sm.add_widget(CalendarScreen(name='calendar'))
        return sm


if __name__ == '__main__':
    InDriveApp().run()