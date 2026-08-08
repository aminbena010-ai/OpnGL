# Utilidades de bajo nivel para Vulkan (OpnGL)
#
# IMPORTANTE: el paquete `vulkan` (realitix) solo expone las 216 funciones
# "core" de Vulkan. Las extensiones VK_KHR (swapchain, presentación, queries
# de superficie) se cargan dinámicamente desde libvulkan.so.1 mediante
# vkGetInstanceProcAddr / vkGetDeviceProcAddr, reutilizando los tipos cffi
# que el paquete ya declara.
import os
import subprocess
import tempfile

import vulkan as vk
from vulkan import ffi

VK_SUCCESS = 0
VK_ERROR_OUT_OF_DATE_KHR = -1000001004
VK_SUBOPTIMAL_KHR = 1000001003

_lib = None


def lib():
    """Devuelve el handle dlopen sobre libvulkan (se comparte en todo el motor)."""
    global _lib
    if _lib is None:
        _lib = ffi.dlopen("libvulkan.so.1")
    return _lib


def cstr(s):
    """Convierte un str python en un char[] de cffi (recordar mantenerlo vivo)."""
    return ffi.new("char[]", s.encode("utf-8"))


def check(result, what=""):
    """Lanza una excepción si el resultado Vulkan no es VK_SUCCESS."""
    if result != vk.VK_SUCCESS:
        raise RuntimeError("[OpnGL] Fallo Vulkan ({}) código={}".format(what, result))
    return result


def devfn(device, name, signature):
    """Carga una función de extensión de nivel device desde libvulkan."""
    pfn = lib().vkGetDeviceProcAddr(device, cstr(name))
    if not pfn:
        raise RuntimeError("[OpnGL] No se pudo resolver la función: " + name)
    return ffi.cast(signature, pfn)


def instfn(instance, name, signature):
    """Carga una función de extensión de nivel instance desde libvulkan."""
    pfn = lib().vkGetInstanceProcAddr(instance, cstr(name))
    if not pfn:
        raise RuntimeError("[OpnGL] No se pudo resolver la función: " + name)
    return ffi.cast(signature, pfn)


def spv_compile(glsl_source, stage, shader_kind="vert"):
    """Compila GLSL a SPIR-V usando glslangValidator.

    stage: 'vert' | 'frag'
    Devuelve un bytearray con el SPIR-V (múltiplo de 4 bytes).
    """
    ext = {shader_kind: shader_kind}.get(shader_kind, shader_kind)
    with tempfile.TemporaryDirectory(prefix="opngl_shader_") as tmp:
        src_path = os.path.join(tmp, "shader." + ext)
        spv_path = os.path.join(tmp, "shader.spv")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(glsl_source)
        cmd = ["glslangValidator", "-V", src_path, "-o", spv_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(spv_path):
            raise RuntimeError(
                "[OpnGL] Error compilando shader GLSL->SPIR-V ({})\n{}".format(stage, proc.stderr)
            )
        with open(spv_path, "rb") as f:
            data = bytearray(f.read())
    pad = len(data) % 4
    if pad:
        data.extend(b"\x00" * (4 - pad))
    return data


def spv_create_module(device, spv_bytes):
    """Crea un VkShaderModule a partir de bytes SPIR-V."""
    buf = bytearray(spv_bytes)
    code_ptr = ffi.from_buffer("uint32_t[]", buf)
    ci = vk.VkShaderModuleCreateInfo()
    ci.sType = vk.VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
    ci.codeSize = len(buf)
    ci.pCode = code_ptr
    module = vk.vkCreateShaderModule(device, ci, None)
    return module, [code_ptr]


def _srgb_to_linear(c):
    """Convierte un canal sRGB (0..1) a lineal. La swapchain es VK_FORMAT_*_SRGB,
    que aplica la conversión lineal->sRGB al escribir; los colores UI vienen en
    hex sRGB, así que se pasan a lineal para no aplicar la gamma dos veces."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def hex_color_to_rgba(value, alpha=1.0):
    """Convierte '#rrggbb' o '#rrggbbaa' en (r, g, b, a) en espacio lineal."""
    s = value.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 6:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return (_srgb_to_linear(r / 255.0), _srgb_to_linear(g / 255.0),
                _srgb_to_linear(b / 255.0), alpha)
    if len(s) == 8:
        r, g, b, a = (int(s[i:i + 2], 16) for i in (0, 2, 4, 6))
        return (_srgb_to_linear(r / 255.0), _srgb_to_linear(g / 255.0),
                _srgb_to_linear(b / 255.0), a / 255.0)
    raise ValueError("[OpnGL] Color inválido: " + value)
