# VulkanDevice: instancia Vulkan, superficie GLFW, dispositivo físico/lógico
# y colas. OpnGL usa estrictamente Vulkan: GLFW crea solo la ventana y la
# superficie VkSurfaceKHR; no existe ningún contexto OpenGL.
import glfw
import vulkan as vk
from vulkan import ffi

from opngl.core import vkutil
from opngl.core.vkutil import check, cstr, instfn

# Firmas cffi de las funciones de extensión de nivel instance
_INST_KHR = {
    "vkGetPhysicalDeviceSurfaceSupportKHR":
        "VkResult (*)(VkPhysicalDevice, uint32_t, VkSurfaceKHR, VkBool32*)",
    "vkGetPhysicalDeviceSurfaceCapabilitiesKHR":
        "VkResult (*)(VkPhysicalDevice, VkSurfaceKHR, VkSurfaceCapabilitiesKHR*)",
    "vkGetPhysicalDeviceSurfaceFormatsKHR":
        "VkResult (*)(VkPhysicalDevice, VkSurfaceKHR, uint32_t*, VkSurfaceFormatKHR*)",
    "vkGetPhysicalDeviceSurfacePresentModesKHR":
        "VkResult (*)(VkPhysicalDevice, VkSurfaceKHR, uint32_t*, uint32_t*)",
}

_DEV_KHR = {
    "vkCreateSwapchainKHR":
        "VkResult (*)(VkDevice, const VkSwapchainCreateInfoKHR*, const VkAllocationCallbacks*, VkSwapchainKHR*)",
    "vkDestroySwapchainKHR":
        "void (*)(VkDevice, VkSwapchainKHR, const VkAllocationCallbacks*)",
    "vkGetSwapchainImagesKHR":
        "VkResult (*)(VkDevice, VkSwapchainKHR, uint32_t*, VkImage*)",
    "vkAcquireNextImageKHR":
        "VkResult (*)(VkDevice, VkSwapchainKHR, uint64_t, VkSemaphore, VkFence, uint32_t*)",
    "vkQueuePresentKHR":
        "VkResult (*)(VkQueue, const VkPresentInfoKHR*)",
}


class VulkanDevice:
    def __init__(self, window, enable_validation=False):
        self._keep = []          # punteros cffi que deben permanecer vivos
        self.window = window
        self.enable_validation = enable_validation
        self.instance = None
        self.surface = None
        self.physical = None
        self.physical_props = None
        self.memory_props = None
        self.device = None
        self.graphics_queue = None
        self.present_queue = None
        self.queue_family = 0
        self.inst = {}           # funciones KHR de nivel instance
        self.devn = {}           # funciones KHR de nivel device
        self._init()

    # ------------------------------------------------------------------ #
    def _init(self):
        self._create_instance()
        self._create_surface()
        self._pick_physical_device()
        self._load_instance_functions()
        self._create_logical_device()
        self._load_device_functions()
        self._get_queues()
        print("[OpnGL] VulkanDevice listo -> {}".format(self.physical_props.deviceName))

    # ------------------------------------------------------------------ #
    def _create_instance(self):
        if not glfw.vulkan_supported():
            raise RuntimeError("[OpnGL] GLFW no detectó el loader de Vulkan.")

        exts = list(glfw.get_required_instance_extensions())
        if self.enable_validation:
            if "VK_EXT_debug_utils" not in exts:
                exts.append("VK_EXT_debug_utils")

        app = vk.VkApplicationInfo()
        app.sType = vk.VK_STRUCTURE_TYPE_APPLICATION_INFO
        app.pApplicationName = cstr("OpnGL")
        app.applicationVersion = vk.VK_MAKE_VERSION(1, 0, 0)
        app.pEngineName = cstr("OpnGL")
        app.engineVersion = vk.VK_MAKE_VERSION(1, 0, 0)
        app.apiVersion = vk.VK_API_VERSION_1_0
        app_ptr = ffi.new("VkApplicationInfo*", app)
        self._keep.append(app_ptr)

        ext_names = [cstr(e) for e in exts]
        ext_array = ffi.new("char*[]", ext_names)
        self._keep += ext_names + [ext_array]

        ci = vk.VkInstanceCreateInfo()
        ci.sType = vk.VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
        ci.pApplicationInfo = app_ptr
        ci.enabledExtensionCount = len(exts)
        ci.ppEnabledExtensionNames = ext_array

        self.instance = vk.vkCreateInstance(ci, None)

    # ------------------------------------------------------------------ #
    def _create_surface(self):
        surface_out = ffi.new("VkSurfaceKHR*")
        result = glfw.create_window_surface(self.instance, self.window.window, None, surface_out)
        check(result, "glfwCreateWindowSurface")
        self.surface = surface_out[0]
        self._keep.append(surface_out)
        print("[OpnGL] Superficie Vulkan (VkSurfaceKHR) creada desde GLFW (NO_API).")

    # ------------------------------------------------------------------ #
    def _pick_physical_device(self):
        surf_support = instfn(self.instance, "vkGetPhysicalDeviceSurfaceSupportKHR",
                              _INST_KHR["vkGetPhysicalDeviceSurfaceSupportKHR"])
        supported = vk.vkEnumeratePhysicalDevices(self.instance)
        if not supported:
            raise RuntimeError("[OpnGL] No se encontró ningún dispositivo Vulkan.")

        best = None
        best_score = -1
        for phys in supported:
            props = vk.vkGetPhysicalDeviceProperties(phys)
            qfs = vk.vkGetPhysicalDeviceQueueFamilyProperties(phys)
            family = None
            for i, qf in enumerate(qfs):
                has_graphics = bool(qf.queueFlags & vk.VK_QUEUE_GRAPHICS_BIT)
                present_ok = ffi.new("VkBool32*")
                res = surf_support(phys, i, self.surface, present_ok)
                if res != vk.VK_SUCCESS:
                    continue
                if has_graphics and present_ok[0]:
                    family = i
                    break
            if family is None:
                continue
            score = 1000 if props.deviceType == vk.VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU else (
                800 if props.deviceType == vk.VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU else 100)
            if score > best_score:
                best_score = score
                best = (phys, family, props)

        if best is None:
            raise RuntimeError("[OpnGL] Ningún dispositivo Vulkan soporta gráficos + presentación.")
        self.physical, self.queue_family, self.physical_props = best
        self.memory_props = vk.vkGetPhysicalDeviceMemoryProperties(self.physical)
        print("[OpnGL] Dispositivo físico elegido: {} (queue family {})".format(
            self.physical_props.deviceName, self.queue_family))

    # ------------------------------------------------------------------ #
    def _load_instance_functions(self):
        for name, sig in _INST_KHR.items():
            self.inst[name] = instfn(self.instance, name, sig)

    def _load_device_functions(self):
        for name, sig in _DEV_KHR.items():
            self.devn[name] = vkutil.devfn(self.device, name, sig)

    # ------------------------------------------------------------------ #
    def _create_logical_device(self):
        priorities = ffi.new("float[]", [1.0])
        self._keep.append(priorities)

        qci = vk.VkDeviceQueueCreateInfo()
        qci.sType = vk.VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO
        qci.queueFamilyIndex = self.queue_family
        qci.queueCount = 1
        qci.pQueuePriorities = priorities
        qci_array = ffi.new("VkDeviceQueueCreateInfo[]", 1)
        qci_array[0] = qci
        self._keep.append(qci_array)

        dev_ext = ["VK_KHR_swapchain"]
        dev_names = [cstr(e) for e in dev_ext]
        dev_array = ffi.new("char*[]", dev_names)
        self._keep += dev_names + [dev_array]

        dci = vk.VkDeviceCreateInfo()
        dci.sType = vk.VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO
        dci.queueCreateInfoCount = 1
        dci.pQueueCreateInfos = qci_array
        dci.enabledExtensionCount = len(dev_ext)
        dci.ppEnabledExtensionNames = dev_array

        self.device = vk.vkCreateDevice(self.physical, dci, None)

    # ------------------------------------------------------------------ #
    def _get_queues(self):
        self.graphics_queue = vk.vkGetDeviceQueue(self.device, self.queue_family, 0)
        self.present_queue = self.graphics_queue  # única cola para gráficos + presentación

    # ------------------------------------------------------------------ #
    # Helpers de memoria / buffers (bajo el capó, ocultos al usuario)    #
    # ------------------------------------------------------------------ #
    def find_memory_type(self, type_filter, required_flags):
        types = self.memory_props.memoryTypes
        for i, mt in enumerate(types):
            if type_filter & (1 << i) and (mt.propertyFlags & required_flags) == required_flags:
                return i
        raise RuntimeError("[OpnGL] No se encontró un tipo de memoria Vulkan adecuado.")

    def allocate_memory(self, size, type_filter, required_flags):
        index = self.find_memory_type(type_filter, required_flags)
        aci = vk.VkMemoryAllocateInfo()
        aci.sType = vk.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
        aci.allocationSize = size
        aci.memoryTypeIndex = index
        return vk.vkAllocateMemory(self.device, aci, None)

    def create_buffer(self, size, usage, required_flags):
        bci = vk.VkBufferCreateInfo()
        bci.sType = vk.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO
        bci.size = size
        bci.usage = usage
        bci.sharingMode = vk.VK_SHARING_MODE_EXCLUSIVE
        buf = vk.vkCreateBuffer(self.device, bci, None)
        reqs = vk.vkGetBufferMemoryRequirements(self.device, buf)
        memory = self.allocate_memory(reqs.size, reqs.memoryTypeBits, required_flags)
        vk.vkBindBufferMemory(self.device, buf, memory, 0)
        return buf, memory

    def map_memory(self, memory, size):
        return vk.vkMapMemory(self.device, memory, 0, size, 0)

    def unmap_memory(self, memory):
        vk.vkUnmapMemory(self.device, memory)

    def execute_now(self, record):
        """Ejecuta `record(command_buffer)` en un submit de un solo uso."""
        pool = self.create_command_pool()
        cb = self.allocate_command_buffers(pool, 1)

        bi = vk.VkCommandBufferBeginInfo()
        bi.sType = vk.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
        bi.flags = vk.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
        vk.vkBeginCommandBuffer(cb, bi)
        record(cb)
        vk.vkEndCommandBuffer(cb)

        si = vk.VkSubmitInfo(commandBufferCount=1, pCommandBuffers=[cb])
        vk.vkQueueSubmit(self.graphics_queue, 1, si, ffi.NULL)
        vk.vkQueueWaitIdle(self.graphics_queue)

        vk.vkFreeCommandBuffers(self.device, pool, 1, [cb])
        vk.vkDestroyCommandPool(self.device, pool, None)

    def create_command_pool(self):
        cpi = vk.VkCommandPoolCreateInfo()
        cpi.sType = vk.VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO
        cpi.flags = vk.VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT
        cpi.queueFamilyIndex = self.queue_family
        return vk.vkCreateCommandPool(self.device, cpi, None)

    def allocate_command_buffers(self, pool, count):
        aci = vk.VkCommandBufferAllocateInfo(
            commandPool=pool,
            level=vk.VK_COMMAND_BUFFER_LEVEL_PRIMARY,
            commandBufferCount=count)
        return vk.vkAllocateCommandBuffers(self.device, aci, None)[0]

    def upload_buffer(self, data_bytes, usage):
        """Crea un buffer device-local copiando `data_bytes` vía staging."""
        if not isinstance(data_bytes, (bytes, bytearray)):
            data_bytes = bytes(data_bytes)
        size = len(data_bytes)
        staging, staging_mem = self.create_buffer(
            size, vk.VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
        data = self.map_memory(staging_mem, size)
        data[:size] = data_bytes
        self.unmap_memory(staging_mem)

        device_local, mem = self.create_buffer(
            size, usage | vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT,
            vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)

        def record(cb):
            region = vk.VkBufferCopy()
            region.srcOffset = 0
            region.dstOffset = 0
            region.size = size
            vk.vkCmdCopyBuffer(cb, staging, device_local, 1, region)

        self.execute_now(record)
        vk.vkDestroyBuffer(self.device, staging, None)
        vk.vkFreeMemory(self.device, staging_mem, None)
        return device_local, mem

    # ------------------------------------------------------------------ #
    def wait_idle(self):
        vk.vkDeviceWaitIdle(self.device)

    def destroy(self):
        if self.device:
            vk.vkDestroyDevice(self.device, None)
            self.device = None
        if self.surface:
            # vkDestroySurfaceKHR es de nivel instance:
            try:
                fn = vkutil.instfn(self.instance, "vkDestroySurfaceKHR",
                                   "void (*)(VkInstance, VkSurfaceKHR, const VkAllocationCallbacks*)")
                fn(self.instance, self.surface, ffi.NULL)
            except Exception:
                pass
            self.surface = None
        if self.instance:
            vk.vkDestroyInstance(self.instance, None)
            self.instance = None
