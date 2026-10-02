# -*- coding: utf-8 -*-
"""Pruebas del autocompletado de todos los campos.

    python test_sugerencias.py

Arranca la app de verdad porque las fuentes de sugerencia son metodos de
las pantallas (casa, ahorro, carro).
"""
import datetime
import sys
import traceback

import main
from kivy.app import App
from kivy.clock import Clock

FALLOS = []


def apuntar(cosa):
    FALLOS.append(cosa)


class Prueba(main.InDriveApp):
    def on_start(self):
        super().on_start()
        Clock.schedule_once(self._probar, 2.0)

    def _probar(self, dt):
        try:
            self._ejecutar()
        except Exception:
            apuntar("excepcion general:\n" + traceback.format_exc())
        print("FALLOS: %d" % len(FALLOS))
        for f in FALLOS:
            print("  - " + str(f))
        App.get_running_app().stop()

    # ------------------------------------------------------------------
    def _ejecutar(self):
        self._aprendizaje()
        self._fuentes()

    def _aprendizaje(self):
        """Filas de prueba para ver si la app aprende lo que escribimos."""
        conn = main.get_db_connection()
        try:
            conn.execute(
                "INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion)"
                " VALUES ('2022-02-02', 'Ahorro InDrive', 'Gasto', 1.0, 'Otros', 'zzborrar')")
            conn.execute(
                "INSERT INTO transacciones (fecha, cuenta, tipo, monto, categoria, descripcion)"
                " VALUES ('2022-03-03', 'Ahorro InDrive', 'Gasto', 2.0, 'Otros', 'zzborrar')")
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM transacciones WHERE descripcion='zzborrar'").fetchall()]
            conn.commit()
        finally:
            conn.close()

        try:
            s = main._sug_texto('transacciones', 'descripcion', 'zzborr')
            if 'zzborrar' not in s:
                apuntar("_sug_texto no aprendio 'zzborrar' -> %s" % s)
            s = main._sug_texto('transacciones', 'descripcion', 'ZZBORRAR')
            if 'zzborrar' not in s:
                apuntar("_sug_texto no encuentra sin distinguir mayusculas -> %s" % s)
            s = main._sug_texto('transacciones', 'descripcion', 'qwertz')
            if s:
                apuntar("_sug_texto devolvio basura -> %s" % s)

            if main._sug_texto('transacciones; DROP TABLE x', 'fecha', ''):
                apuntar("_sug_texto no bloqueo una tabla inyectada")
            if main._sug_texto('transacciones', 'fecha " OR 1=1', ''):
                apuntar("_sug_texto no bloqueo una columna inyectada")

            f = main._sug_fechas('02/02/2022')
            if '02/02/2022' not in f:
                apuntar("_sug_fechas no encontro 02/02/2022 -> %s" % f)
            if '03/03/2022' in f:
                apuntar("_sug_fechas ignora el texto escrito -> %s" % f)

            m = main._sug_meses('mar')
            if not any(x.lower().startswith('mar') for x in m):
                apuntar("_sug_meses('mar') -> %s" % m)

            de = main._sug_de('transacciones', 'descripcion')
            if 'zzborrar' not in de('zzborr'):
                apuntar("_sug_de no listo la fila nueva -> %s" % de('zzborr'))
        finally:
            conn = main.get_db_connection()
            for i in ids:
                conn.execute("DELETE FROM transacciones WHERE id=?", (i,))
            conn.commit()
            conn.close()

    # ------------------------------------------------------------------
    def _fuentes(self):
        """Cada campo de la app debe tener su fuente de sugerencias."""
        sm = self.root
        casa = sm.get_screen('casa')

        revisados = [
            ('carro.c_fecha', sm.get_screen('carro').ids.c_fecha),
            ('carro.c_desc', sm.get_screen('carro').ids.c_desc),
        ]
        ubicacion = {
            'txt_pf': ('cliente', 'pagos'), 'txt_pd': ('cliente', 'pagos'),
            'txt_ph': ('cliente', 'pagos'),
            'txt_a_fec': ('cliente', 'aseo'), 'txt_a_mes': ('cliente', 'aseo'),
            'txt_gf': ('gastos', None), 'txt_gc': ('gastos', None),
            'txt_gt': ('gastos', None),
            'txt_af': ('ahorro', None), 'txt_acon': ('ahorro', None),
            'txt_df': ('cliente', 'deuda'), 'txt_ddesc': ('cliente', 'deuda'),
        }
        for campo, (vista, pestana) in ubicacion.items():
            casa.vista_actual = vista
            if pestana:
                casa.tab_actual = pestana
            casa._render_tab()
            revisados.append(('casa.' + campo, getattr(casa, campo, None)))

        ah = sm.get_screen('ahorro')
        for form in ('viaje', 'otro'):
            ah.current_form = form
            ah.load_form_layout()
            revisados.append(('ahorro[%s].txt_fecha' % form, ah.txt_fecha))
            if form == 'otro':
                revisados.append(('ahorro[%s].txt_desc' % form,
                                  getattr(ah, 'txt_desc', None)))

        hoy = datetime.date.today().strftime("%Y-%m-%d")
        for nombre, widget in revisados:
            if widget is None:
                apuntar("%s no existe" % nombre)
                continue
            if getattr(widget, 'fuente', None) is None:
                apuntar("%s sin fuente de sugerencias" % nombre)
                continue
            try:
                opciones = widget.fuente('')
            except Exception as e:
                apuntar("%s.fuente lanzo %r" % (nombre, e))
                continue
            if not isinstance(opciones, list):
                apuntar("%s.fuente devolvio %r" % (nombre, type(opciones)))
            if not hasattr(widget, 'fecha_iso'):
                continue
            if widget.text and not widget.fecha_valida:
                apuntar("%s no arranca con fecha valida: %r" % (nombre, widget.text))
            elif widget.text and widget.fecha_iso != hoy:
                apuntar("%s no arranca en hoy: %r" % (nombre, widget.fecha_iso))


if __name__ == '__main__':
    Prueba().run()
    sys.exit(1 if FALLOS else 0)
