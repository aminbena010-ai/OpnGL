# ImageManager: carga imágenes (PNG/JPG/…) y las sube a texturas Vulkan.
#
# Las texturas de imagen se crean en formato R8G8B8A8_SRGB (la GPU decodifica
# sRGB -> lineal al muestrear) con filtrado LINEAL, de modo que la swapchain
# SRGB re-encodifica en pantalla y las imágenes se ven con el color correcto
# y sin escalado pixelado.
import os

import vulkan as vk
from PIL import Image as PILImage

from opngl.graphics.texture import Texture
from opngl.resources import resolve


class ImageManager:
    """Cache de texturas de imagen por nombre o ruta."""

    def __init__(self, device):
        self.device = device
        self._images = {}          # clave (alias o ruta abs) -> Texture
        self._loaded = {}          # nombre -> ruta absoluta resuelta

    # ------------------------------------------------------------------ #
    def load(self, path, name=None, linear_filter=True, srgb=True):
        """Carga un archivo de imagen (PNG/JPG/…) y sube la textura.
        Si `name` no se da, la clave es la ruta resuelta."""
        resolved = self._resolve(path)
        key = name or resolved
        existing = self._images.get(key)
        if existing is not None:
            return existing

        img = PILImage.open(resolved)
        img = img.convert("RGBA")
        w, h = img.size
        image_format = (vk.VK_FORMAT_R8G8B8A8_SRGB if srgb
                        else vk.VK_FORMAT_R8G8B8A8_UNORM)
        filter_mode = vk.VK_FILTER_LINEAR if linear_filter else vk.VK_FILTER_NEAREST
        tex = Texture(self.device, w, h, img.tobytes(), image_format,
                      filter_mode=filter_mode)
        tex.name = name or os.path.basename(resolved)
        self._images[key] = tex
        self._loaded[key] = resolved
        return tex

    def register(self, texture, name):
        """Registra una textura ya creada bajo un alias."""
        self._images[name] = texture
        self._loaded[name] = name
        return texture

    def get(self, name):
        """Devuelve la textura <name> (alias o ruta), cargándola si hace falta."""
        if name is None:
            return None
        tex = self._images.get(name)
        if tex is None:
            try:
                tex = self.load(name)
            except FileNotFoundError:
                return None
        return tex

    def names(self):
        return list(self._images)

    def has(self, name):
        return name in self._images

    # ------------------------------------------------------------------ #
    def _resolve(self, path):
        found = resolve(path, "images")
        if found is not None:
            return found
        from opngl.resources import search_locations
        raise FileNotFoundError(
            "[OpnGL] Imagen no encontrada: '{}'\n"
            "  Buscada en:\n"
            "    - {}\n"
            "  Coloca el archivo junto a tu script .py, en la carpeta desde la\n"
            "  que ejecutas, o en opngl/resources/images/.".format(
                path, "\n    - ".join(search_locations(path, "images"))))

    def destroy(self):
        for tex in self._images.values():
            tex.destroy()
        self._images.clear()
        self._loaded.clear()
