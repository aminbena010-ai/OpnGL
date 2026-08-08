# Demo del motor OpnGL: python -m opngl
# Carga TODOS los .xml de examples/interfaces/ como interfaces.
# La ventana (tamaño, título y color de fondo) se lee de la cabecera
# <AppWindow> del XML: en Python solo se aplica la lógica.
import os

from opngl import App, load_interfaces_from_dir


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    interfaces_dir = os.path.join(root_dir, "examples", "interfaces")

    if os.path.isdir(interfaces_dir) and any(
            f.lower().endswith(".xml") for f in os.listdir(interfaces_dir)):
        app, interfaces = load_interfaces_from_dir(interfaces_dir)
        print("[OpnGL] Interfaces cargadas: {}".format(", ".join(interfaces)))
    else:
        app = App(title="OpnGL Engine sobre Vulkan")
        app.label(text="Motor OpnGL Activo (Vulkan puro)", font_size=22)
        app.button(text="Cerrar", id="btn_close")

    for widget_id, handler in (
        ("btn_render", lambda b: print("[Evento] Botón de render pulsado")),
        ("btn_close", lambda b: app.quit()),
        ("btn_opciones", lambda b: app.set_interface("opciones", transition=True)),
        ("btn_volver", lambda b: app.set_interface("principal", transition=True)),
    ):
        try:
            app.on_click(widget_id, handler)
        except KeyError:
            pass

    app.run()


if __name__ == "__main__":
    main()
