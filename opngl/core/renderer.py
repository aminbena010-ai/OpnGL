# Renderer: render pass, pipelines de UI, command buffers, sincronización
# y presentación. Oculta toda la complejidad de Vulkan bajo una API de
# "draw" por frame, estilo OpenGL moderno.
import os
from array import array

import vulkan as vk
from vulkan import ffi

from opngl.core.vkutil import check, VK_ERROR_OUT_OF_DATE_KHR, VK_SUBOPTIMAL_KHR
from opngl.graphics.buffer import DynamicBuffer
from opngl.graphics.fonts import FontManager
from opngl.graphics.images import ImageManager
from opngl.graphics.pipeline import GraphicsPipeline, VertexFormat
from opngl.graphics.shader import ShaderProgram

UINT64_MAX = 0xFFFFFFFFFFFFFFFF
SHADERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shaders")

# Formato de vértice UI: pos(3) + color(4) + uv(2) = 9 floats = 36 bytes
VERTEX_FORMAT = VertexFormat(36, [
    (0, vk.VK_FORMAT_R32G32B32_SFLOAT, 0),
    (1, vk.VK_FORMAT_R32G32B32A32_SFLOAT, 12),
    (2, vk.VK_FORMAT_R32G32_SFLOAT, 28),
])
PUSH_SIZE = 64  # vec2 viewport + vec2 rect + radius + borderWidth + borderColor
                # + fillColor2 (gradiente) + padding  == 60 bytes (redondeado a 64)


class Renderer:
    def __init__(self, device, swapchain, window):
        self.device = device
        self.swapchain = swapchain
        self.window = window
        self._keep = []
        self.clear_color = (0.07, 0.08, 0.12, 1.0)
        self.max_frames = 2
        self.current = 0
        self.current_image = 0
        self.recreate_requested = False
        self._dyn_offset = 0

        self.render_pass = self._create_render_pass()
        self.fonts = FontManager(device)
        self.images = ImageManager(device)
        self._font_sets = {}
        self._image_sets = {}
        self.descriptor_set = self._create_descriptor_set(self.fonts.default.texture)

        self.pipelines = self._create_pipelines()
        self.framebuffers = []
        self.command_pool = device.create_command_pool()
        self.command_buffers = [
            device.allocate_command_buffers(self.command_pool, 1) for _ in range(self.max_frames)
        ]
        self.dyn = DynamicBuffer(device, 8 * 1024 * 1024)
        self._create_sync()
        self.rebuild_framebuffers()
        print("[OpnGL] Renderer Vulkan listo (render pass + pipelines + sync).")

    # ------------------------------------------------------------------ #
    def _create_render_pass(self):
        color = vk.VkAttachmentDescription()
        color.format = self.swapchain.format.format
        color.samples = vk.VK_SAMPLE_COUNT_1_BIT
        color.loadOp = vk.VK_ATTACHMENT_LOAD_OP_CLEAR
        color.storeOp = vk.VK_ATTACHMENT_STORE_OP_STORE
        color.stencilLoadOp = vk.VK_ATTACHMENT_LOAD_OP_DONT_CARE
        color.stencilStoreOp = vk.VK_ATTACHMENT_STORE_OP_DONT_CARE
        color.initialLayout = vk.VK_IMAGE_LAYOUT_UNDEFINED
        color.finalLayout = vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR

        depth = vk.VkAttachmentDescription()
        depth.format = self.swapchain.depth_format
        depth.samples = vk.VK_SAMPLE_COUNT_1_BIT
        depth.loadOp = vk.VK_ATTACHMENT_LOAD_OP_CLEAR
        depth.storeOp = vk.VK_ATTACHMENT_STORE_OP_DONT_CARE
        depth.stencilLoadOp = vk.VK_ATTACHMENT_LOAD_OP_DONT_CARE
        depth.stencilStoreOp = vk.VK_ATTACHMENT_STORE_OP_DONT_CARE
        depth.initialLayout = vk.VK_IMAGE_LAYOUT_UNDEFINED
        depth.finalLayout = vk.VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL

        color_ref = vk.VkAttachmentReference()
        color_ref.attachment = 0
        color_ref.layout = vk.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
        depth_ref = vk.VkAttachmentReference()
        depth_ref.attachment = 1
        depth_ref.layout = vk.VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL

        color_refs = ffi.new("VkAttachmentReference[]", 1)
        color_refs[0] = color_ref
        depth_refs = ffi.new("VkAttachmentReference[]", 1)
        depth_refs[0] = depth_ref

        subpass = vk.VkSubpassDescription()
        subpass.pipelineBindPoint = vk.VK_PIPELINE_BIND_POINT_GRAPHICS
        subpass.colorAttachmentCount = 1
        subpass.pColorAttachments = color_refs
        subpass.pDepthStencilAttachment = depth_refs

        dep = vk.VkSubpassDependency()
        dep.srcSubpass = vk.VK_SUBPASS_EXTERNAL
        dep.dstSubpass = 0
        dep.srcStageMask = vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT
        dep.srcAccessMask = 0
        dep.dstStageMask = vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT
        dep.dstAccessMask = vk.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT

        attachments = ffi.new("VkAttachmentDescription[]", 2)
        attachments[0] = color
        attachments[1] = depth
        subpasses = ffi.new("VkSubpassDescription[]", 1)
        subpasses[0] = subpass
        dependencies = ffi.new("VkSubpassDependency[]", 1)
        dependencies[0] = dep

        rp = vk.VkRenderPassCreateInfo()
        rp.sType = vk.VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO
        rp.attachmentCount = 2
        rp.pAttachments = attachments
        rp.subpassCount = 1
        rp.pSubpasses = subpasses
        rp.dependencyCount = 1
        rp.pDependencies = dependencies

        self._keep += [color_refs, depth_refs, attachments, subpasses, dependencies]
        return vk.vkCreateRenderPass(self.device.device, rp, None)

    # ------------------------------------------------------------------ #
    def _create_descriptor_set(self, texture):
        """Crea el layout + pool (una vez) y el descriptor set de `texture`."""
        if not hasattr(self, "descriptor_set_layout"):
            binding = vk.VkDescriptorSetLayoutBinding()
            binding.binding = 0
            binding.descriptorType = vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
            binding.descriptorCount = 1
            binding.stageFlags = vk.VK_SHADER_STAGE_FRAGMENT_BIT
            binding.pImmutableSamplers = ffi.NULL

            bindings = ffi.new("VkDescriptorSetLayoutBinding[]", 1)
            bindings[0] = binding
            lci = vk.VkDescriptorSetLayoutCreateInfo()
            lci.sType = vk.VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO
            lci.bindingCount = 1
            lci.pBindings = bindings
            self._keep.append(bindings)
            self.descriptor_set_layout = vk.vkCreateDescriptorSetLayout(self.device.device, lci, None)

            pool_size = vk.VkDescriptorPoolSize()
            pool_size.type = vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
            pool_size.descriptorCount = 64
            pool_sizes = ffi.new("VkDescriptorPoolSize[]", 1)
            pool_sizes[0] = pool_size
            pci = vk.VkDescriptorPoolCreateInfo()
            pci.sType = vk.VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO
            pci.maxSets = 64
            pci.poolSizeCount = 1
            pci.pPoolSizes = pool_sizes
            self._keep.append(pool_sizes)
            self.descriptor_pool = vk.vkCreateDescriptorPool(self.device.device, pci, None)

        layout_arr = ffi.new("VkDescriptorSetLayout[]", 1)
        layout_arr[0] = self.descriptor_set_layout
        aci = vk.VkDescriptorSetAllocateInfo()
        aci.sType = vk.VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO
        aci.descriptorPool = self.descriptor_pool
        aci.descriptorSetCount = 1
        aci.pSetLayouts = layout_arr
        descriptor_set = vk.vkAllocateDescriptorSets(self.device.device, aci, None)[0]

        img_info = vk.VkDescriptorImageInfo()
        img_info.sampler = texture.sampler
        img_info.imageView = texture.view
        img_info.imageLayout = vk.VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL

        write = vk.VkWriteDescriptorSet(
            dstSet=descriptor_set,
            dstBinding=0,
            descriptorCount=1,
            descriptorType=vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
            pImageInfo=[img_info])
        vk.vkUpdateDescriptorSets(self.device.device, 1, write, 0, ffi.NULL)
        return descriptor_set

    def descriptor_for(self, family):
        """Devuelve el descriptor set de la fuente <familia>, creándolo si hace falta."""
        family = family or self.fonts.default.family
        ds = self._font_sets.get(family)
        if ds is None:
            ds = self._create_descriptor_set(self.fonts.get(family).texture)
            self._font_sets[family] = ds
        return ds

    def image_descriptor_for(self, name):
        """Devuelve el descriptor set de la imagen <name>, creándolo si hace falta."""
        if name is None:
            return None
        ds = self._image_sets.get(name)
        if ds is None:
            tex = self.images.get(name)
            if tex is None:
                return None
            ds = self._create_descriptor_set(tex)
            self._image_sets[name] = ds
        return ds

    # ------------------------------------------------------------------ #
    def _create_pipelines(self):
        push = vk.VkPushConstantRange()
        push.stageFlags = vk.VK_SHADER_STAGE_VERTEX_BIT | vk.VK_SHADER_STAGE_FRAGMENT_BIT
        push.offset = 0
        push.size = PUSH_SIZE

        pipelines = {}
        for key, frag_name, premult in (
                ("shape", "ui_shape.frag", False),
                ("text", "ui_text.frag", False),
                ("image", "ui_image.frag", True)):
            shader = ShaderProgram(self.device,
                                   os.path.join(SHADERS_DIR, "ui.vert"),
                                   os.path.join(SHADERS_DIR, frag_name))
            pipe = GraphicsPipeline(self.device, self.render_pass, shader, VERTEX_FORMAT,
                                    self.descriptor_set_layout, push,
                                    premultiplied=premult)
            pipelines[key] = pipe
        return pipelines

    # ------------------------------------------------------------------ #
    def rebuild_framebuffers(self):
        for fb in self.framebuffers:
            vk.vkDestroyFramebuffer(self.device.device, fb, None)
        self.framebuffers = []
        w, h = self.swapchain.extent
        for view in self.swapchain.image_views:
            fci = vk.VkFramebufferCreateInfo(
                renderPass=self.render_pass,
                attachmentCount=2,
                pAttachments=[view, self.swapchain.depth_view],
                width=w, height=h, layers=1)
            self.framebuffers.append(vk.vkCreateFramebuffer(self.device.device, fci, None))

    # ------------------------------------------------------------------ #
    def _create_sync(self):
        self.image_available = []
        self.render_finished = []
        self.in_flight = []
        for _ in range(self.max_frames):
            sci = vk.VkSemaphoreCreateInfo(sType=vk.VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO)
            self.image_available.append(vk.vkCreateSemaphore(self.device.device, sci, None))
            self.render_finished.append(vk.vkCreateSemaphore(self.device.device, sci, None))

            fci = vk.VkFenceCreateInfo(sType=vk.VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,
                                       flags=vk.VK_FENCE_CREATE_SIGNALED_BIT)
            self.in_flight.append(vk.vkCreateFence(self.device.device, fci, None))

    # ------------------------------------------------------------------ #
    # Bucle por frame
    # ------------------------------------------------------------------ #
    def begin_frame(self):
        """Adquiere la siguiente imagen y graba el inicio del render pass.
        Devuelve el command buffer o None si hay que recrear la swapchain."""
        fence = self.in_flight[self.current]
        vk.vkWaitForFences(self.device.device, 1, [fence], vk.VK_TRUE, UINT64_MAX)

        acquire = self.device.devn["vkAcquireNextImageKHR"]
        index = ffi.new("uint32_t*")
        res = acquire(self.device.device, self.swapchain.swapchain, UINT64_MAX,
                      self.image_available[self.current], ffi.NULL, index)
        if res == VK_ERROR_OUT_OF_DATE_KHR:
            self.recreate_requested = True
            return None
        if res != vk.VK_SUCCESS:
            check(res, "vkAcquireNextImageKHR")

        vk.vkResetFences(self.device.device, 1, [fence])
        self.current_image = index[0]
        cb = self.command_buffers[self.current]
        self._dyn_offset = 0

        vk.vkResetCommandBuffer(cb, 0)
        bi = vk.VkCommandBufferBeginInfo()
        bi.sType = vk.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
        bi.flags = vk.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
        vk.vkBeginCommandBuffer(cb, bi)
        self._begin_render_pass(cb)
        return cb

    def _begin_render_pass(self, cb):
        w, h = self.swapchain.extent
        clear = ffi.new("VkClearValue[]", 2)
        clear[0].color.float32[0] = self.clear_color[0]
        clear[0].color.float32[1] = self.clear_color[1]
        clear[0].color.float32[2] = self.clear_color[2]
        clear[0].color.float32[3] = self.clear_color[3]
        clear[1].depthStencil.depth = 1.0

        rpi = vk.VkRenderPassBeginInfo()
        rpi.sType = vk.VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO
        rpi.renderPass = self.render_pass
        rpi.framebuffer = self.framebuffers[self.current_image]
        rpi.renderArea.offset.x = 0
        rpi.renderArea.offset.y = 0
        rpi.renderArea.extent.width = w
        rpi.renderArea.extent.height = h
        rpi.clearValueCount = 2
        rpi.pClearValues = clear
        vk.vkCmdBeginRenderPass(cb, rpi, vk.VK_SUBPASS_CONTENTS_INLINE)

        viewport = vk.VkViewport()
        viewport.x = 0.0
        viewport.y = 0.0
        viewport.width = float(w)
        viewport.height = float(h)
        viewport.minDepth = 0.0
        viewport.maxDepth = 1.0
        vp_arr = ffi.new("VkViewport[]", 1)
        vp_arr[0] = viewport
        vk.vkCmdSetViewport(cb, 0, 1, vp_arr)

        scissor = vk.VkRect2D()
        scissor.extent.width = w
        scissor.extent.height = h
        sc_arr = ffi.new("VkRect2D[]", 1)
        sc_arr[0] = scissor
        vk.vkCmdSetScissor(cb, 0, 1, sc_arr)

    def draw(self, cb, vertices, pipeline_key, rect_size=None, radius=0.0,
             border_width=0.0, border_color=None, gradient=None,
             descriptor_set=None):
        """Sube `vertices` (lista de floats) al DynamicBuffer y emite un draw."""
        if not vertices:
            return
        data = array("f", vertices)
        data_bytes = data.tobytes()
        offset = self._dyn_offset
        self.dyn.write(data_bytes, offset)
        self._dyn_offset += len(data_bytes)
        if self._dyn_offset >= self.dyn.capacity:
            raise RuntimeError(
                "[OpnGL] DynamicBuffer de UI desbordado (8 MB). Demasiada geometría por frame.")

        w, h = self.swapchain.extent
        if rect_size is None:
            rect_size = (0.0, 0.0)
        if border_color is None:
            border_color = (0.0, 0.0, 0.0, 0.0)
        if gradient is None:
            gradient = (0.0, 0.0, 0.0, 0.0)
        # Layout std430 del bloque: viewport[0] rectSize[8] radius[16]
        # borderWidth[20] (pad[24]) borderColor[32] fillColor2[48] (pad[64]).
        # Los vec4 obligan a alinear a 16 bytes -> 2 floats de padding.
        push_vals = array("f", [float(w), float(h),
                                float(rect_size[0]), float(rect_size[1]),
                                float(radius), float(border_width),
                                0.0, 0.0,
                                *[float(x) for x in border_color],
                                *[float(x) for x in gradient]])
        push_ptr = ffi.from_buffer("float[]", push_vals)

        pipe = self.pipelines[pipeline_key]
        vk.vkCmdBindPipeline(cb, vk.VK_PIPELINE_BIND_POINT_GRAPHICS, pipe.pipeline)
        vk.vkCmdPushConstants(cb, pipe.layout,
                              vk.VK_SHADER_STAGE_VERTEX_BIT | vk.VK_SHADER_STAGE_FRAGMENT_BIT,
                              0, PUSH_SIZE, push_ptr)
        dsl_arr = ffi.new("VkDescriptorSet[]", 1)
        dsl_arr[0] = descriptor_set if descriptor_set is not None else self.descriptor_set
        vk.vkCmdBindDescriptorSets(cb, vk.VK_PIPELINE_BIND_POINT_GRAPHICS, pipe.layout,
                                   0, 1, dsl_arr, 0, ffi.NULL)
        binding = ffi.new("VkBuffer[]", 1)
        binding[0] = self.dyn.buffer
        off_arr = ffi.new("VkDeviceSize[]", 1)
        off_arr[0] = offset
        vk.vkCmdBindVertexBuffers(cb, 0, 1, binding, off_arr)
        vk.vkCmdDraw(cb, len(vertices) // 9, 1, 0, 0)

    def end_frame(self):
        """Cierra el render pass, envía a la cola y presenta."""
        cb = self.command_buffers[self.current]
        vk.vkCmdEndRenderPass(cb)
        vk.vkEndCommandBuffer(cb)

        si = vk.VkSubmitInfo(
            waitSemaphoreCount=1,
            pWaitSemaphores=[self.image_available[self.current]],
            pWaitDstStageMask=[vk.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT],
            commandBufferCount=1,
            pCommandBuffers=[cb],
            signalSemaphoreCount=1,
            pSignalSemaphores=[self.render_finished[self.current]])
        vk.vkQueueSubmit(self.device.graphics_queue, 1, si, self.in_flight[self.current])

        pi = vk.VkPresentInfoKHR(
            waitSemaphoreCount=1,
            pWaitSemaphores=[self.render_finished[self.current]],
            swapchainCount=1,
            pSwapchains=[self.swapchain.swapchain],
            pImageIndices=[self.current_image])

        present = self.device.devn["vkQueuePresentKHR"]
        result = present(self.device.graphics_queue, ffi.addressof(pi))
        if result in (VK_ERROR_OUT_OF_DATE_KHR, VK_SUBOPTIMAL_KHR):
            self.recreate_requested = True
        elif result != vk.VK_SUCCESS:
            check(result, "vkQueuePresentKHR")

        self.current = (self.current + 1) % self.max_frames

    def handle_recreate(self):
        if self.recreate_requested:
            self.device.wait_idle()
            self.swapchain.recreate(self)
            self.recreate_requested = False

    def readback(self, x=0, y=0, w=None, h=None):
        """Copia la imagen de swapchain actual a bytes RGBA host-visibles (para tests/verificación)."""
        self.device.wait_idle()
        if w is None:
            w, h = self.swapchain.extent
        size = w * h * 4
        buf, mem = self.device.create_buffer(
            size, vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT,
            vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
        image = self.swapchain.images[self.current_image]

        def _barrier(cb, old, new, src_access, dst_access):
            b = vk.VkImageMemoryBarrier()
            b.sType = vk.VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER
            b.oldLayout = old
            b.newLayout = new
            b.srcQueueFamilyIndex = vk.VK_QUEUE_FAMILY_IGNORED
            b.dstQueueFamilyIndex = vk.VK_QUEUE_FAMILY_IGNORED
            b.image = image
            b.subresourceRange.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
            b.subresourceRange.levelCount = 1
            b.subresourceRange.layerCount = 1
            b.srcAccessMask = src_access
            b.dstAccessMask = dst_access
            return b

        def record(cb):
            vk.vkCmdPipelineBarrier(
                cb, vk.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
                0, 0, ffi.NULL, 0, ffi.NULL, 1,
                _barrier(cb, vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
                         vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, 0, vk.VK_ACCESS_TRANSFER_READ_BIT))
            region = vk.VkBufferImageCopy()
            region.imageSubresource.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
            region.imageSubresource.layerCount = 1
            region.imageOffset.x = x
            region.imageOffset.y = y
            region.imageExtent.width = w
            region.imageExtent.height = h
            region.imageExtent.depth = 1
            vk.vkCmdCopyImageToBuffer(cb, image, vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buf, 1, region)
            vk.vkCmdPipelineBarrier(
                cb, vk.VK_PIPELINE_STAGE_TRANSFER_BIT, vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                0, 0, ffi.NULL, 0, ffi.NULL, 1,
                _barrier(cb, vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                         vk.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
                         vk.VK_ACCESS_TRANSFER_READ_BIT, 0))

        self.device.execute_now(record)
        data = self.device.map_memory(mem, size)
        pixels = bytes(data[:size])
        self.device.unmap_memory(mem)
        vk.vkDestroyBuffer(self.device.device, buf, None)
        vk.vkFreeMemory(self.device.device, mem, None)
        return pixels

    # ------------------------------------------------------------------ #
    def destroy(self):
        self.device.wait_idle()
        for fb in self.framebuffers:
            vk.vkDestroyFramebuffer(self.device.device, fb, None)
        self.framebuffers = []
        for pipe in self.pipelines.values():
            pipe.destroy()
        vk.vkDestroyRenderPass(self.device.device, self.render_pass, None)
        for s in self.image_available + self.render_finished:
            vk.vkDestroySemaphore(self.device.device, s, None)
        for f in self.in_flight:
            vk.vkDestroyFence(self.device.device, f, None)
        vk.vkDestroyCommandPool(self.device.device, self.command_pool, None)
        self.dyn.destroy()
        self.fonts.destroy()
        self.images.destroy()
        vk.vkDestroyDescriptorPool(self.device.device, self.descriptor_pool, None)
        vk.vkDestroyDescriptorSetLayout(self.device.device, self.descriptor_set_layout, None)
