# GraphicsPipeline: construcción de pipelines de Vulkan a partir de un
# ShaderProgram y un formato de vértices, de forma declarativa.
import vulkan as vk

from opngl.core.vkutil import check, cstr


class VertexFormat:
    """Descripción del layout de un vértice (binding + attributos)."""

    def __init__(self, stride_bytes, attributes):
        # attributes: lista de (location, format, offset)
        self.stride_bytes = stride_bytes
        self.attributes = attributes

    def bindings(self):
        b = vk.VkVertexInputBindingDescription()
        b.binding = 0
        b.stride = self.stride_bytes
        b.inputRate = vk.VK_VERTEX_INPUT_RATE_VERTEX
        return b

    def attribute_descriptions(self):
        out = []
        for location, fmt, offset in self.attributes:
            a = vk.VkVertexInputAttributeDescription()
            a.binding = 0
            a.location = location
            a.format = fmt
            a.offset = offset
            out.append(a)
        return out


class GraphicsPipeline:
    def __init__(self, device, render_pass, shader, vertex_format, descriptor_set_layout,
                 push_range=None, premultiplied=False):
        self.device = device
        self._keep = []
        self.shader = shader

        # -- pipeline layout -----------------------------------------------
        pli = vk.VkPipelineLayoutCreateInfo()
        pli.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
        if descriptor_set_layout is not None:
            dsl_arr = ffi_array_dsl(descriptor_set_layout)
            pli.setLayoutCount = 1
            pli.pSetLayouts = dsl_arr
            self._keep.append(dsl_arr)
        if push_range is not None:
            pr_arr = ffi_array_push(push_range)
            pli.pushConstantRangeCount = 1
            pli.pPushConstantRanges = pr_arr
            self._keep.append(pr_arr)
        self.layout = vk.vkCreatePipelineLayout(device.device, pli, None)

        # -- shader stages -------------------------------------------------
        s1, s2 = shader.stages()
        stages = ffi_new_stages(s1, s2)
        self._keep.append(stages)

        # -- vertex input --------------------------------------------------
        bindings = ffi_new_bindings([vertex_format.bindings()])
        attrs = ffi_new_attrs(vertex_format.attribute_descriptions())
        self._keep += [bindings, attrs]
        via = vk.VkPipelineVertexInputStateCreateInfo()
        via.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
        via.vertexBindingDescriptionCount = 1
        via.pVertexBindingDescriptions = bindings
        via.vertexAttributeDescriptionCount = len(attrs)
        via.pVertexAttributeDescriptions = attrs

        ias = vk.VkPipelineInputAssemblyStateCreateInfo()
        ias.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
        ias.topology = vk.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
        ias.primitiveRestartEnable = vk.VK_FALSE

        vp = vk.VkPipelineViewportStateCreateInfo()
        vp.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO
        vp.viewportCount = 1
        vp.scissorCount = 1

        rs = vk.VkPipelineRasterizationStateCreateInfo()
        rs.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO
        rs.depthClampEnable = vk.VK_FALSE
        rs.rasterizerDiscardEnable = vk.VK_FALSE
        rs.polygonMode = vk.VK_POLYGON_MODE_FILL
        rs.lineWidth = 1.0
        rs.cullMode = vk.VK_CULL_MODE_NONE
        rs.frontFace = vk.VK_FRONT_FACE_COUNTER_CLOCKWISE
        rs.depthBiasEnable = vk.VK_FALSE

        ms = vk.VkPipelineMultisampleStateCreateInfo()
        ms.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO
        ms.rasterizationSamples = vk.VK_SAMPLE_COUNT_1_BIT
        ms.sampleShadingEnable = vk.VK_FALSE

        # blend: alpha correcto para UI.
        #   * normal:        src_alpha / one_minus_src_alpha (texto, formas)
        #   * premultiplied: ONE / ONE_MINUS_SRC_ALPHA (imágenes RGBA: bordes
        #                    de transparencia sin halos)
        blend_att = vk.VkPipelineColorBlendAttachmentState()
        blend_att.blendEnable = vk.VK_TRUE
        if premultiplied:
            blend_att.srcColorBlendFactor = vk.VK_BLEND_FACTOR_ONE
            blend_att.dstColorBlendFactor = vk.VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
            blend_att.srcAlphaBlendFactor = vk.VK_BLEND_FACTOR_ONE
            blend_att.dstAlphaBlendFactor = vk.VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
        else:
            blend_att.srcColorBlendFactor = vk.VK_BLEND_FACTOR_SRC_ALPHA
            blend_att.dstColorBlendFactor = vk.VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
            blend_att.srcAlphaBlendFactor = vk.VK_BLEND_FACTOR_ONE
            blend_att.dstAlphaBlendFactor = vk.VK_BLEND_FACTOR_ZERO
        blend_att.colorBlendOp = vk.VK_BLEND_OP_ADD
        blend_att.alphaBlendOp = vk.VK_BLEND_OP_ADD
        blend_att.colorWriteMask = (vk.VK_COLOR_COMPONENT_R_BIT | vk.VK_COLOR_COMPONENT_G_BIT
                                    | vk.VK_COLOR_COMPONENT_B_BIT | vk.VK_COLOR_COMPONENT_A_BIT)
        blend_arr = ffi_new_blend([blend_att])
        self._keep.append(blend_arr)

        bs = vk.VkPipelineColorBlendStateCreateInfo()
        bs.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO
        bs.logicOpEnable = vk.VK_FALSE
        bs.attachmentCount = 1
        bs.pAttachments = blend_arr

        ds = vk.VkPipelineDepthStencilStateCreateInfo()
        ds.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO
        ds.depthTestEnable = vk.VK_FALSE
        ds.depthWriteEnable = vk.VK_FALSE
        ds.depthCompareOp = vk.VK_COMPARE_OP_LESS
        ds.stencilTestEnable = vk.VK_FALSE

        dyn = vk.VkPipelineDynamicStateCreateInfo()
        dyn.sType = vk.VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO
        dyn_arr = ffi_new_dyn([vk.VK_DYNAMIC_STATE_VIEWPORT, vk.VK_DYNAMIC_STATE_SCISSOR])
        dyn.dynamicStateCount = 2
        dyn.pDynamicStates = dyn_arr
        self._keep.append(dyn_arr)

        gci = vk.VkGraphicsPipelineCreateInfo()
        gci.sType = vk.VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO
        gci.stageCount = 2
        gci.pStages = stages
        gci.pVertexInputState = ffi.addressof(via)
        gci.pInputAssemblyState = ffi.addressof(ias)
        gci.pViewportState = ffi.addressof(vp)
        gci.pRasterizationState = ffi.addressof(rs)
        gci.pMultisampleState = ffi.addressof(ms)
        gci.pDepthStencilState = ffi.addressof(ds)
        gci.pColorBlendState = ffi.addressof(bs)
        gci.pDynamicState = ffi.addressof(dyn)
        gci.layout = self.layout
        gci.renderPass = render_pass
        gci.subpass = 0

        self.pipeline = vk.vkCreateGraphicsPipelines(device.device, ffi.NULL, 1, gci, None)[0]

    def destroy(self):
        if self.device and self.device.device:
            vk.vkDestroyPipeline(self.device.device, self.pipeline, None)
            vk.vkDestroyPipelineLayout(self.device.device, self.layout, None)


# -- constructores cffi (mantener referencias para evitar segfaults) ------
from vulkan import ffi  # noqa: E402


def ffi_array_dsl(handle):
    arr = ffi.new("VkDescriptorSetLayout[]", 1)
    arr[0] = handle
    return arr


def ffi_array_push(push_range):
    arr = ffi.new("VkPushConstantRange[]", 1)
    arr[0] = push_range
    return arr


def ffi_new_stages(s1, s2):
    arr = ffi.new("VkPipelineShaderStageCreateInfo[]", 2)
    arr[0] = s1
    arr[1] = s2
    return arr


def ffi_new_bindings(bindings):
    arr = ffi.new("VkVertexInputBindingDescription[]", len(bindings))
    for i, b in enumerate(bindings):
        arr[i] = b
    return arr


def ffi_new_attrs(attrs):
    arr = ffi.new("VkVertexInputAttributeDescription[]", len(attrs))
    for i, a in enumerate(attrs):
        arr[i] = a
    return arr


def ffi_new_blend(atts):
    arr = ffi.new("VkPipelineColorBlendAttachmentState[]", len(atts))
    for i, a in enumerate(atts):
        arr[i] = a
    return arr


def ffi_new_dyn(states):
    arr = ffi.new("VkDynamicState[]", len(states))
    for i, s in enumerate(states):
        arr[i] = s
    return arr
