# Widget base del sistema UI de OpnGL.
# La UI es un árbol de widgets; cada widget puede emitir geometría a un
# Batch (solid / rounded / text) y recibir eventos de ratón.
import itertools

_counter = itertools.count(1)


def quad_verts(x, y, w, h, color, uv=None):
    """6 vértices [pos3, color4, uv2] de un quad en píxeles (origen arriba-izq)."""
    if uv is None:
        uv = [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0)]
    c = tuple(color)
    (u0, v0), (u1, v1), (u2, v2), (u3, v3), (u4, v4), (u5, v5) = uv
    x0, y0, x1, y1 = x, y, x + w, y + h
    return [
        x0, y0, 0.0, *c, u0, v0,
        x1, y0, 0.0, *c, u1, v1,
        x1, y1, 0.0, *c, u2, v2,
        x0, y0, 0.0, *c, u3, v3,
        x1, y1, 0.0, *c, u4, v4,
        x0, y1, 0.0, *c, u5, v5,
    ]


def rounded_quad_verts(x, y, w, h, color):
    """Quad para el shader de esquinas redondeadas: uv = coords locales (px)."""
    cx, cy = x + w / 2.0, y + h / 2.0
    return [
        x, y, 0.0, *color, x - cx, y - cy,
        x + w, y, 0.0, *color, x + w - cx, y - cy,
        x + w, y + h, 0.0, *color, x + w - cx, y + h - cy,
        x, y, 0.0, *color, x - cx, y - cy,
        x + w, y + h, 0.0, *color, x + w - cx, y + h - cy,
        x, y + h, 0.0, *color, x - cx, y + h - cy,
    ]


class Batch:
    """Acumula geometría del frame agrupada por tipo de pipeline.
    Solo hay dos pipelines en el motor: 'shape' (solid/rounded/borde/gradiente)
    y 'text'. Los items de 'shape' se agrupan por sus push-constants para
    minimizar cambios de pipeline."""

    def __init__(self):
        self.shape = {}     # (w,h,radius,bw, border_rgba, grad_rgba) -> verts
        self.text = {}      # familia de fuente -> vértices
        self.image = {}     # nombre de imagen -> vértices
        self.alpha = 1.0    # multiplicador global de alfa (transiciones)

    def _alpha(self, verts):
        if self.alpha >= 1.0:
            return verts
        out = verts[:]
        for i in range(0, len(out), 9):
            out[i + 6] *= self.alpha
        return out

    def add_shape(self, verts, w, h, radius=0.0, border_width=0.0,
                  border_color=None, gradient=None):
        key = (w, h, radius, border_width, border_color or (), gradient or ())
        self.shape.setdefault(key, []).extend(self._alpha(verts))

    def add_text(self, verts, family=None):
        self.text.setdefault(family, []).extend(self._alpha(verts))

    def add_image(self, verts, name=None):
        self.image.setdefault(name, []).extend(self._alpha(verts))


class UIWidget:
    def __init__(self, id=None, x=None, y=None, width=None, height=None, z=0):
        self.id = id if id is not None else "w{}".format(next(_counter))
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.z = z
        self.parent = None
        self.children = []
        self.visible = True
        self.hovered = False
        self.pressed = False
        self.clickable = False
        self.click_handler = None

    # -- árbol -----------------------------------------------------------
    def add(self, child):
        child.parent = self
        self.children.append(child)
        return child

    def find(self, widget_id):
        if self.id == widget_id:
            return self
        for c in self.children:
            r = c.find(widget_id)
            if r is not None:
                return r
        return None

    def on_click(self, handler):
        self.clickable = True
        self.click_handler = handler
        return self

    # -- medición y layout ------------------------------------------------
    def measure(self, parent_width, parent_height):
        return (self.width or 0, self.height or 0)

    def layout(self, x, y):
        self.x = x
        self.y = y
        self.layout_children()

    def layout_children(self):
        for c in self.children:
            pass

    # -- dibujo ----------------------------------------------------------
    def draw(self, batch, fonts):
        """Por defecto dibuja los hijos. Los widgets hoja redefinen este método."""
        for c in self.children:
            c.draw(batch, fonts)

    # -- hit-testing -----------------------------------------------------
    def contains(self, px, py):
        if not self.visible:
            return False
        return (self.x <= px < self.x + (self.width or 0)
                and self.y <= py < self.y + (self.height or 0))

    def find_at(self, px, py):
        for c in reversed(self.children):
            hit = c.find_at(px, py)
            if hit is not None:
                return hit
        if self.clickable and self.contains(px, py):
            return self
        return None
