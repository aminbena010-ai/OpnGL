# Label: texto simple renderizado con el atlas de glifos.
from opngl.core.vkutil import hex_color_to_rgba
from opngl.widgets.base import UIWidget


class Label(UIWidget):
    def __init__(self, text="", font_size=16.0, color="#ffffff", x=None, y=None,
                 width=None, height=None, align="left", valign="top",
                 font=None, id=None):
        super().__init__(id=id, x=x, y=y, width=width, height=height)
        self.text = text
        self.font_size = font_size
        self.color = color
        self.align = align if align in ("left", "center", "right") else "left"
        self.valign = valign if valign in ("top", "middle", "bottom") else "top"
        self.font = font
        self.max_width = width

    def measure(self, parent_width, parent_height):
        if self.max_width is None and parent_width:
            self.max_width = parent_width
        atlas = getattr(self, "_atlas", None)
        if atlas is not None:
            return atlas.measure(self.text, self.font_size, self.max_width)
        adv = getattr(self, "_adv_factor", 0.6)
        line = getattr(self, "_line_factor", 1.2)
        natural = len(self.text) * self.font_size * adv
        if self.max_width and natural > self.max_width:
            lines = max(1, int(natural // self.max_width) + 1)
            return self.max_width, lines * self.font_size * line
        return natural, self.font_size * line

    def draw(self, batch, fonts):
        if not self.visible or not self.text:
            return
        atlas = fonts.get(self.font)
        if atlas is None:
            return
        color = hex_color_to_rgba(self.color)
        mw = self.max_width if self.max_width is not None else self.width
        lines, total_h = atlas.wrap_lines(self.text, self.font_size, mw)
        y = self.y
        if self.valign != "top" and self.parent is not None:
            box_h = self.height or 0
            if abs(box_h - total_h) < 1.0:
                box_h = (self.parent.height or 0) - 2 * getattr(self.parent, "padding", 0)
            if box_h > total_h:
                if self.valign == "middle":
                    y += (box_h - total_h) * 0.5
                elif self.valign == "bottom":
                    y += box_h - total_h
        verts = atlas.build_text(self.text, self.x, y, self.font_size, color,
                                 align=self.align, max_width=mw)
        batch.add_text(verts, self.font)
