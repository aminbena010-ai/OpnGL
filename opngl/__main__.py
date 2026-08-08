# Demo del motor OpnGL: python -m opngl
# Usa examples/interfaz.xml si existe (desarrollo); si no, crea una UI en código.
import os

from opngl import App


def main():
    examples = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "examples", "interfaz.xml")

    if os.path.exists(examples):
        app = App(examples, title="OpnGL Engine sobre Vulkan")
    else:
        app = App(title="OpnGL Engine sobre Vulkan")
        app.label(text="Motor OpnGL Activo (Vulkan puro)", font_size=22)
        app.button(text="Cerrar", id="btn_close")

    app.on_click("btn_render", lambda b: print("[Evento] Botón de render pulsado"))
    app.on_click("btn_close", lambda b: app.quit())
    app.run()


if __name__ == "__main__":
    main()
