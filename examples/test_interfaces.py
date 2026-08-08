#!/usr/bin/env python3
"""
Ejemplo de uso del motor OpnGL con interfaces declarativas en XML.

Carga todas las interfaces en examples/interfaces/ como pantallas
navegables, con transiciones fade entre ellas.

Ejecuta:
    python examples/test_interfaces.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opngl import App, load_interfaces_from_dir


def main():
    examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    interfaces_dir = os.path.join(examples_dir, "interfaces")

    app, interfaces = load_interfaces_from_dir(interfaces_dir)
    print("[Test] Interfaces cargadas: {}".format(", ".join(interfaces)))

    app.on_click("btn_render", lambda b: print("[Test] Renderizar pulsado"))
    app.on_click("btn_close", lambda b: app.quit())
    app.on_click("btn_opciones",
                 lambda b: app.set_interface("main", transition=True, duration=0.4))
    app.on_click("btn_volver",
                 lambda b: app.set_interface("principal", transition=True, duration=0.4))

    app.on_frame(lambda app: None)

    app.run()


if __name__ == "__main__":
    main()