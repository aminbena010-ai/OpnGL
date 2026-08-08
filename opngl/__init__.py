# =========================================================================
# OpnGL - Motor gráfico sobre VULKAN puro.
#
#   * Ventana:    GLFW con CLIENT_API=NO_API (sin contexto OpenGL jamás)
#   * Render:     Vulkan (swapchain, render pass, pipelines, command buffers)
#   * UI:         árbol de widgets definido en XML o en código
#   * Fuentes:    recursos base en resources/fonts/, familia en el atributo
#                 font="..." de Label/Button (por defecto "dejavu")
#   * Interfaces: varios XML cargados como interfaces, con transiciones fade
#   * Shaders:    GLSL 450 en shaders/, compilados a SPIR-V con glslangValidator
#
# MODO SUPREMO (uso recomendado):
#   from opngl import App
#
#   app = App("ui.xml", title="Mi App")          # UI declarativa desde XML
#   app.on_click("boton1", lambda b: print("Click!"))
#   app.run()
#
#   #  o varias interfaces con transición:
#   app.load_interface("menu", "menu.xml")
#   app.load_interface("juego", "juego.xml")
#   app.set_interface("juego", transition=True, duration=0.4)
#
#   #  o 100% en código:
#   app = App(title="Mi App")
#   app.button(text="Hola", id="btn").on_click(...)
#   app.run()
# =========================================================================
import time

import os

import glfw
import vulkan as vk
from vulkan import ffi

from opngl.core.window import OpnGLWindow
from opngl.core.device import VulkanDevice
from opngl.core.swapchain import VulkanSwapchain
from opngl.core.renderer import Renderer
from opngl.core.vkutil import hex_color_to_rgba
from opngl.renderer.ui import UIRenderer
from opngl.audio import AudioManager
from opngl.widgets.base import UIWidget
from opngl.widgets.containers import VBox, HBox, Panel, AppWindow
from opngl.widgets.button import Button
from opngl.widgets.image import Image
from opngl.widgets.label import Label
from opngl.widgets.textinput import TextInput
from opngl.xml_parser.parser import XMLUIParser
from opngl.xml_parser.layout import apply_layout

__version__ = "0.1.0"

__all__ = [
    "App",
    "OpnGL",
    "OpnGLWindow",
    "VulkanDevice",
    "VulkanSwapchain",
    "Renderer",
    "UIRenderer",
    "UIWidget",
    "VBox",
    "HBox",
    "Panel",
    "AppWindow",
    "Button",
    "Label",
    "Image",
    "TextInput",
    "AudioManager",
    "XMLUIParser",
]


class App:
    """Aplicación OpnGL: ventana + dispositivo Vulkan + renderer + UI."""

    def __init__(self, xml=None, width=800, height=600, title="OpnGL App",
                 background="#111827"):
        self.width = width
        self.height = height
        self.title = title
        self.window = OpnGLWindow(width=width, height=height, title=title)
        self.window.initialize()
        print("--- Inicializando Vulkan (GLFW sin OpenGL, CLIENT_API=NO_API) ---")

        self.device = VulkanDevice(self.window)
        self.swapchain = VulkanSwapchain(self.device, self.window)
        self.renderer = Renderer(self.device, self.swapchain, self.window)
        self.ui = UIRenderer()
        self.audio = AudioManager()
        self._on_frame = None
        self._pending_draws = []
        self._cb = None
        self._running = False

        self.root = AppWindow(width=width, height=height, padding=20, spacing=12,
                              background=background)
        self.ui.set_root(self.root)
        self.interfaces = {}
        self.window.on_mouse_move = self.ui.on_mouse_move
        self.window.on_mouse_button = self.ui.on_mouse_button
        self.window.on_key = self.ui.on_key
        self.window.on_char = self.ui.on_char

        if xml is not None:
            self.load_xml(xml)
        self._apply_layout()
        print("[OpnGL] App lista. Abre la ventana y pulsa ESC para salir.")

    # ------------------------------------------------------------------ #
    # Carga de UI
    # ------------------------------------------------------------------ #
    def load_xml(self, source):
        root = self._parse_root(source)
        self.interfaces["main"] = root
        self.set_root(root)
        return root

    def load_interface(self, name, source):
        """Carga un XML como interfaz con nombre, sin mostrarla."""
        root = self._parse_root(source)
        self.interfaces[name] = root
        return root

    def set_interface(self, name, transition=False, duration=0.3):
        """Activa la interfaz <name>. Si transition=True, hace un fade."""
        if name not in self.interfaces:
            raise KeyError("[OpnGL] Interfaz '{}' no cargada".format(name))
        root = self.interfaces[name]
        if transition:
            self.ui.transition_to(root, duration)
        else:
            self.ui.set_root(root)
        self.root = root
        return root

    def set_root(self, root):
        self.root = root
        self.ui.set_root(root)
        self._apply_layout()
        return root

    def _parse_root(self, source):
        parser = XMLUIParser(source)
        root = parser.parse()
        root.width = self.width
        root.height = self.height
        self._annotate_metrics(root)
        apply_layout(root, self.width, self.height)
        self._wire_button_sounds(root)
        return root

    def _annotate_metrics(self, widget):
        """Guarda métricas de fuente (avance/alto/atlas) y dimensiones de imagen
        en cada widget para medir y dibujar sin recargar recursos."""
        if hasattr(widget, "font_size"):
            family = getattr(widget, "font", None)
            adv, line = self.renderer.fonts.metrics(family)
            widget._adv_factor = adv
            widget._line_factor = line
            widget._atlas = self.renderer.fonts.get(family)
        if getattr(widget, "src", None) is not None:
            tex = self.renderer.images.get(widget.src)
            if tex is not None:
                widget._image_w = tex.width
                widget._image_h = tex.height
        for child in getattr(widget, "children", ()):
            self._annotate_metrics(child)

    def _wire_button_sounds(self, widget):
        """Conecta el atributo sound="" de los botones XML al AudioManager.
        El sonido se carga automáticamente (WAV/OGG/MP3/FLAC) al parsear la
        interfaz: busca junto al script, en el CWD o en resources/sounds/.
        Si el archivo no existe, avisa por consola y el botón queda sin sonido.
        El nombre se guarda en _sound_name; App.on_click() lo reproduce cuando
        el usuario registra su propio manejador."""
        if getattr(widget, "sound", None):
            name = widget.sound
            if name not in self.audio.sounds:
                try:
                    self.load_sound(name)
                except FileNotFoundError as exc:
                    print(exc)
                    print("[OpnGL] Advertencia: el botón '{}' no tendrá sonido.".format(
                        widget.id or widget.text))
            if name in self.audio.sounds:
                widget._sound_name = name
        for child in getattr(widget, "children", ()):
            self._wire_button_sounds(child)

    def _apply_layout(self):
        apply_layout(self.root, self.width, self.height)

    def layout(self):
        """Reaplica el layout tras cambios programáticos."""
        self._apply_layout()
        return self

    # ------------------------------------------------------------------ #
    # Construcción de widgets en código
    # ------------------------------------------------------------------ #
    def add(self, widget):
        self.root.add(widget)
        return widget

    def vbox(self, **kw):
        return self.add(VBox(**kw))

    def hbox(self, **kw):
        return self.add(HBox(**kw))

    def panel(self, **kw):
        return self.add(Panel(**kw))

    def button(self, **kw):
        return self.add(Button(**kw))

    def label(self, **kw):
        return self.add(Label(**kw))

    def text_input(self, **kw):
        return self.add(TextInput(**kw))

    def widget(self, widget_id):
        """Busca un widget por id en la interfaz activa y en el resto de
        interfaces cargadas (load_interface), para poder registrar eventos
        de cualquier pantalla aunque no esté visible."""
        found = self.root.find(widget_id)
        if found is None:
            for root in self.interfaces.values():
                if root is self.root:
                    continue
                found = root.find(widget_id)
                if found is not None:
                    break
        if found is None:
            raise KeyError("[OpnGL] No existe el widget '{}'".format(widget_id))
        return found

    def on_click(self, widget_id, handler):
        """Registra el manejador del clic. Si el botón XML tiene sound="",
        reproduce el sonido antes de llamar al manejador."""
        widget = self.widget(widget_id)
        name = getattr(widget, "_sound_name", None)
        if name:
            def _handler(b):
                try:
                    self.play_sound(name)
                except KeyError:
                    pass
                return handler(b)
        else:
            _handler = handler
        widget.on_click(_handler)
        return self

    # ------------------------------------------------------------------ #
    # Imágenes (recursos)
    # ------------------------------------------------------------------ #
    def load_image(self, path, name=None):
        """Carga una imagen (PNG/JPG/…) y la sube a la GPU. Devuelve la textura."""
        return self.renderer.images.load(path, name=name)

    def image(self, src=None, **kw):
        return self.add(Image(src=src, **kw))

    # ------------------------------------------------------------------ #
    # Sonido
    # ------------------------------------------------------------------ #
    def load_sound(self, path, name=None):
        """Decodifica un sonido (WAV/OGG/MP3/FLAC) y lo guarda como <name>
        (por defecto, el nombre del archivo). Devuelve True si se cargó."""
        if name is None:
            name = os.path.basename(path)
        return self.audio.load(name, path)

    def play_sound(self, name, volume=1.0, loop=False):
        """Reproduce el sonido <name>. Devuelve el objeto Sound para detenerlo."""
        return self.audio.play(name, volume=volume, loop=loop)

    def stop_sound(self, sound):
        self.audio.stop(sound)

    def stop_all_sounds(self):
        self.audio.stop_all()

    def set_sound_volume(self, volume):
        """Volumen global de sonido (0.0..1.0)."""
        self.audio.set_volume(volume)

    # ------------------------------------------------------------------ #
    # Bucle principal
    # ------------------------------------------------------------------ #
    def on_frame(self, handler):
        """Registra un callback por frame: handler(app)."""
        self._on_frame = handler
        return self

    def draw(self, vertices, pipeline="shape", rect_size=None, radius=0.0,
             border_width=0.0, border_color=None, gradient=None):
        """Dibuja geometría personalizada dentro del frame actual.
        Solo hay dos pipelines: 'shape' (solid/rounded/borde/gradiente) y 'text'."""
        if self._cb is not None:
            self.renderer.draw(self._cb, vertices, pipeline, rect_size, radius,
                               border_width=border_width, border_color=border_color,
                               gradient=gradient)
        else:
            self._pending_draws.append((vertices, pipeline, rect_size, radius,
                                        border_width, border_color, gradient))
        return self

    def clear_color(self, r, g, b, a=1.0):
        self.renderer.clear_color = (r, g, b, a)

    def readback(self, x=0, y=0, w=None, h=None):
        """Devuelve bytes RGBA de la imagen actual (verificación/tests)."""
        return self.renderer.readback(x, y, w, h)

    def run(self):
        self._running = True
        last = time.time()
        try:
            while self._running and not self.window.should_close():
                self.window.poll_events()
                now = time.time()
                dt = now - last
                last = now

                if self.window.consume_resize_flag():
                    for name, root in self.interfaces.items():
                        apply_layout(root, *self.window.framebuffer_size())
                    self.renderer.recreate_requested = True

                if self._on_frame is not None:
                    self._on_frame(self)

                self.ui.update(dt)

                cb = self.renderer.begin_frame()
                if cb is None:
                    self.renderer.handle_recreate()
                    continue

                self._cb = cb
                for verts, pipeline, rect, radius, bw, bc, grad in self._pending_draws:
                    self.renderer.draw(cb, verts, pipeline, rect, radius,
                                       border_width=bw, border_color=bc, gradient=grad)
                self._pending_draws = []

                self.ui.render(self.renderer, cb)
                self.renderer.end_frame()
                self._cb = None

                self.renderer.handle_recreate()
        except KeyboardInterrupt:
            print("\n[OpnGL] Interrupción (Ctrl+C). Cerrando la aplicación...")
        finally:
            self.close()

    def quit(self):
        """Solicita salir del bucle de forma segura."""
        self._running = False

    # ------------------------------------------------------------------ #
    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._running = False
        self.audio.destroy()
        self.renderer.destroy()
        self.swapchain.destroy()
        self.device.destroy()
        self.window.close()
        print("[OpnGL] Aplicación cerrada.")


# ------------------------------------------------------------------------
# API de bajo nivel (compatibilidad con OpnGL clásico y acceso al motor)
# ------------------------------------------------------------------------
class OpnGL:
    """Acceso directo al motor Vulkan para uso avanzado.

    Uso recomendado: App (modo supremo). OpnGL expone device/swapchain/
    renderer para quienes quieran control total de Vulkan.
    """
    app = None
    device = None
    swapchain = None
    renderer = None
    window = None

    @classmethod
    def init(cls, width=800, height=600, title="OpnGL Engine (Vulkan)"):
        cls.app = App(width=width, height=height, title=title)
        cls.device = cls.app.device
        cls.swapchain = cls.app.swapchain
        cls.renderer = cls.app.renderer
        cls.window = cls.app.window
        return cls.app

    @classmethod
    def run(cls, on_frame=None):
        if on_frame is not None:
            cls.app.on_frame(on_frame)
        cls.app.run()

    @classmethod
    def load_shader(cls, vertex_path, fragment_path):
        from opngl.graphics.shader import ShaderProgram
        return ShaderProgram(cls.device, vertex_path, fragment_path)

    @classmethod
    def create_vertex_buffer(cls, vertices):
        from opngl.graphics.buffer import VertexBuffer
        return VertexBuffer(cls.device, vertices)

    @classmethod
    def clear_color(cls, r, g, b, a=1.0):
        cls.renderer.clear_color = (r, g, b, a)

    @classmethod
    def draw_arrays(cls, vertex_count):
        raise RuntimeError(
            "[OpnGL] draw_arrays requiere un command buffer activo. "
            "Usa app.draw(vertices, ...) dentro de app.on_frame().")
