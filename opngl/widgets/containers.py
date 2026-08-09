# Contenedores: VBox, HBox, Panel y AppWindow con medición y layout 2D.
from opngl.core.vkutil import hex_color_to_rgba
from opngl.widgets.base import UIWidget, rounded_quad_verts


class Container(UIWidget):
    def __init__(self, id=None, spacing=0, padding=0, background=None,
                 border_radius=0.0, border_width=0.0, border_color=None,
                 gradient=None, x=None, y=None, width=None, height=None,
                 align="stretch", pack="start", title=None, **kw):
        super().__init__(id=id, x=x, y=y, width=width, height=height)
        self.title = title
        self.spacing = spacing
        self.padding = padding
        self.background = background
        self.border_radius = border_radius
        self.border_width = border_width
        self.border_color = border_color
        self.gradient = gradient
        self.align = align if align in ("stretch", "left", "center", "right",
                                        "top", "bottom") else "stretch"
        self.pack = pack if pack in ("start", "center", "end") else "start"
        self.orientation = "vertical"  # 'vertical' | 'horizontal'

    # -- medición ----------------------------------------------------------
    def _children_sizes(self):
        pad = self.padding
        avail_w = self.width - 2 * pad if self.width is not None else None
        avail_h = self.height - 2 * pad if self.height is not None else None
        sizes = []
        for c in self.children:
            if self.orientation == "vertical":
                w = c.width
                if w is None:
                    pw = avail_w if self.align == "stretch" else None
                    w = avail_w if self.align == "stretch" else c.measure(pw, None)[0]
                h = c.height
                if h is None:
                    h = c.measure(w, None)[1]
                sizes.append((w, h))
            else:
                h = c.height
                if h is None:
                    ph = avail_h if self.align == "stretch" else None
                    h = avail_h if self.align == "stretch" else c.measure(None, ph)[1]
                w = c.width
                if w is None:
                    w = c.measure(None, h)[0]
                sizes.append((w, h))
        return sizes

    def measure(self, parent_width, parent_height):
        sizes = self._children_sizes()
        if self.orientation == "vertical":
            w = max([s[0] or 0 for s in sizes], default=0) + 2 * self.padding
            h = sum(s[1] or 0 for s in sizes) + self.spacing * max(len(sizes) - 1, 0) + 2 * self.padding
        else:
            h = max([s[1] or 0 for s in sizes], default=0) + 2 * self.padding
            w = sum(s[0] or 0 for s in sizes) + self.spacing * max(len(sizes) - 1, 0) + 2 * self.padding
        if self.width is not None:
            w = self.width
        if self.height is not None:
            h = self.height
        return w, h

    # -- layout ------------------------------------------------------------
    def _main_offset(self, children, sizes, avail):
        """Desplazamiento inicial según self.pack ('start'|'center'|'end')
        sobre el eje principal, usando solo los hijos apilados (los que no
        tienen posición fija en ese eje: sin 'y' en vertical, sin 'x' en
        horizontal)."""
        pack = self.pack
        if pack == "start":
            return 0.0
        if self.orientation == "vertical":
            stack = [h for c, (w, h) in zip(children, sizes) if c.y is None]
        else:
            stack = [w for c, (w, h) in zip(children, sizes) if c.x is None]
        total = sum(x or 0 for x in stack) + self.spacing * max(len(stack) - 1, 0)
        if pack == "center":
            return max(0.0, (avail - total) * 0.5)
        return max(0.0, avail - total)

    def layout_children(self):
        pad = self.padding
        if self.width is None:
            self.width = self.parent.width - 2 * self.parent.padding if self.parent else 0
        if self.height is None:
            self.height = self.parent.height - 2 * self.parent.padding if self.parent else 0
        avail_w = max(0.0, (self.width or 0) - 2 * pad)
        avail_h = max(0.0, (self.height or 0) - 2 * pad)

        # Un único hijo contenedor apilado llena todo el espacio del padre
        # (ambos ejes): así pack/align pueden centrar o anclar el contenido
        # respecto al área completa a cualquier profundidad
        # (AppWindow > Panel > VBox), y sirven igual para centrar que para
        # pegar a la derecha/izquierda/arriba/abajo.
        stacked = [c for c in self.children
                   if (c.y is None if self.orientation == "vertical" else c.x is None)]
        if len(stacked) == 1 and isinstance(stacked[0], Container):
            child = stacked[0]
            if self.orientation == "vertical":
                if child.height is None:
                    child.height = avail_h
                if child.width is None:
                    child.width = avail_w
            else:
                if child.width is None:
                    child.width = avail_w
                if child.height is None:
                    child.height = avail_h

        sizes = self._children_sizes()
        if self.orientation == "vertical":
            x0 = self.x + pad
            y0 = self.y + pad + self._main_offset(self.children, sizes, avail_h)
            y = y0
            for c, (w, h) in zip(self.children, sizes):
                c.width = w
                c.height = h
                if c.x is not None:
                    cx = c.x
                else:
                    cx = x0
                    if self.align == "center" and (w or 0) <= avail_w:
                        cx = x0 + (avail_w - (w or 0)) * 0.5
                    elif self.align == "right" and (w or 0) <= avail_w:
                        cx = x0 + (avail_w - (w or 0))
                c.layout(cx, c.y if c.y is not None else y)
                y += (h or 0) + self.spacing
        else:
            x0 = self.x + pad + self._main_offset(self.children, sizes, avail_w)
            y0 = self.y + pad
            x = x0
            for c, (w, h) in zip(self.children, sizes):
                c.width = w
                c.height = h
                if c.y is not None:
                    cy = c.y
                else:
                    cy = y0
                    if self.align == "center" and (h or 0) <= avail_h:
                        cy = y0 + (avail_h - (h or 0)) * 0.5
                    elif self.align == "bottom" and (h or 0) <= avail_h:
                        cy = y0 + (avail_h - (h or 0))
                c.layout(c.x if c.x is not None else x, cy)
                x += (w or 0) + self.spacing

    # -- dibujo ------------------------------------------------------------
    def draw_background(self, batch):
        w, h = self.width or 0, self.height or 0
        if w <= 0 or h <= 0:
            return
        if self.background is None and self.border_color is None:
            return
        fill = hex_color_to_rgba(self.background) if self.background else (0.0, 0.0, 0.0, 0.0)
        border = hex_color_to_rgba(self.border_color) if self.border_color else None
        grad = hex_color_to_rgba(self.gradient) if self.gradient else None
        batch.add_shape(rounded_quad_verts(self.x, self.y, w, h, fill), w, h,
                        self.border_radius or 0.0, self.border_width or 0.0,
                        border, grad)

    def draw(self, batch, fonts):
        if not self.visible:
            return
        self.draw_background(batch)
        for c in self.children:
            c.draw(batch, fonts)


class VBox(Container):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"


class HBox(Container):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "horizontal"


class Panel(Container):
    """Contenedor con fondo opcional (puede tener esquinas redondeadas)."""


class AppWindow(Container):
    """Widget raíz: ocupa toda la ventana y pinta el fondo de la app."""
