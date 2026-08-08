# Image: widget que muestra una textura cargada por ImageManager.
# Soporta ajuste de tamaño (fit) y tinte/opacidad, dibujando un quad con UV.
from opngl.core.vkutil import hex_color_to_rgba
from opngl.widgets.base import UIWidget, quad_verts

_FITS = ("stretch", "fill", "contain", "cover")


class Image(UIWidget):
    def __init__(self, src=None, width=None, height=None, x=None, y=None,
                 fit="contain", opacity=1.0, tint="#ffffff", id=None):
        super().__init__(id=id, x=x, y=y, width=width, height=height)
        self.src = src
        self.fit = fit if fit in _FITS else "contain"
        self.opacity = max(0.0, min(1.0, opacity))
        self.tint = tint
        self.clickable = False
        self._image_w = None
        self._image_h = None

    def natural_size(self):
        return self._image_w or 0, self._image_h or 0

    def measure(self, parent_width, parent_height):
        iw, ih = self.natural_size()
        if iw <= 0 or ih <= 0:
            return (self.width or 0, self.height or 0)
        w = self.width if self.width is not None else iw
        h = self.height if self.height is not None else ih
        return w, h

    def _rect_and_uv(self, iw, ih):
        w = self.width if self.width is not None else iw
        h = self.height if self.height is not None else ih
        x, y = self.x or 0, self.y or 0
        if self.fit in ("stretch", "fill"):
            return (x, y, w, h), (0.0, 0.0, 1.0, 1.0)
        ar_i = iw / ih
        ar_b = w / h
        if self.fit == "contain":
            if ar_i > ar_b:
                nw, nh = w, w / ar_i
            else:
                nw, nh = h * ar_i, h
            dx = (w - nw) * 0.5
            dy = (h - nh) * 0.5
            return (x + dx, y + dy, nw, nh), (0.0, 0.0, 1.0, 1.0)
        # cover: llena la caja recortando el exceso (recorte centrado)
        if ar_i > ar_b:
            nw, nh = h * ar_i, h
        else:
            nw, nh = w, w / ar_i
        u0 = (nw - w) / (2.0 * nw)
        v0 = (nh - h) / (2.0 * nh)
        return (x, y, w, h), (u0, v0, 1.0 - u0, 1.0 - v0)

    def draw(self, batch, fonts):
        if not self.visible or not self.src:
            return
        iw, ih = self.natural_size()
        if iw <= 0 or ih <= 0:
            return
        w = self.width if self.width is not None else iw
        h = self.height if self.height is not None else ih
        if w <= 0 or h <= 0:
            return
        rect, (u0, v0, u1, v1) = self._rect_and_uv(iw, ih)
        color = hex_color_to_rgba(self.tint)
        if self.opacity < 1.0:
            color = (color[0], color[1], color[2], color[3] * self.opacity)
        uv = [(u0, v0), (u1, v0), (u1, v1),
              (u0, v0), (u1, v1), (u0, v1)]
        batch.add_image(quad_verts(rect[0], rect[1], rect[2], rect[3], color, uv),
                        self.src)
