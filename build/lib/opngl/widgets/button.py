# Button: botón con esquinas redondeadas, estados hover/pressed y texto.
from opngl.core.vkutil import hex_color_to_rgba
from opngl.widgets.base import UIWidget, rounded_quad_verts


class Button(UIWidget):
    def __init__(self, text="Button", width=None, height=None,
                 background="#3b82f6", hover_background="#4f93f7",
                 pressed_background="#2f6ce0", color="#ffffff",
                 font_size=16, border_radius=6.0, border_width=0.0,
                 border_color=None, gradient=None, font=None, sound=None,
                 x=None, y=None, id=None):
        super().__init__(id=id, x=x, y=y, width=width, height=height)
        self.text = text
        self.background = background
        self.hover_background = hover_background
        self.pressed_background = pressed_background
        self.color = color
        self.font_size = font_size
        self.border_radius = border_radius
        self.border_width = border_width
        self.border_color = border_color
        self.gradient = gradient
        self.font = font
        self.sound = sound
        self.clickable = True

    def measure(self, parent_width, parent_height):
        atlas = getattr(self, "_atlas", None)
        if atlas is not None:
            text_w = atlas.measure(self.text, self.font_size, None)[0]
        else:
            adv = getattr(self, "_adv_factor", 0.6)
            text_w = len(self.text) * self.font_size * adv
        w = self.width if self.width is not None else max(120.0, text_w + 2 * self.font_size)
        h = self.height if self.height is not None else max(36.0, self.font_size + 14)
        return w, h

    def draw(self, batch, fonts):
        if not self.visible:
            return
        bg = self.pressed_background if self.pressed else (
            self.hover_background if self.hovered else self.background)
        color = hex_color_to_rgba(bg)
        w, h = self.width or 0, self.height or 0
        border = hex_color_to_rgba(self.border_color) if self.border_color else None
        grad = hex_color_to_rgba(self.gradient) if self.gradient else None
        batch.add_shape(rounded_quad_verts(self.x, self.y, w, h, color), w, h,
                        self.border_radius, self.border_width or 0.0, border, grad)

        atlas = fonts.get(self.font)
        text_color = hex_color_to_rgba(self.color)
        mw = max(8.0, w - 2 * 8)
        _, th = atlas.wrap_lines(self.text, self.font_size, mw)
        ty = self.y + max(0.0, (h - th) / 2.0)
        verts = atlas.build_text(self.text, self.x, ty, self.font_size, text_color,
                                 align="center", max_width=mw)
        batch.add_text(verts, self.font)
