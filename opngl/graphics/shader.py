# ShaderProgram: carga shaders GLSL desde disco, los compila a SPIR-V
# con glslangValidator y crea los VkShaderModule de Vulkan.
import os

import vulkan as vk

from opngl.core.vkutil import spv_compile, spv_create_module

_VERT_STAGE = vk.VK_SHADER_STAGE_VERTEX_BIT
_FRAG_STAGE = vk.VK_SHADER_STAGE_FRAGMENT_BIT

STAGE_EXTS = {_VERT_STAGE: "vert", _FRAG_STAGE: "frag"}


class ShaderProgram:
    """Agrupa un vertex + fragment shader ya compilado a SPIR-V."""

    def __init__(self, device, vertex_path, fragment_path):
        self.device = device
        self.vertex_path = vertex_path
        self.fragment_path = fragment_path
        self._keep = []
        self.vertex_module = self._load_stage(vertex_path, _VERT_STAGE)
        self.fragment_module = self._load_stage(fragment_path, _FRAG_STAGE)
        print("[OpnGL] ShaderProgram -> {} + {}".format(
            os.path.basename(vertex_path), os.path.basename(fragment_path)))

    def _read_source(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _load_stage(self, path, stage):
        source = self._read_source(path)
        kind = STAGE_EXTS[stage]
        spv = spv_compile(source, kind, kind)
        module, keep = spv_create_module(self.device.device, spv)
        self._keep += keep
        return module

    def stages(self, entry="main"):
        s1 = vk.VkPipelineShaderStageCreateInfo(
            stage=_VERT_STAGE, module=self.vertex_module, pName=entry)
        s2 = vk.VkPipelineShaderStageCreateInfo(
            stage=_FRAG_STAGE, module=self.fragment_module, pName=entry)
        return s1, s2

    def destroy(self):
        if self.device and self.device.device:
            vk.vkDestroyShaderModule(self.device.device, self.vertex_module, None)
            vk.vkDestroyShaderModule(self.device.device, self.fragment_module, None)
