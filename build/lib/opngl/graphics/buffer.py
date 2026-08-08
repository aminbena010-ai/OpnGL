# Buffers Vulkan simplificados (Vertex / Index / Dinámicos).
# El usuario solo ve listas de python; el copy a VRAM es automático.
import vulkan as vk

from opngl.core.vkutil import check


class VertexBuffer:
    """Buffer de vértices device-local subido mediante staging."""

    def __init__(self, device, vertices, usage=vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT):
        import array
        self.device = device
        if not isinstance(vertices, array.array):
            flat = []
            for v in vertices:
                if isinstance(v, (list, tuple)):
                    flat.extend(v)
                else:
                    flat.append(v)
            vertices = array.array("f", flat)
        self._data = vertices
        self.size = len(self._data) * 4
        self.vertex_count = len(self._data) // 3
        self.buffer, self.memory = device.upload_buffer(self._data, usage)
        print("[OpnGL] VertexBuffer: {} vértices ({} bytes) subido a VRAM.".format(
            self.vertex_count, self.size))

    def destroy(self):
        vk.vkDestroyBuffer(self.device.device, self.buffer, None)
        vk.vkFreeMemory(self.device.device, self.memory, None)


class IndexBuffer:
    """Buffer de índices device-local."""

    def __init__(self, device, indices):
        import array
        self.device = device
        self._data = array.array("I", indices)
        self.size = len(self._data) * 4
        self.index_count = len(self._data)
        self.buffer, self.memory = device.upload_buffer(self._data, vk.VK_BUFFER_USAGE_INDEX_BUFFER_BIT)
        print("[OpnGL] IndexBuffer: {} índices.".format(self.index_count))

    def destroy(self):
        vk.vkDestroyBuffer(self.device.device, self.buffer, None)
        vk.vkFreeMemory(self.device.device, self.memory, None)


class DynamicBuffer:
    """Buffer host-visible/coherente que se reescribe cada frame.

    Perfecto para la UI: los vértices se regeneran en CPU por frame y se
    suben sin fricción (VK_MEMORY_PROPERTY_HOST_VISIBLE |
    HOST_COHERENT) a la VRAM visible por la GPU.
    """

    def __init__(self, device, capacity_bytes):
        self.device = device
        self.capacity = capacity_bytes
        self.buffer, self.memory = device.create_buffer(
            capacity_bytes,
            vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
        self._mapped = device.map_memory(self.memory, capacity_bytes)
        print("[OpnGL] DynamicBuffer: {} bytes host-visible.".format(capacity_bytes))

    def write(self, data_bytes, offset=0):
        n = len(data_bytes)
        if offset + n > self.capacity:
            raise RuntimeError("[OpnGL] DynamicBuffer desbordado ({} + {} > {}).".format(
                offset, n, self.capacity))
        self._mapped[offset:offset + n] = data_bytes

    def destroy(self):
        if self.device and self.device.device:
            self.device.unmap_memory(self.memory)
            vk.vkDestroyBuffer(self.device.device, self.buffer, None)
            vk.vkFreeMemory(self.device.device, self.memory, None)
