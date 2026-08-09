# Texture: imágenes de Vulkan (VkImage + view + sampler) y el atlas de texto.
import os

import vulkan as vk
from vulkan import ffi

from opngl.graphics.font8x8 import FONT8X8, FIRST, LAST

GLYPH_W = 8
GLYPH_H = 8
ATLAS_COLS = 16


class Texture:
    def __init__(self, device, width, height, pixels, image_format,
                 usage=vk.VK_IMAGE_USAGE_SAMPLED_BIT | vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT,
                 filter_mode=vk.VK_FILTER_NEAREST):
        self.device = device
        self.width = width
        self.height = height
        self.image_format = image_format
        self._keep = []
        self._create_image(pixels)
        self._create_view()
        self._create_sampler(filter_mode)

    # ------------------------------------------------------------------ #
    def _create_image(self, pixels):
        ici = vk.VkImageCreateInfo()
        ici.sType = vk.VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
        ici.imageType = vk.VK_IMAGE_TYPE_2D
        ici.format = self.image_format
        ici.extent.width = self.width
        ici.extent.height = self.height
        ici.extent.depth = 1
        ici.mipLevels = 1
        ici.arrayLayers = 1
        ici.samples = vk.VK_SAMPLE_COUNT_1_BIT
        ici.tiling = vk.VK_IMAGE_TILING_OPTIMAL
        ici.usage = vk.VK_IMAGE_USAGE_SAMPLED_BIT | vk.VK_IMAGE_USAGE_TRANSFER_DST_BIT
        ici.sharingMode = vk.VK_SHARING_MODE_EXCLUSIVE
        ici.initialLayout = vk.VK_IMAGE_LAYOUT_UNDEFINED
        self.image = vk.vkCreateImage(self.device.device, ici, None)

        reqs = vk.vkGetImageMemoryRequirements(self.device.device, self.image)
        self.memory = self.device.allocate_memory(
            reqs.size, reqs.memoryTypeBits, vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)
        vk.vkBindImageMemory(self.device.device, self.image, self.memory, 0)

        self._upload(pixels)

    def _upload(self, pixels):
        staging, staging_mem = self.device.create_buffer(
            len(pixels), vk.VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
        data = self.device.map_memory(staging_mem, len(pixels))
        data[:] = pixels
        self.device.unmap_memory(staging_mem)

        def record(cb):
            vk.vkCmdPipelineBarrier(
                cb,
                vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                0, 0, ffi.NULL, 0, ffi.NULL, 1, self._barrier(vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL))
            region = vk.VkBufferImageCopy()
            region.imageSubresource.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
            region.imageSubresource.layerCount = 1
            region.imageExtent.width = self.width
            region.imageExtent.height = self.height
            region.imageExtent.depth = 1
            vk.vkCmdCopyBufferToImage(cb, staging, self.image,
                                      vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, region)
            vk.vkCmdPipelineBarrier(
                cb,
                vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                vk.VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
                0, 0, ffi.NULL, 0, ffi.NULL, 1,
                self._barrier(vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL))

        self.device.execute_now(record)
        vk.vkDestroyBuffer(self.device.device, staging, None)
        vk.vkFreeMemory(self.device.device, staging_mem, None)

    def _barrier(self, new_layout):
        b = vk.VkImageMemoryBarrier()
        b.sType = vk.VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER
        b.oldLayout = vk.VK_IMAGE_LAYOUT_UNDEFINED
        b.newLayout = new_layout
        b.srcQueueFamilyIndex = vk.VK_QUEUE_FAMILY_IGNORED
        b.dstQueueFamilyIndex = vk.VK_QUEUE_FAMILY_IGNORED
        b.image = self.image
        b.subresourceRange.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
        b.subresourceRange.levelCount = 1
        b.subresourceRange.layerCount = 1
        if new_layout == vk.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL:
            b.srcAccessMask = 0
            b.dstAccessMask = vk.VK_ACCESS_TRANSFER_WRITE_BIT
        else:
            b.srcAccessMask = vk.VK_ACCESS_TRANSFER_WRITE_BIT
            b.dstAccessMask = vk.VK_ACCESS_SHADER_READ_BIT
        return b

    # ------------------------------------------------------------------ #
    def _create_view(self):
        iv = vk.VkImageViewCreateInfo()
        iv.sType = vk.VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
        iv.image = self.image
        iv.viewType = vk.VK_IMAGE_VIEW_TYPE_2D
        iv.format = self.image_format
        iv.components.r = vk.VK_COMPONENT_SWIZZLE_IDENTITY
        iv.components.g = vk.VK_COMPONENT_SWIZZLE_IDENTITY
        iv.components.b = vk.VK_COMPONENT_SWIZZLE_IDENTITY
        iv.components.a = vk.VK_COMPONENT_SWIZZLE_IDENTITY
        iv.subresourceRange.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
        iv.subresourceRange.levelCount = 1
        iv.subresourceRange.layerCount = 1
        self.view = vk.vkCreateImageView(self.device.device, iv, None)

    def _create_sampler(self, filter_mode):
        sci = vk.VkSamplerCreateInfo()
        sci.sType = vk.VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO
        sci.magFilter = filter_mode
        sci.minFilter = filter_mode
        sci.addressModeU = vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE
        sci.addressModeV = vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE
        sci.addressModeW = vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE
        sci.anisotropyEnable = vk.VK_FALSE
        sci.maxAnisotropy = 1.0
        sci.borderColor = vk.VK_BORDER_COLOR_INT_OPAQUE_WHITE
        sci.unnormalizedCoordinates = vk.VK_FALSE
        sci.compareEnable = vk.VK_FALSE
        sci.compareOp = vk.VK_COMPARE_OP_ALWAYS
        sci.mipmapMode = vk.VK_SAMPLER_MIPMAP_MODE_NEAREST
        sci.mipLodBias = 0.0
        sci.minLod = 0.0
        sci.maxLod = 0.0
        self.sampler = vk.vkCreateSampler(self.device.device, sci, None)

    def destroy(self):
        if self.device and self.device.device:
            vk.vkDestroySampler(self.device.device, self.sampler, None)
            vk.vkDestroyImageView(self.device.device, self.view, None)
            vk.vkDestroyImage(self.device.device, self.image, None)
            vk.vkFreeMemory(self.device.device, self.memory, None)


class FontAtlas:
    """Atlas de glifos en una VkImage R8 con métricas por carácter.

    Soporta dos fuentes:
      * from_8x8()  -> fuente bitmap incluida (ASCII 0x20..0x7E)
      * from_ttf()  -> fuente TrueType rasterizada con Pillow (acentos, etc.)

    build_text() convierte texto en vértices usando avance por glifo y la
    baseline, de forma que las cajas de texto son consistentes entre fuentes.
    """

    def __init__(self, device, family, atlas_size, baseline_px=0):
        self.device = device
        self.family = family
        self.atlas_size = atlas_size        # em de referencia en px
        self.baseline_px = baseline_px      # offset de baseline en el atlas
        self.line_height_factor = 1.0       # alto de línea = factor * font_size
        self.adv_factor = 1.0               # avance medio = factor * font_size
        self.glyphs = {}                    # code -> (u0,v0,u1,v1, rel_top_px, adv_px)
        self.default_advance = atlas_size
        self.width = 0
        self.height = 0
        self.texture = None
        self._keep = []

    # -- fabrica 8x8 --------------------------------------------------- #
    @classmethod
    def from_8x8(cls, device, family="8x8"):
        self = cls(device, family, atlas_size=GLYPH_H, baseline_px=0)
        rows = (LAST - FIRST + 1 + ATLAS_COLS - 1) // ATLAS_COLS
        self.width = ATLAS_COLS * GLYPH_W
        self.height = rows * GLYPH_H
        pixels = bytearray(self.width * self.height)
        for code in range(FIRST, LAST + 1):
            glyph = FONT8X8[code]
            idx = code - FIRST
            col = idx % ATLAS_COLS
            row = idx // ATLAS_COLS
            for y in range(GLYPH_H):
                for x in range(GLYPH_W):
                    if glyph[y] & (0x80 >> x):
                        px = col * GLYPH_W + x
                        py = row * GLYPH_H + y
                        pixels[py * self.width + px] = 255
        self.texture = Texture(device, self.width, self.height, bytes(pixels),
                               vk.VK_FORMAT_R8_UNORM)
        for code in range(FIRST, LAST + 1):
            idx = code - FIRST
            col = idx % ATLAS_COLS
            row = idx // ATLAS_COLS
            u0 = (col * GLYPH_W) / self.width
            v0 = (row * GLYPH_H) / self.height
            u1 = ((col + 1) * GLYPH_W) / self.width
            v1 = ((row + 1) * GLYPH_H) / self.height
            self.glyphs[code] = (u0, v0, u1, v1, 0.0, GLYPH_W)
        return self

    # -- fabrica TrueType ------------------------------------------------ #
    @classmethod
    def from_ttf(cls, device, path, family=None, atlas_size=64, chars=None,
                 cell_pad=2, cols=16):
        from PIL import Image, ImageDraw, ImageFont
        import math

        if family is None:
            family = os.path.splitext(os.path.basename(path))[0]
        font = ImageFont.truetype(path, atlas_size)
        asc, desc = font.getmetrics()

        if chars is None:
            chars = [c for c in range(0x20, 0x100)]
            chars += [0x00A0, 0x2013, 0x2014, 0x2018, 0x2019,
                      0x201C, 0x201D, 0x2026, 0x20AC]
        advances = {c: font.getlength(chr(c)) for c in chars}
        max_adv = max(advances.values(), default=float(atlas_size))
        cell_w = int(math.ceil(max_adv)) + cell_pad * 2
        cell_h = asc + desc + cell_pad * 2
        rows = (len(chars) + cols - 1) // cols
        atlas_w = cols * cell_w
        atlas_h = rows * cell_h
        img = Image.new("L", (atlas_w, atlas_h), 0)
        draw = ImageDraw.Draw(img)

        self = cls(device, family, atlas_size=atlas_size, baseline_px=asc)
        self.line_height_factor = max(1.0, (asc + desc) / atlas_size)
        self.adv_factor = (sum(advances.values()) / max(len(advances), 1)) / atlas_size
        self.width = atlas_w
        self.height = atlas_h
        for i, code in enumerate(chars):
            ch = chr(code)
            adv = advances[code]
            bbox = font.getbbox(ch, anchor="ls")
            ink_w = max(0, bbox[2] - bbox[0])
            ink_h = max(0, bbox[3] - bbox[1])
            col = i % cols
            row = i // cols
            cx0 = col * cell_w + cell_pad
            baseline_y = row * cell_h + cell_pad + asc
            # Ancla "ls": el texto se dibuja con su baseline en baseline_y,
            # de modo que TODOS los glifos comparten la misma línea base.
            # El bbox "ls" da coordenadas relativas a esa baseline:
            #   ink.x ∈ [bbox[0], bbox[2]], ink.y ∈ [bbox[1] (arriba), bbox[3] (abajo)]
            draw.text((cx0, baseline_y), ch, font=font, fill=255, anchor="ls")
            if ink_w <= 0 or ink_h <= 0:
                self.glyphs[code] = (0.0, 0.0, 0.0, 0.0, asc, adv)
                continue
            x0 = cx0 + bbox[0]
            y0 = baseline_y + bbox[1]
            x1 = cx0 + bbox[2]
            y1 = baseline_y + bbox[3]
            u0 = x0 / atlas_w
            v0 = y0 / atlas_h
            u1 = x1 / atlas_w
            v1 = y1 / atlas_h
            # rel_top: distancia desde la línea de ascendentes (tope de la caja)
            # hasta el borde superior del glifo. Todos los glifos quedan en la
            # misma baseline: ink_top = cy + rel_top*scale, ink_bottom = cy + asc*scale.
            rel_top = asc + bbox[1]
            self.glyphs[code] = (u0, v0, u1, v1, rel_top, adv)
        self.texture = Texture(device, atlas_w, atlas_h, img.tobytes(),
                               vk.VK_FORMAT_R8_UNORM)
        return self

    # ------------------------------------------------------------------ #
    def _adv(self, code):
        return self.glyphs.get(code, (0, 0, 0, 0, 0, self.default_advance))[5]

    def _measure(self, text):
        return sum(self._adv(ord(ch)) for ch in text)

    def line_height(self, font_size):
        return self.line_height_factor * font_size

    def wrap_lines(self, text, font_size, max_width):
        """Divide el texto en líneas por palabras y por saltos \n.
        Devuelve (lines, height_px)."""
        if not text:
            return [text], self.line_height(font_size)
        scale = font_size / self.atlas_size
        if max_width is None or max_width <= 0:
            lines = text.split("\n")
            return lines, len(lines) * self.line_height(font_size)
        space_w = self._adv(ord(" ")) * scale
        lines = []
        for paragraph in text.split("\n"):
            cur = ""
            cur_w = 0.0
            for word in paragraph.split(" "):
                word_w = self._measure(word) * scale
                if cur and cur_w + space_w + word_w > max_width:
                    lines.append(cur)
                    cur = word
                    cur_w = word_w
                else:
                    cur = cur + (" " if cur else "") + word
                    cur_w += (space_w if cur_w else 0.0) + word_w
            if cur:
                lines.append(cur)
        return lines, len(lines) * self.line_height(font_size)

    def measure(self, text, font_size, max_width=None):
        scale = font_size / self.atlas_size
        lines, h = self.wrap_lines(text, font_size, max_width)
        return max((self._measure(line) for line in lines), default=0) * scale, h

    def build_text(self, text, x, y, font_size, color, align="left", max_width=None):
        """Devuelve una lista de floats [pos3, color4, uv2] para cada vértice."""
        scale = font_size / self.atlas_size
        lines, _ = self.wrap_lines(text, font_size, max_width)
        ref_w = max_width if max_width else max((self._measure(line)
                                                 for line in lines), default=0) * scale
        verts = []
        cy = y
        for line in lines:
            line_w = self._measure(line) * scale
            cx = x
            if align == "center":
                cx = x + (ref_w - line_w) * 0.5
            elif align == "right":
                cx = x + (ref_w - line_w)
            for ch in line:
                code = ord(ch)
                g = self.glyphs.get(code)
                adv = self._adv(code)
                if g is None or (g[2] - g[0]) <= 0.0:
                    cx += adv * scale
                    continue
                u0, v0, u1, v1, rel_top, _ = g
                gw = (u1 - u0) * self.width * scale
                gh = (v1 - v0) * self.height * scale
                top = cy + rel_top * scale
                verts += [
                    cx, top, 0.0, *color, u0, v0,
                    cx + gw, top, 0.0, *color, u1, v0,
                    cx + gw, top + gh, 0.0, *color, u1, v1,
                    cx, top, 0.0, *color, u0, v0,
                    cx + gw, top + gh, 0.0, *color, u1, v1,
                    cx, top + gh, 0.0, *color, u0, v1,
                ]
                cx += adv * scale
            cy += self.line_height(font_size)
        return verts
