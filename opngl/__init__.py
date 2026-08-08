# =========================================================================
# OpnGL - Motor gráfico sobre VULKAN puro.
#
#   * Ventana:    GLFW con CLIENT_API=NO_API (sin contexto OpenGL jamás)
#   * Render:     Vulkan (swapchain, render pass, pipelines, command buffers)
#   * UI:         árbol de widgets definido en XML o en código
#   * Ventana XML: el tamaño, el título y el color de fondo se leen de la
#                 cabecera <AppWindow width height title background> del XML.
#                 Python solo aplica la lógica: todo el diseño visual vive
#                 en los archivos .xml (en Python únicamente eventos/lógica).
#   * Interfaces: varios XML cargados como interfaces (load_interfaces /
#                 load_interfaces_from_dir), con transiciones fade.
#   * Fuentes:    recursos base en resources/fonts/, familia en el atributo
#                 font="..." de Label/Button (por defecto "dejavu")
#   * Shaders:    GLSL 450 en shaders/, compilados a SPIR-V con glslangValidator
#
# MODO SUPREMO (uso recomendado):
#   from opngl import App
#
#   app = App("ui.xml")                          # UI + ventana desde XML
#   app.on_click("boton1", lambda b: print("Click!"))
#   app.run()
#
#   #  o cargar TODOS los .xml de un directorio como interfaces:
#   app, interfaces = load_interfaces_from_dir("ui/")
#   app.set_interface("menu", transition=True, duration=0.4)
#
#   #  o varias interfaces con transición:
#   app = App("menu.xml")                        # la ventana se lee de menu.xml
#   app.load_interface("juego", "juego.xml")
#   app.set_interface("juego", transition=True, duration=0.4)
#
#   #  o 100% en código:
#   app = App(title="Mi App")
#   app.button(text="Hola", id="btn").on_click(...)
#   app.run()
# =========================================================================
import fnmatch
import time
import inspect

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
from opngl.xml_parser.parser import XMLUIParser, window_config
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
    "load_interfaces_from_dir",
]


class App:
    """Aplicación OpnGL: ventana + dispositivo Vulkan + renderer + UI."""

    def __init__(self, xml=None, width=800, height=600, title="OpnGL App",
                 background="#111827"):
        # La ventana (tamaño, título y fondo) se maneja desde la cabecera
        # <AppWindow> del XML cuando se pasa uno: el XML manda, Python solo
        # aplica la lógica.
        if xml is not None:
            cfg = window_config(xml)
            if cfg.get("width") is not None:
                width = int(cfg["width"])
            if cfg.get("height") is not None:
                height = int(cfg["height"])
            if cfg.get("title"):
                title = cfg["title"]
            if cfg.get("background"):
                background = cfg["background"]
        self.width = width
        self.height = height
        self.title = title
        self.background = background
        self.window = OpnGLWindow(width=width, height=height, title=title)
        self.window.initialize()
        print("--- Inicializando Vulkan (GLFW sin OpenGL, CLIENT_API=NO_API) ---")

        self.device = VulkanDevice(self.window)
        self.swapchain = VulkanSwapchain(self.device, self.window)
        self.renderer = Renderer(self.device, self.swapchain, self.window)
        self._apply_clear_color(background)
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
        self._sync_clear_color(root)
        return root

    def load_interface(self, name, source):
        """Carga un XML como interfaz con nombre, sin mostrarla."""
        root = self._parse_root(source)
        self.interfaces[name] = root
        return root

    def load_interfaces(self, *sources, names=None):
        """Carga varios XML (rutas o cadenas) como interfaces con nombre.
        `names` asigna nombres personalizados; si no, se usa el nombre del
        archivo sin extensión. Devuelve un dict {nombre: AppWindow}."""
        loaded = {}
        for i, source in enumerate(sources):
            name = None
            if names is not None and i < len(names):
                name = names[i]
            if name is None:
                base = os.path.basename(source)
                if base.lower().endswith(".xml"):
                    name = os.path.splitext(base)[0]
                else:
                    name = "interfaz_{}".format(i)
            self.interfaces[name] = self._parse_root(source)
            loaded[name] = self.interfaces[name]
        return loaded

    def load_interfaces_from_dir(self, directory, pattern="*.xml"):
        """Carga todos los .xml de `directory` como interfaces con nombre
        (nombre de archivo sin extensión), listos para usarse con
        set_interface(). Devuelve un dict {nombre: AppWindow}."""
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            raise FileNotFoundError(
                "[OpnGL] Directorio de interfaces no encontrado: {}".format(directory))
        files = sorted(os.path.join(directory, f) for f in os.listdir(directory)
                       if fnmatch.fnmatch(f, pattern)
                       and os.path.isfile(os.path.join(directory, f)))
        return self.load_interfaces(*files)

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
        self._sync_clear_color(root)
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

    def _apply_clear_color(self, background):
        """Limpia el framebuffer con el color de fondo definido en el XML."""
        if background:
            r, g, b, a = hex_color_to_rgba(background)
            self.renderer.clear_color = (r, g, b, a)

    def _sync_clear_color(self, root):
        """Sincroniza el clear color con el fondo de la interfaz activa."""
        bg = getattr(root, "background", None)
        if bg:
            self._apply_clear_color(bg)

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


# ------------------------------------------------------------------------
# Carga de interfaces desde XML
# ------------------------------------------------------------------------
def load_xmls(directory, pattern="*.xml"):
    """Función de nivel superior: crea una App y carga TODOS los .xml de
    `directory` como interfaces (nombre = archivo sin extensión), listos para
    usarse con app.set_interface() / app.on_click().

    La ventana (tamaño, título y color de fondo) se lee de la cabecera
    <AppWindow> del primer XML. Python solo aplica la lógica; el diseño
    visual vive 100% en los archivos .xml.

    Devuelve (app, {nombre: AppWindow}).
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        raise FileNotFoundError(
            "[OpnGL] Directorio de interfaces no encontrado: {}".format(directory))
    files = sorted(os.path.join(directory, f) for f in os.listdir(directory)
                   if fnmatch.fnmatch(f, pattern)
                   and os.path.isfile(os.path.join(directory, f)))
    if not files:
        raise FileNotFoundError(
            "[OpnGL] No se encontraron archivos '{}' en '{}'".format(pattern, directory))
    app = App(files[0])
    app.load_interfaces(*files[1:])
    return app, app.interfaces

import os
import inspect
import fnmatch

def xml(filename_or_pattern):
    """
    Busca archivos XML o directorios:
    - xml("ui/render/game/layot.xml") -> Busca esa ruta exacta de archivo.
    - xml("interfaces/*.xml") -> Busca archivos que coincidan con un patrón o comodín.
    - xml("nombre") -> Busca en 'interfaces/' o en la raíz.
    - xml("nombre_carpeta") -> Devuelve la ruta absoluta si es un directorio.
    """
    # 1. Obtener la base del script que hace la llamada
    caller_frame = inspect.currentframe().f_back
    caller_file = caller_frame.f_globals.get('__file__')
    base_dir = os.path.dirname(os.path.abspath(caller_file)) if caller_file else os.path.abspath(".")

    # 2. Si contiene comodines (ej. "*.xml") o barras con comodines
    if "*" in filename_or_pattern or "?" in filename_or_pattern:
        full_path = os.path.join(base_dir, filename_or_pattern)
        return full_path

    # 3. Si el usuario pasa una ruta completa (contiene '/' o '\')
    if "/" in filename_or_pattern or "\\" in filename_or_pattern:
        full_path = os.path.join(base_dir, filename_or_pattern)
        if os.path.isdir(full_path):
            return full_path
        if os.path.isfile(full_path):
            return full_path
        raise FileNotFoundError(f"[OpnGL] Ruta no encontrada: '{full_path}'")

    # 4. Si es un nombre de carpeta directa en la raíz
    dir_path = os.path.join(base_dir, filename_or_pattern)
    if os.path.isdir(dir_path):
        return dir_path

    # 5. Si es un nombre simple, añadir .xml si no lo tiene y buscar en estándar
    filename = filename_or_pattern
    if not filename.endswith(".xml"):
        filename += ".xml"

    # Buscar en 'interfaces/' o en la raíz
    for path in [os.path.join(base_dir, "interfaces", filename), os.path.join(base_dir, filename)]:
        if os.path.isfile(path):
            return path
            
    raise FileNotFoundError(f"[OpnGL] No se encontró el archivo o directorio XML: '{filename_or_pattern}'")
    