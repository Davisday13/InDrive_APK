# -*- coding: utf-8 -*-
"""Pruebas de la navegacion con el boton Atras (historial de pantallas).

    python test_navegacion.py

Regresión del 13/10: el Atras caminaba una lista fija de nombres
(['calendar', 'stats', 'carro', 'ahorro', 'casa']) y desde Ahorros el
gesto atrás del teléfono saltaba por pantallas que el usuario nunca
abrió: ahorro -> carro -> stats -> calendar -> dashboard.

Ahora el Atras usa una pila con la pantalla real de origen.
"""
import main
from kivy.uix.screenmanager import ScreenManager, Screen

FALLOS = []


def chk(cond, msg):
    if not cond:
        FALLOS.append(msg)


apuntar = chk


class _PopupTrucho(object):
    """Cuenta aperturas sin crear ventanas reales."""

    abiertos = 0

    def __init__(self, **k):
        pass

    def open(self, *a, **k):
        _PopupTrucho.abiertos += 1

    def dismiss(self, *a, **k):
        pass


def _app():
    """App con ScreenManager de mentira y el historial sembrado."""
    app = main.InDriveApp()
    sm = ScreenManager()
    for n in ('login', 'dashboard', 'ahorro', 'carro', 'casa',
              'stats', 'calendar'):
        sm.add_widget(Screen(name=n))
    # 'casa' con la clase real: su _volver_atras decide entre sus vistas
    # internas y el dashboard.
    sm.remove_widget(sm.get_screen('casa'))
    sm.add_widget(main.CasaScreen(name='casa'))
    app.root = sm
    sm.current = 'dashboard'
    app._historial_pantallas = [sm.current]
    sm.bind(current=app._registrar_pantalla)
    return app, sm


def ir(app, nombre):
    """Simula que el usuario tocó un botón del menú."""
    app.root.current = nombre


def _sin_render(casa):
    # Sin KV cargado los ids no existen: se dejan los renders mudos.
    casa._render_inicio = lambda *a: None
    casa._render_lista_clientes = lambda *a: None
    casa._render_cliente = lambda *a: None


def revisar_atras_vuelve_al_origen():
    """Cualquier pantalla del menú: un Atras lleva al dashboard."""
    for nombre in ('ahorro', 'carro', 'stats', 'calendar'):
        app, sm = _app()
        ir(app, nombre)
        app._handle_back()
        apuntar(sm.current == 'dashboard',
                "%s: el Atras fue a '%s' (esperaba dashboard)"
                % (nombre, sm.current))


def revisar_atras_no_salta_a_carro():
    """Regresión directa del reporte: desde ahorros, Atras = dashboard.

    El código viejo mandaba a 'carro' y de ahí a 'stats', 'calendar'
    y recién al dashboard.
    """
    app, sm = _app()
    ir(app, 'ahorro')
    app._handle_back()
    apuntar(sm.current == 'dashboard',
            "desde ahorros el Atras fue a '%s' (codigo viejo: carro)"
            % sm.current)


def revisar_historial_real():
    """Si el usuario vino de carro vía dashboard, Atras desde ahorros
    no puede caer en carro: el origen real era el dashboard."""
    app, sm = _app()
    ir(app, 'carro')
    ir(app, 'dashboard')
    ir(app, 'ahorro')
    app._handle_back()
    apuntar(sm.current == 'dashboard',
            "atras desde ahorros (viniendo del dashboard) fue a '%s'"
            % sm.current)


def revisar_doble_atras():
    """Dos Atras seguidos: el segundo no camina la lista vieja."""
    app, sm = _app()
    ir(app, 'carro')
    app._handle_back()
    apuntar(sm.current == 'dashboard',
            "primer atras desde carro fue a '%s'" % sm.current)
    viejo = _PopupTrucho.abiertos
    import kivy.uix.popup as _popup
    original = _popup.Popup
    _popup.Popup = _PopupTrucho
    try:
        app._handle_back()
    finally:
        _popup.Popup = original
    apuntar(sm.current == 'dashboard',
            "segundo atras cambio la pantalla a '%s'" % sm.current)
    apuntar(_PopupTrucho.abiertos == viejo + 1,
            "el atras en dashboard no abrio el confirmar salida")


def revisar_casa_vuelve_al_dashboard():
    """Casa con vista 'inicio': su Atras propio lleva al dashboard y
    la pila queda limpia (no deja 'casa' colgando)."""
    app, sm = _app()
    casa = sm.get_screen('casa')
    _sin_render(casa)
    ir(app, 'casa')
    app._handle_back()
    apuntar(sm.current == 'dashboard',
            "casa inicio: el Atras fue a '%s'" % sm.current)
    apuntar(app._historial_pantallas[-1] == 'dashboard',
            "la pila quedo con '%s' arriba" % app._historial_pantallas[-1])


def revisar_casa_vistas_internas():
    """Dentro de Casa: el primer Atras retrocede de vista, el segundo
    sale al dashboard."""
    app, sm = _app()
    casa = sm.get_screen('casa')
    _sin_render(casa)
    ir(app, 'casa')
    casa.vista_actual = 'clientes'
    app._handle_back()
    apuntar(sm.current == 'casa',
            "atras en vista clientes cambio de pantalla a '%s'" % sm.current)
    apuntar(casa.vista_actual == 'inicio',
            "atras en vista clientes dejo vista '%s'" % casa.vista_actual)
    app._handle_back()
    apuntar(sm.current == 'dashboard',
            "segundo atras desde casa fue a '%s'" % sm.current)


def revisar_atras_repetido_no_acumula():
    """Ida y vuelta varias veces: la pila no crece sin control."""
    app, sm = _app()
    for _ in range(5):
        ir(app, 'ahorro')
        app._handle_back()
    apuntar(sm.current == 'dashboard',
            "tras 5 ida y vuelta la pantalla quedo en '%s'" % sm.current)
    apuntar(len(app._historial_pantallas) <= 3,
            "la pila crecio hasta %d entradas" % len(app._historial_pantallas))


revisar_atras_vuelve_al_origen()
revisar_atras_no_salta_a_carro()
revisar_historial_real()
revisar_doble_atras()
revisar_casa_vuelve_al_dashboard()
revisar_casa_vistas_internas()
revisar_atras_repetido_no_acumula()

print("FALLOS: %d" % len(FALLOS))
for f in FALLOS:
    print("  - " + f)
