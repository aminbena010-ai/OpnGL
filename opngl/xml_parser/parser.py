# Parser de XML robusto: convierte <AppWindow>, <VBox>, <HBox>, <Panel>,
# <Button>, <Label> (y tags registrados por el usuario) en el árbol de
# widgets del motor, validando atributos y reportando errores con contexto.
import xml.etree.ElementTree as ET

from opngl.widgets.base import UIWidget
from opngl.widgets.containers import AppWindow, VBox, HBox, Panel
from opngl.widgets.button import Button
from opngl.widgets.image import Image
from opngl.widgets.label import Label
from opngl.widgets.textinput import TextInput

# -- registro de tags ------------------------------------------------------
_INT = ("x", "y", "padding", "spacing")
_FLOAT = ("width", "height", "font_size", "border_radius", "border_width")


class WidgetFactory:
    """Crea un widget a partir de un elemento XML validando atributos."""

    def __init__(self, cls, defaults=None, numeric=None, color_attrs=()):
        self.cls = cls
        self.defaults = defaults or {}
        self.numeric = numeric or {}
        self.color_attrs = color_attrs

    def build(self, node):
        attrs = dict(self.defaults)
        unknown = []
        for key, value in node.attrib.items():
            key = key.replace("-", "_")
            if key in self.numeric:
                try:
                    attrs[key] = self.numeric[key](value)
                except ValueError:
                    raise ValueError("Atributo '{}' debe ser numérico: '{}'".format(key, value))
            else:
                attrs[key] = value
        widget = self.cls(**attrs)
        return widget


_TAG_FACTORIES = {
    "AppWindow": WidgetFactory(AppWindow, {
        "width": 800, "height": 600, "padding": 20, "spacing": 12,
        "background": "#111827", "border_radius": 0.0,
        "border_width": 0.0, "border_color": None, "gradient": None,
        "align": "stretch", "pack": "start",
    }, {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "VBox": WidgetFactory(VBox, {"spacing": 10, "padding": 0,
                                 "border_width": 0.0, "border_color": None,
                                 "gradient": None, "align": "stretch",
                                 "pack": "start"},
                          {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "HBox": WidgetFactory(HBox, {"spacing": 10, "padding": 0,
                                 "border_width": 0.0, "border_color": None,
                                 "gradient": None, "align": "stretch",
                                 "pack": "start"},
                          {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "Panel": WidgetFactory(Panel, {"padding": 0, "border_radius": 0.0,
                                   "border_width": 0.0, "border_color": None,
                                   "gradient": None, "align": "stretch",
                                   "pack": "start"},
                           {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "Button": WidgetFactory(Button, {
        "text": "Button", "width": None, "height": None,
        "background": "#3b82f6", "hover_background": "#4f93f7",
        "pressed_background": "#2f6ce0", "color": "#ffffff",
        "font_size": 16.0, "border_radius": 6.0, "border_width": 0.0,
        "border_color": None, "gradient": None, "font": None, "sound": None,
    }, {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "Label": WidgetFactory(Label, {"text": "", "font_size": 16.0, "color": "#ffffff",
                                   "align": "left", "valign": "top", "font": None},
                           {k: float for k in _FLOAT} | {k: int for k in _INT}),
    "Image": WidgetFactory(Image, {"src": None, "width": None, "height": None,
                                   "fit": "contain", "opacity": 1.0,
                                   "tint": "#ffffff"},
                           {k: float for k in _FLOAT} | {k: int for k in _INT}
                           | {"opacity": float}),
    "TextInput": WidgetFactory(TextInput, {
        "text": "", "placeholder": "", "font_size": 16.0, "color": "#e5e7eb",
        "placeholder_color": "#6b7280", "background": "#1f2937",
        "hover_background": "#1e2a3a", "focused_background": "#0f172a",
        "border_color": "#374151", "focused_border_color": "#3b82f6",
        "border_width": 1.0, "border_radius": 6.0, "font": None,
        "max_length": None, "width": None, "height": None,
    }, {k: float for k in _FLOAT} | {k: int for k in _INT}
       | {"max_length": int}),
    "Input": WidgetFactory(TextInput, {
        "text": "", "placeholder": "", "font_size": 16.0, "color": "#e5e7eb",
        "placeholder_color": "#6b7280", "background": "#1f2937",
        "hover_background": "#1e2a3a", "focused_background": "#0f172a",
        "border_color": "#374151", "focused_border_color": "#3b82f6",
        "border_width": 1.0, "border_radius": 6.0, "font": None,
        "max_length": None, "width": None, "height": None,
    }, {k: float for k in _FLOAT} | {k: int for k in _INT}
       | {"max_length": int}),
}

_CONTAINERS = {"AppWindow", "VBox", "HBox", "Panel"}


class XMLUIParser:
    def __init__(self, source):
        """source: ruta a un archivo .xml o una cadena XML."""
        self.source = source
        self.factories = dict(_TAG_FACTORIES)

    def register_tag(self, tag, factory):
        self.factories[tag] = factory

    # ------------------------------------------------------------------ #
    def _load_tree(self):
        if isinstance(self.source, str) and ("<" in self.source and ">" in self.source):
            return ET.fromstring(self.source)
        return ET.parse(self.source).getroot()

    def parse(self):
        root = self._load_tree()
        widget = self._build(root, parent_required=False)
        return widget

    # ------------------------------------------------------------------ #
    def _build(self, node, parent_required):
        tag = node.tag
        if tag not in self.factories:
            raise ValueError("[OpnGL UI] Tag XML desconocido: <{}>".format(tag))
        factory = self.factories[tag]
        widget = factory.build(node)
        if tag in _CONTAINERS:
            for child in node:
                if isinstance(child.tag, str):
                    if child.tag not in self.factories:
                        raise ValueError("[OpnGL UI] <{}> contiene tag desconocido: <{}>".format(tag, child.tag))
                    widget.add(self._build(child, parent_required=True))
        return widget

    def __repr__(self):
        return "XMLUIParser({!r})".format(self.source)
