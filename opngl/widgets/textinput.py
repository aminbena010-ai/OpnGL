# TextInput: campo de texto de una línea con foco de teclado.
#
# Soporta: cursor intermitente, placeholder, edición con teclado
# (Backspace/Delete, flechas, Home/End), Ctrl+C/V/X con el portapapeles de
# GLFW, Enter para enviar y ESC para quitar el foco. La entrada se recorta
# horizontalmente (scroll) cuando el texto no cabe.
import glfw

from opngl.core.vkutil import hex_color_to_rgba
from opngl.widgets.base import UIWidget, quad_verts, rounded_quad_verts

_PAD = 8.0            # margen horizontal interior
_CARET_W = 2.0        # ancho del cursor


class TextInput(UIWidget):
    def __init__(self, text="", placeholder="", font_size=16, color="#e5e7eb",
                 placeholder_color="#6b7280", background="#1f2937",
                 hover_background="#1e2a3a", focused_background="#0f172a",
                 border_color="#374151", focused_border_color="#3b82f6",
                 border_width=1.0, border_radius=6.0, font=None,
                 max_length=None, width=None, height=None,
                 x=None, y=None, id=None):
        super().__init__(id=id, x=x, y=y, width=width, height=height)
        self.text = text
        self.placeholder = placeholder
        self.font_size = font_size
        self.color = color
        self.placeholder_color = placeholder_color
        self.background = background
        self.hover_background = hover_background
        self.focused_background = focused_background
        self.border_color = border_color
        self.focused_border_color = focused_border_color
        self.border_width = border_width
        self.border_radius = border_radius
        self.font = font
        self.max_length = max_length
        self.focused = False
        self.cursor = len(text)
        self._scroll = 0
        self._blink = 0.0
        self.change_handler = None
        self.submit_handler = None
        self.clickable = True

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def on_change(self, handler):
        """handler(widget) se invoca en cada edición del texto."""
        self.change_handler = handler
        return self

    def on_submit(self, handler):
        """handler(widget) se invoca al pulsar Enter."""
        self.submit_handler = handler
        return self

    def focus(self, px=None, py=None):
        self.focused = True
        self._blink = 0.0
        if px is not None:
            self._cursor_at(px)
        else:
            self.cursor = len(self.text)
            self._clamp_scroll()
        return self

    def blur(self):
        self.focused = False
        return self

    def _tick(self, dt):
        """Avanza el temporizador del cursor (llamado por UIRenderer.update)."""
        if self.focused:
            self._blink += dt

    # ------------------------------------------------------------------ #
    # Eventos de teclado
    # ------------------------------------------------------------------ #
    def char_event(self, codepoint):
        """Recibe un codepoint de GLFW (set_char_callback)."""
        if not self.focused or codepoint is None:
            return
        c = chr(codepoint)
        if c in ("\n", "\r", "\x00", "\x1b"):
            return
        self._insert(c)

    def key_event(self, key, action, mods):
        """Recibe eventos de tecla. Devuelve True si la UI debe soltar el foco."""
        if not self.focused or action not in (glfw.PRESS, glfw.REPEAT):
            return False
        ctrl = bool(mods & glfw.MOD_CONTROL)
        if key == glfw.KEY_BACKSPACE:
            self._backspace()
        elif key == glfw.KEY_DELETE:
            self._delete()
        elif key == glfw.KEY_LEFT:
            self._move(-1)
        elif key == glfw.KEY_RIGHT:
            self._move(1)
        elif key == glfw.KEY_HOME:
            self.cursor = 0
            self._clamp_scroll()
        elif key == glfw.KEY_END:
            self.cursor = len(self.text)
            self._clamp_scroll()
        elif key in (glfw.KEY_ENTER, glfw.KEY_KP_ENTER):
            if self.submit_handler is not None:
                self.submit_handler(self)
        elif key == glfw.KEY_ESCAPE:
            return True
        elif ctrl and key == glfw.KEY_V:
            self._paste()
        elif ctrl and key == glfw.KEY_C:
            self._copy()
        elif ctrl and key == glfw.KEY_X:
            self._copy()
            self._delete()
        return False

    # ------------------------------------------------------------------ #
    # Edición interna
    # ------------------------------------------------------------------ #
    def _insert(self, s):
        if self.max_length is not None:
            room = max(0, self.max_length - len(self.text))
            s = s[:room]
        if not s:
            return
        self.text = self.text[:self.cursor] + s + self.text[self.cursor:]
        self.cursor += len(s)
        self._clamp_scroll()
        self._notify_change()

    def _backspace(self):
        if self.cursor <= 0:
            return
        self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        self.cursor -= 1
        self._clamp_scroll()
        self._notify_change()

    def _delete(self):
        if self.cursor >= len(self.text):
            return
        self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        self._clamp_scroll()
        self._notify_change()

    def _move(self, delta):
        self.cursor = max(0, min(len(self.text), self.cursor + delta))
        self._clamp_scroll()

    def _paste(self):
        try:
            clip = glfw.get_clipboard_string(glfw.get_current_context())
        except Exception:
            clip = None
        if clip:
            self._insert(clip)

    def _copy(self):
        if self.text:
            try:
                glfw.set_clipboard_string(glfw.get_current_context(), self.text)
            except Exception:
                pass

    def _notify_change(self):
        if self.change_handler is not None:
            self.change_handler(self)

    def _cursor_at(self, px):
        """Coloca el cursor según la posición X del clic."""
        atlas = getattr(self, "_atlas", None)
        offset = px - (self.x or 0) - _PAD
        if atlas is None or offset <= 0:
            self.cursor = 0
        else:
            shown = self.text[self._scroll:]
            i = 0
            for i in range(len(shown) + 1):
                if atlas.measure(shown[:i], self.font_size, None)[0] > offset:
                    break
            self.cursor = min(len(self.text), self._scroll + i)
        self._clamp_scroll()

    def _clamp_scroll(self):
        """Asegura que el cursor quede dentro del área visible (sin scroll)."""
        atlas = getattr(self, "_atlas", None)
        if atlas is None:
            return
        content_w = self._content_width()
        if content_w <= 0:
            return
        abs_w = [atlas.measure(self.text[:i], self.font_size, None)[0]
                 for i in range(len(self.text) + 1)]
        left = abs_w[self._scroll]
        caret = abs_w[self.cursor]
        if caret < left:
            self._scroll = max(0, self.cursor)
        elif caret - left > content_w:
            self._scroll = min(len(self.text), self.cursor)

    def _content_width(self):
        w = self.width or 0
        return max(0.0, w - 2 * _PAD)

    # ------------------------------------------------------------------ #
    # Medición y dibujo
    # ------------------------------------------------------------------ #
    def measure(self, parent_width, parent_height):
        w = self.width if self.width is not None else max(200.0,
                                                          len(self.text or "") * self.font_size * 0.6)
        h = self.height if self.height is not None else self.font_size + 16
        return w, h

    def draw(self, batch, fonts):
        if not self.visible:
            return
        w, h = self.width or 0, self.height or 0
        if w <= 0 or h <= 0:
            return
        bg = (self.focused_background if self.focused else
              self.hover_background if self.hovered else self.background)
        color = hex_color_to_rgba(bg)
        border = hex_color_to_rgba(
            self.focused_border_color if self.focused else self.border_color)
        batch.add_shape(rounded_quad_verts(self.x, self.y, w, h, color), w, h,
                        self.border_radius, self.border_width or 0.0,
                        border if border else None)

        atlas = fonts.get(self.font)
        if atlas is None:
            return
        self._clamp_scroll()
        content_w = self._content_width()

        shown = self.text if self.text else self.placeholder
        color_hex = self.color if self.text else self.placeholder_color
        text_color = hex_color_to_rgba(color_hex)

        abs_w = [atlas.measure(self.text[:i], self.font_size, None)[0]
                 for i in range(len(self.text) + 1)]
        left = abs_w[self._scroll]
        text_x = self.x + _PAD - left
        ty = self.y + max(0.0, (h - atlas.line_height(self.font_size)) / 2.0)
        mw = max(8.0, content_w + left)

        if shown:
            verts = atlas.build_text(shown, text_x, ty, self.font_size, text_color,
                                     align="left", max_width=None)
            batch.add_text(verts, self.font)

        if self.focused:
            if int(self._blink) % 2 == 0:
                caret_x = self.x + _PAD + (abs_w[self.cursor] - left)
                caret_y = ty
                caret_h = atlas.line_height(self.font_size)
                caret = quad_verts(caret_x, caret_y, _CARET_W, caret_h,
                                   hex_color_to_rgba(self.color))
                batch.add_shape(caret, _CARET_W, caret_h)
