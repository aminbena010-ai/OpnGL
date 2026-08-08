# Ventana OpnGL: GLFW sin contexto OpenGL (NO_API) para Vulkan puro.
import sys

import glfw


class OpnGLWindow:
    def __init__(self, width=800, height=600, title="OpnGL Engine (Vulkan)"):
        self.width = width
        self.height = height
        self.title = title
        self.window = None
        self._framebuffer_resized = False
        self._last_fb_width = 0
        self._last_fb_height = 0
        self.on_resize = None
        self.on_key = None
        self.on_char = None
        self.on_mouse_button = None
        self.on_mouse_move = None
        self.on_cursor = None

    @staticmethod
    def _error_callback(error, description):
        print("[GLFW Error {}]: {}".format(error, description))

    # -- callbacks internos GLFW ------------------------------------------
    def _fb_size_callback(self, window, fb_width, fb_height):
        self._framebuffer_resized = True
        self._last_fb_width = fb_width
        self._last_fb_height = fb_height
        if self.on_resize:
            self.on_resize(fb_width, fb_height)

    def _key_callback(self, window, key, scancode, action, mods):
        if self.on_key:
            self.on_key(key, scancode, action, mods)

    def _char_callback(self, window, codepoint):
        if self.on_char:
            self.on_char(codepoint)

    def _mouse_button_callback(self, window, button, action, mods):
        if self.on_mouse_button:
            x, y = glfw.get_cursor_pos(window)
            self.on_mouse_button(button, action, mods, x, y)

    def _cursor_pos_callback(self, window, xpos, ypos):
        if self.on_mouse_move:
            self.on_mouse_move(xpos, ypos)

    def initialize(self):
        glfw.set_error_callback(self._error_callback)

        if not glfw.init():
            print("[Error] No se pudo inicializar GLFW")
            sys.exit(1)

        # == CLAVE: Vulkan puro ==
        # CLIENT_API = NO_API -> GLFW NO crea ningún contexto OpenGL.
        # La única conexión con la GPU es la superficie Vulkan (VkSurfaceKHR).
        glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)
        glfw.window_hint(glfw.RESIZABLE, glfw.TRUE)
        glfw.window_hint(glfw.SCALE_TO_MONITOR, glfw.TRUE)

        self.window = glfw.create_window(self.width, self.height, self.title, None, None)
        if not self.window:
            print("[Error] No se pudo crear la ventana de GLFW")
            glfw.terminate()
            sys.exit(1)

        glfw.set_framebuffer_size_callback(self.window, self._fb_size_callback)
        glfw.set_key_callback(self.window, self._key_callback)
        glfw.set_char_callback(self.window, self._char_callback)
        glfw.set_mouse_button_callback(self.window, self._mouse_button_callback)
        glfw.set_cursor_pos_callback(self.window, self._cursor_pos_callback)

        fb_w, fb_h = glfw.get_framebuffer_size(self.window)
        self._last_fb_width = fb_w
        self._last_fb_height = fb_h
        print("[OpnGL] Ventana GLFW creada con éxito (Vulkan / NO_API): {}x{}".format(fb_w, fb_h))

    # -- API pública ------------------------------------------------------
    def framebuffer_size(self):
        return glfw.get_framebuffer_size(self.window)

    def should_close(self):
        return glfw.window_should_close(self.window)

    def poll_events(self):
        glfw.poll_events()

    def get_cursor_pos(self):
        return glfw.get_cursor_pos(self.window)

    def consume_resize_flag(self):
        flag = self._framebuffer_resized
        self._framebuffer_resized = False
        return flag

    def run(self, render_callback=None):
        self.initialize()
        print("\n[OpnGL] Bucle interactivo iniciado. Cierra la ventana para salir.")
        try:
            while not glfw.window_should_close(self.window):
                glfw.poll_events()
                if render_callback:
                    render_callback()
        finally:
            self.close()

    def close(self):
        if self.window:
            glfw.destroy_window(self.window)
            self.window = None
        glfw.terminate()
        print("[OpnGL] Ventana cerrada y recursos liberados.")

    def __del__(self):
        if self.window is not None:
            try:
                self.close()
            except Exception:
                pass
