# -*- coding: utf-8 -*-
"""Widgets reutilizables: campos de fecha con calendario y autocompletado.

Sin dependencias externas: solo libreria estandar y Kivy, para que
python-for-android no necesite recetas adicionales.
"""

from datetime import datetime, timedelta

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS_CORTOS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]

PRIMARIO = [0.07, 0.65, 0.60, 1]
TEXTO = [0.08, 0.08, 0.09, 1]
SUAVE = [0.3, 0.3, 0.35, 1]
ERROR_BG = [1.0, 0.88, 0.88, 1]
BLANCO = [1, 1, 1, 1]


# ---------------------------------------------------------------- fechas ----

def parse_fecha(valor):
    """Acepta DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD, D/M/AA y DD/MM.

    Devuelve (iso, dd_mm_aaa) o (None, None) si no se puede interpretar.
    """
    if valor is None:
        return None, None
    texto = str(valor).strip().replace('.', '/').replace('-', '/')
    partes = [p for p in texto.split('/') if p != '']
    try:
        if len(partes) == 3:
            a, b, c = partes
            if len(a) == 4:
                anio, mes, dia = int(a), int(b), int(c)
            else:
                dia, mes, anio = int(a), int(b), int(c)
                if anio < 100:
                    anio += 2000
        elif len(partes) == 2:
            dia, mes = int(partes[0]), int(partes[1])
            anio = datetime.now().year
        else:
            return None, None
        momento = datetime(anio, mes, dia)
    except Exception:
        return None, None
    return momento.strftime("%Y-%m-%d"), momento.strftime("%d/%m/%Y")


def fecha_iso(valor):
    """YYYY-MM-DD para la base de datos.

    Devuelve '' cuando el campo esta vacio y None cuando el valor es invalido.
    """
    texto = '' if valor is None else str(valor).strip()
    if not texto:
        return ''
    iso, _ = parse_fecha(texto)
    return iso


def mostrar_fecha(valor):
    """Formato corto para listar en pantalla (acepta cualquier formato guardado)."""
    if valor is None or str(valor).strip() == '':
        return '-'
    _, corta = parse_fecha(valor)
    return corta or str(valor).strip()[:10]


def hoy_iso():
    return datetime.now().strftime("%Y-%m-%d")


def hoy_corto():
    return datetime.now().strftime("%d/%m/%Y")


# ------------------------------------------------------- con sugerencias ----

class CampoSugerencias(TextInput):
    """TextInput con lista desplegable aprendida por la propia app.

    `fuente` es un callable que recibe el texto escrito y devuelve opciones.
    Si es None no se muestra nada.
    """
    fuente = ObjectProperty(None, allownone=True)
    max_sugerencias = NumericProperty(6)

    def __init__(self, **kwargs):
        kwargs.setdefault('multiline', False)
        super(CampoSugerencias, self).__init__(**kwargs)
        self._desplegable = None
        self._trasiego = False
        self.bind(focus=self._al_cambiar_foco, text=self._al_cambiar_texto,
                  parent=self._al_cambiar_padre)

    # ------------------------------------------------------- eventos ----
    def _al_cambiar_foco(self, instancia, valor):
        if valor:
            Clock.schedule_once(lambda dt: self._refrescar(), 0.06)
        else:
            self._cerrar()

    def _al_cambiar_texto(self, *args):
        if self._trasiego or not self.focus:
            return
        Clock.schedule_once(lambda dt: self._refrescar(), 0.12)

    def _al_cambiar_padre(self, instancia, valor):
        if valor is None:
            self._cerrar()

    def _cerrar(self, *args):
        if self._desplegable is not None:
            self._desplegable.dismiss()

    # -------------------------------------------------- desplegable ----
    def _refrescar(self, *args):
        if not self.focus or self.parent is None or self.fuente is None:
            self._cerrar()
            return
        try:
            opciones = self.fuente(self.text or '')
        except Exception:
            opciones = []
        limpias = []
        for opcion in (opciones or []):
            texto = str(opcion).strip() if opcion is not None else ''
            if texto and texto != self.text and texto not in limpias:
                limpias.append(texto)
            if len(limpias) >= int(self.max_sugerencias):
                break
        if not limpias:
            self._cerrar()
            return

        if self._desplegable is None:
            self._desplegable = DropDown(max_height=dp(150))
        lista = self._desplegable
        lista.clear_widgets()
        for opcion in limpias:
            boton = Button(
                text=opcion, size_hint_y=None, height=dp(30), font_size='12sp',
                background_normal='', background_color=BLANCO, color=TEXTO,
                halign='left', valign='middle', shorten=True, shorten_from='right')
            boton.bind(size=lambda inst, valor: setattr(inst, 'text_size',
                                                         (max(valor[0] - dp(14), 0), None)))
            boton.bind(on_release=lambda inst, valor=opcion: self._elegir(valor))
            lista.add_widget(boton)
        try:
            lista.open(self)
        except Exception:
            self._cerrar()

    def _elegir(self, valor):
        self._trasiego = True
        try:
            self.text = valor
            self.cursor = (len(valor), 0)
        finally:
            self._trasiego = False
        self._cerrar()


# ------------------------------------------------------------ DateInput ----

class DateInput(CampoSugerencias):
    """Campo de fecha DD/MM/AAAA con mascara automatica y calendario.

    - Solo admite digitos; las barras se solas ponen.
    - Tolera AAAA-MM-DD y DD-MM-AAAA.
    - El boton de la derecha abre un calendario para elegir cualquier fecha
      (meses pasados incluidos).
    - El fondo se pinta en rojo mientras la fecha no sea valida.
    """
    fecha_iso = StringProperty('')
    fecha_valida = BooleanProperty(True)

    def __init__(self, **kwargs):
        kwargs.setdefault('hint_text', 'DD/MM/AAAA')
        kwargs.setdefault('multiline', False)
        kwargs.setdefault('padding', [dp(8), dp(6), dp(34), dp(6)])
        super(DateInput, self).__init__(**kwargs)
        self._bloqueo = False
        with self.canvas.after:
            Color(rgba=PRIMARIO)
            self._fondo_zona = RoundedRectangle(size=(0, 0), pos=(0, 0), radius=[4])
            Color(rgba=BLANCO)
            self._flecha = Line(points=[0, 0, 0, 0, 0, 0], width=1.4, close=True)
        self.bind(pos=self._dibujar, size=self._dibujar, text=self._al_texto_externo)
        self._dibujar()
        crudo = self._a_crudo(self.text)[:8]
        if crudo:
            self._poner_mascara(crudo, len(crudo))
        else:
            self._validar()

    # ---------------------------------------------------------- mascara ----
    @staticmethod
    def _digitos(valor):
        return ''.join(c for c in (valor or '') if c.isdigit())

    @staticmethod
    def _a_crudo(valor):
        """Texto ajeno a la mascara -> digitos en orden dia-mes-anio.

        Nuestra mascara usa 'DD/MM/AAAA', asi que los digitos ya vienen en
        orden y basta con quitar las barras. La excepcion es 'AAAA-MM-DD',
        que llega desde la base de datos y habria que invertirlo.
        """
        t = (valor or '').strip()
        if len(t) >= 10 and t[4] in '-/.' and t[7] in '-/.' and \
                t[:4].isdigit() and t[5:7].isdigit() and t[8:10].isdigit():
            try:
                return datetime(int(t[0:4]), int(t[5:7]), int(t[8:10])).strftime("%d%m%Y")
            except Exception:
                pass
        return DateInput._digitos(t)[:8]

    @staticmethod
    def _mascara(crudo):
        crudo = crudo[:8]
        if len(crudo) > 4:
            return crudo[:2] + '/' + crudo[2:4] + '/' + crudo[4:]
        if len(crudo) > 2:
            return crudo[:2] + '/' + crudo[2:]
        return crudo

    def _poner_mascara(self, crudo, cursor_digitos):
        crudo = crudo[:8]
        cursor_digitos = max(0, min(cursor_digitos, len(crudo)))
        self._bloqueo = True
        try:
            self.text = self._mascara(crudo)
            posicion = len(self._mascara(crudo[:cursor_digitos]))
            self.cursor = (min(posicion, len(self.text)), 0)
        finally:
            self._bloqueo = False
        self._validar()

    def _validar(self):
        texto = self.text.strip()
        if not texto:
            self.fecha_iso = ''
            self.fecha_valida = True
        else:
            iso, _ = parse_fecha(texto)
            self.fecha_iso = iso or ''
            self.fecha_valida = iso is not None
        fondo = ERROR_BG if (texto and not self.fecha_valida) else BLANCO
        if list(self.background_color) != fondo:
            self.background_color = fondo

    def _al_texto_externo(self, instancia, valor):
        if self._bloqueo:
            return
        crudo = self._a_crudo(valor)[:8]
        self._poner_mascara(crudo, len(crudo))

    def _rango_seleccion(self):
        if not self.selection_text:
            return None
        a, b = self.selection_from, self.selection_to
        if a is None or b is None:
            return None
        return (min(a, b), max(a, b))

    def insert_text(self, substring, from_undo=False):
        if from_undo or self.readonly:
            return super(DateInput, self).insert_text(substring, from_undo=True)
        digitos = self._digitos(substring)
        rango = self._rango_seleccion()
        if rango is not None:
            self.cancel_selection()
            izquierda = self._digitos(self.text[:rango[0]])
            derecha = self._digitos(self.text[rango[1]:])
            cursor = len(izquierda)
        else:
            indice = self.cursor_index()
            izquierda = self._digitos(self.text[:indice])
            derecha = self._digitos(self.text[indice:])
            cursor = len(izquierda)
        if not digitos and rango is None:
            return
        self._poner_mascara((izquierda + digitos + derecha)[:8], cursor + len(digitos))

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self.readonly:
            return
        rango = self._rango_seleccion()
        if rango is not None:
            self.cancel_selection()
            izquierda = self._digitos(self.text[:rango[0]])
            derecha = self._digitos(self.text[rango[1]:])
            self._poner_mascara((izquierda + derecha)[:8], len(izquierda))
            return
        indice = self.cursor_index()
        if indice <= 0:
            return
        if not self.text[indice - 1].isdigit():
            indice -= 1
        if indice <= 0:
            return
        izquierda = self._digitos(self.text[:indice])
        derecha = self._digitos(self.text[indice:])
        self._poner_mascara((izquierda[:-1] + derecha)[:8], max(0, len(izquierda) - 1))

    def delete_selection(self):
        rango = self._rango_seleccion()
        if rango is None:
            super(DateInput, self).delete_selection()
            return
        # Calculado sobre nuestra mascara (siempre dia-mes-anio) para no
        # depender de como Kivy deja el texto a medias durante el borrado.
        izquierda = self._digitos(self.text[:rango[0]])
        derecha = self._digitos(self.text[rango[1]:])
        self._bloqueo = True
        try:
            super(DateInput, self).delete_selection()
        finally:
            self._bloqueo = False
        self._poner_mascara((izquierda + derecha)[:8], len(izquierda))

    # ------------------------------------------------------- calendario ----
    def _ancho_zona(self):
        return min(dp(34), max(dp(24), self.width * 0.2))

    def _dibujar(self, *args):
        ancho = self._ancho_zona()
        alto = max(self.height - dp(6), dp(8))
        origen = (self.right - ancho - dp(3), self.y + dp(3))
        self._fondo_zona.size = (ancho, alto)
        self._fondo_zona.pos = origen
        cx = origen[0] + ancho / 2.0
        cy = origen[1] + alto / 2.0
        t = dp(4)
        self._flecha.points = [cx - t, cy + t, cx + t, cy + t, cx, cy - t]
        # El texto no debe meterse debajo de la flecha, y en campos bajos
        # el relleno vertical se encoge para que la fecha entera se vea.
        px = max(dp(4), min(dp(10), self.width * 0.03))
        py = max(dp(0.5), (self.height - self.font_size) / 2.0 - dp(1))
        nuevo = [px, py, ancho, py]
        if [round(float(x), 1) for x in self.padding] != [round(float(x), 1) for x in nuevo]:
            self.padding = nuevo

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if (self.right - touch.x) <= self._ancho_zona() and touch.x >= self.x:
                self.focus = True
                mostrar_selector_fecha(self)
                return True
        return super(DateInput, self).on_touch_down(touch)


# ------------------------------------------------- calendario emergente ----

def _ultimo_dia(anio, mes):
    if mes == 12:
        return 31
    return (datetime(anio, mes + 1, 1) - timedelta(days=1)).day


def mostrar_selector_fecha(campo, al_elegir=None):
    """Calendario para escoger cualquier dia, meses pasados incluidos."""
    hoy = datetime.now()
    estado = {'anio': hoy.year, 'mes': hoy.month}

    popup = Popup(title='Elegir fecha', size_hint=(0.94, 0.86), auto_dismiss=True)
    raiz = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))

    cabecera = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
    btn_anterior = Button(text='<<', size_hint_x=None, width=dp(56), font_size='14sp')
    etiqueta = Label(font_size='15sp', bold=True, color=TEXTO)
    btn_siguiente = Button(text='>>', size_hint_x=None, width=dp(56), font_size='14sp')
    cabecera.add_widget(btn_anterior)
    cabecera.add_widget(etiqueta)
    cabecera.add_widget(btn_siguiente)

    rejilla = GridLayout(cols=7, spacing=dp(3), size_hint_y=None)
    rejilla.bind(minimum_height=rejilla.setter('height'))

    pie = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
    btn_hoy = Button(text='Hoy', font_size='13sp')
    btn_cerrar = Button(text='Cerrar', font_size='13sp')
    pie.add_widget(btn_hoy)
    pie.add_widget(btn_cerrar)

    raiz.add_widget(cabecera)
    raiz.add_widget(rejilla)
    raiz.add_widget(pie)
    popup.content = raiz

    def pintar(*args):
        etiqueta.text = "%s %d" % (MESES[estado['mes'] - 1].upper(), estado['anio'])
        rejilla.clear_widgets()
        for nombre in DIAS_CORTOS:
            rejilla.add_widget(Label(text=nombre, font_size='11sp', bold=True,
                                     color=SUAVE, size_hint_y=None, height=dp(22)))
        primero = datetime(estado['anio'], estado['mes'], 1)
        for _ in range(primero.weekday()):
            rejilla.add_widget(Label(text='', size_hint_y=None, height=dp(34)))
        for dia in range(1, _ultimo_dia(estado['anio'], estado['mes']) + 1):
            fecha_dia = datetime(estado['anio'], estado['mes'], dia)
            es_hoy = fecha_dia.date() == hoy.date()
            boton = Button(
                text=str(dia), size_hint_y=None, height=dp(34), font_size='13sp',
                bold=es_hoy, background_normal='',
                background_color=PRIMARIO if es_hoy else BLANCO,
                color=BLANCO if es_hoy else TEXTO)
            boton.bind(on_release=lambda inst, valor=fecha_dia:
                       elegir(valor.strftime("%Y-%m-%d")))
            rejilla.add_widget(boton)

    def elegir(dia_iso):
        campo.text = datetime.strptime(dia_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
        if al_elegir is not None:
            al_elegir(dia_iso)
        popup.dismiss()

    def mes_anterior(*args):
        if estado['mes'] == 1:
            estado['mes'], estado['anio'] = 12, estado['anio'] - 1
        else:
            estado['mes'] -= 1
        pintar()

    def mes_siguiente(*args):
        if estado['mes'] == 12:
            estado['mes'], estado['anio'] = 1, estado['anio'] + 1
        else:
            estado['mes'] += 1
        pintar()

    def ir_hoy(*args):
        estado['anio'], estado['mes'] = hoy.year, hoy.month
        pintar()

    btn_anterior.bind(on_release=mes_anterior)
    btn_siguiente.bind(on_release=mes_siguiente)
    btn_hoy.bind(on_release=ir_hoy)
    btn_cerrar.bind(on_release=popup.dismiss)

    inicial = fecha_iso(getattr(campo, 'text', '') or '')
    if inicial:
        try:
            momento = datetime.strptime(inicial, "%Y-%m-%d")
            estado['anio'], estado['mes'] = momento.year, momento.month
        except Exception:
            pass

    pintar()
    popup.open()
    return popup
