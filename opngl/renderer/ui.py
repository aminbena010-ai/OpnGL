# UIRenderer: recorre el árbol de widgets, genera la geometría por frame
# (batches solid/rounded/text), gestiona interacción de ratón y las
# transiciones entre interfaces (fade).
import glfw

from opngl.widgets.base import Batch


class UIRenderer:
    def __init__(self):
        self.root = None
        self._hovered = None
        self._pressed = None
        self._focused = None
        self._transition = None   # (old, new, elapsed, duration)

    # ------------------------------------------------------------------ #
    def set_root(self, root):
        self.root = root
        self._focused = None
        self._transition = None

    def transition_to(self, new_root, duration=0.3):
        """Fade hacia `new_root`. Deja `root` como interfaz activa."""
        if self.root is None:
            self.root = new_root
            return
        self._transition = [self.root, new_root, 0.0, max(0.01, duration)]

    def _active_root(self):
        """Devuelve la raíz donde los eventos deben dirigirse.

        Durante una transición de fade, los eventos van a la nueva raíz
        (que se está fundiendo en), no a la vieja que se está fundiendo fuera."""
        if self._transition is not None:
            return self._transition[1]
        return self.root

    def update(self, dt):
        if self._transition is not None:
            self._transition[2] += dt
            if self._transition[2] >= self._transition[3]:
                self.root = self._transition[1]
                self._transition = None
        if self._focused is not None and hasattr(self._focused, "_tick"):
            self._focused._tick(dt)

    # ------------------------------------------------------------------ #
    def render(self, renderer, cb):
        if self.root is None:
            return
        if self._transition is not None:
            old, new, t, dur = self._transition
            k = min(1.0, t / dur)
            self._draw_root(renderer, cb, old, 1.0 - k)
            self._draw_root(renderer, cb, new, k)
        else:
            self._draw_root(renderer, cb, self.root, 1.0)

    def _draw_root(self, renderer, cb, root, alpha):
        batch = Batch()
        batch.alpha = alpha
        root.draw(batch, renderer.fonts)
        for (w, h, radius, bw, bcolor, grad), verts in batch.shape.items():
            renderer.draw(cb, verts, "shape", (w, h), radius,
                          border_width=bw, border_color=bcolor or None,
                          gradient=grad or None)
        for family, verts in batch.text.items():
            renderer.draw(cb, verts, "text", descriptor_set=renderer.descriptor_for(family))
        for name, verts in batch.image.items():
            renderer.draw(cb, verts, "image", descriptor_set=renderer.image_descriptor_for(name))

    # ------------------------------------------------------------------ #
    # Eventos de ratón (conectados a OpnGLWindow)
    # ------------------------------------------------------------------ #
    def on_mouse_move(self, x, y):
        if self.root is None:
            return
        target = self._active_root()
        hit = target.find_at(x, y)
        if hit is not self._hovered:
            if self._hovered is not None:
                self._hovered.hovered = False
            self._hovered = hit
            if hit is not None:
                hit.hovered = True

    def on_mouse_button(self, button, action, mods, x, y):
        if self.root is None or button != glfw.MOUSE_BUTTON_LEFT:
            return
        target = self._active_root()
        if action == glfw.PRESS:
            self._pressed = target.find_at(x, y)
            if self._pressed is not None:
                self._pressed.pressed = True
            self._handle_focus(self._pressed, x, y)
        elif action == glfw.RELEASE:
            hit = target.find_at(x, y)
            if self._pressed is not None:
                self._pressed.pressed = False
                if hit is self._pressed and self._pressed.click_handler is not None:
                    self._pressed.click_handler(self._pressed)
            self._pressed = None

    def _handle_focus(self, widget, x, y):
        """Da foco a un TextInput al pulsar sobre él; si no, lo quita."""
        if widget is not None and hasattr(widget, "focus"):
            if self._focused is not None and self._focused is not widget:
                self._focused.blur()
            self._focused = widget
            widget.focus(x, y)
        elif self._focused is not None:
            self._focused.blur()
            self._focused = None

    # ------------------------------------------------------------------ #
    # Eventos de teclado (conectados a OpnGLWindow)
    # ------------------------------------------------------------------ #
    def on_key(self, key, scancode, action, mods):
        if self._focused is not None and hasattr(self._focused, "key_event"):
            if self._focused.key_event(key, action, mods):
                self._focused.blur()
                self._focused = None

    def on_char(self, codepoint):
        if self._focused is not None and hasattr(self._focused, "char_event"):
            self._focused.char_event(codepoint)
