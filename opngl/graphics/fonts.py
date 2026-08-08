# FontManager: registro de familias de fuentes del motor.
#
# Los recursos base del motor viven en resources/ junto al proyecto:
#   resources/fonts/<familia>.ttf   -> fuente TrueType cargable por nombre
#
# La familia por defecto es "dejavu" (incluida en resources/fonts); la fuente
# bitmap 8x8 sigue disponible como "8x8".
import os

from opngl.graphics.texture import FontAtlas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(ROOT, "resources")
FONTS_DIR = os.path.join(RESOURCES_DIR, "fonts")


class FontManager:
    """Mantiene los FontAtlas por familia y resuelve 'familia' desde el XML."""

    def __init__(self, device, default="dejavu"):
        self.device = device
        self._default = default
        self._fonts = {}

        self.register(FontAtlas.from_8x8(device))

        bundled = os.path.join(FONTS_DIR, "DejaVuSans.ttf")
        if os.path.exists(bundled):
            self.load_ttf("dejavu", bundled)
        else:
            self._default = "8x8"

        self._fonts.setdefault(self._default, self._fonts["8x8"])

    # ------------------------------------------------------------------ #
    def register(self, atlas, family=None):
        self._fonts[family or atlas.family] = atlas
        return atlas

    def load_ttf(self, family, path, atlas_size=64):
        return self.register(FontAtlas.from_ttf(self.device, path, family=family,
                                                atlas_size=atlas_size))

    def find_ttf(self, family):
        """Busca resources/fonts/<family>.ttf y la registra si existe."""
        path = os.path.join(FONTS_DIR, family + ".ttf")
        if os.path.exists(path):
            return self.load_ttf(family, path)
        return None

    def get(self, family=None):
        name = family or self._default
        atlas = self._fonts.get(name)
        if atlas is not None:
            return atlas
        self.find_ttf(name)
        return self._fonts.get(name, self.default)

    @property
    def default(self):
        return self._fonts[self._default]

    def families(self):
        return list(self._fonts)

    def metrics(self, family=None):
        """(avance_medio_factor, line_height_factor) para estimar layout."""
        atlas = self.get(family)
        return (atlas.adv_factor, atlas.line_height_factor)

    def destroy(self):
        for atlas in self._fonts.values():
            if atlas.texture is not None:
                atlas.texture.destroy()
        self._fonts.clear()
