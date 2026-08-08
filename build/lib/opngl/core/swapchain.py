# VulkanSwapchain: cadena de presentación sobre la superficie GLFW.
# Maneja imágenes, image views, profundidad y su recreación en resize.
import vulkan as vk
from vulkan import ffi

from opngl.core.vkutil import check, instfn, devfn

VK_PRESENT_MODE_MAILBOX = 1
VK_PRESENT_MODE_FIFO = 2
VK_PRESENT_MODE_FIFO_RELAXED = 3
VK_COLOR_SPACE_SRGB_NONLINEAR = 0


class VulkanSwapchain:
    def __init__(self, device, window):
        self._keep = []
        self.device = device
        self.window = window
        self.format = None
        self.color_space = None
        self.present_mode = None
        self.extent = None
        self.min_image_count = 2
        self.swapchain = None
        self.images = []
        self.image_views = []
        self.depth_image = None
        self.depth_memory = None
        self.depth_view = None
        self.depth_format = vk.VK_FORMAT_D32_SFLOAT
        self._create()

    # ------------------------------------------------------------------ #
    def _query_surface(self):
        caps_fn = self.device.inst["vkGetPhysicalDeviceSurfaceCapabilitiesKHR"]
        caps = ffi.new("VkSurfaceCapabilitiesKHR*")
        check(caps_fn(self.device.physical, self.device.surface, caps), "surfaceCapabilities")
        return caps[0]

    def _query_formats(self):
        formats_fn = self.device.inst["vkGetPhysicalDeviceSurfaceFormatsKHR"]
        count = ffi.new("uint32_t*")
        check(formats_fn(self.device.physical, self.device.surface, count, ffi.NULL), "surfaceFormats")
        arr = ffi.new("VkSurfaceFormatKHR[]", count[0])
        check(formats_fn(self.device.physical, self.device.surface, count, arr), "surfaceFormats")
        return list(arr)[:count[0]]

    def _query_present_modes(self):
        modes_fn = self.device.inst["vkGetPhysicalDeviceSurfacePresentModesKHR"]
        count = ffi.new("uint32_t*")
        check(modes_fn(self.device.physical, self.device.surface, count, ffi.NULL), "presentModes")
        arr = ffi.new("uint32_t[]", count[0])
        check(modes_fn(self.device.physical, self.device.surface, count, arr), "presentModes")
        return list(arr)[:count[0]]

    # ------------------------------------------------------------------ #
    def _choose_format(self, formats):
        for fmt in formats:
            if (fmt.format == vk.VK_FORMAT_B8G8R8A8_SRGB
                    and fmt.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR):
                return fmt
        for fmt in formats:
            if fmt.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR:
                return fmt
        return formats[0]

    def _choose_present_mode(self, modes):
        if VK_PRESENT_MODE_MAILBOX in modes:
            return VK_PRESENT_MODE_MAILBOX
        if VK_PRESENT_MODE_FIFO in modes:
            return VK_PRESENT_MODE_FIFO
        return modes[0]

    def _choose_extent(self, caps):
        fb_w, fb_h = self.window.framebuffer_size()
        width = max(caps.minImageExtent.width, min(caps.maxImageExtent.width, fb_w))
        height = max(caps.minImageExtent.height, min(caps.maxImageExtent.height, fb_h))
        return width, height

    def _find_depth_format(self):
        candidates = [vk.VK_FORMAT_D32_SFLOAT, vk.VK_FORMAT_D24_UNORM_S8_UINT,
                      vk.VK_FORMAT_D16_UNORM]
        for fmt in candidates:
            props = vk.vkGetPhysicalDeviceFormatProperties(self.device.physical, fmt)
            if props.optimalTilingFeatures & vk.VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT:
                return fmt
        raise RuntimeError("[OpnGL] Sin formato de profundidad Vulkan soportado.")

    # ------------------------------------------------------------------ #
    def _create(self):
        caps = self._query_surface()
        self.format = self._choose_format(self._query_formats())
        self.color_space = self.format.colorSpace
        self.present_mode = self._choose_present_mode(self._query_present_modes())
        width, height = self._choose_extent(caps)
        self.extent = (width, height)
        self.depth_format = self._find_depth_format()

        self.min_image_count = caps.minImageCount + 1
        if caps.maxImageCount > 0:
            self.min_image_count = min(self.min_image_count, caps.maxImageCount)

        swap_ci = vk.VkSwapchainCreateInfoKHR()
        swap_ci.sType = vk.VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR
        swap_ci.surface = self.device.surface
        swap_ci.minImageCount = self.min_image_count
        swap_ci.imageFormat = self.format.format
        swap_ci.imageColorSpace = self.color_space
        swap_ci.imageExtent.width = width
        swap_ci.imageExtent.height = height
        swap_ci.imageArrayLayers = 1
        swap_ci.imageUsage = vk.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
        swap_ci.imageSharingMode = vk.VK_SHARING_MODE_EXCLUSIVE
        swap_ci.preTransform = caps.currentTransform
        swap_ci.compositeAlpha = vk.VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
        swap_ci.presentMode = self.present_mode
        swap_ci.clipped = vk.VK_TRUE
        swap_ci.oldSwapchain = ffi.NULL

        create_fn = self.device.devn["vkCreateSwapchainKHR"]
        out = ffi.new("VkSwapchainKHR*")
        check(create_fn(self.device.device, ffi.addressof(swap_ci), ffi.NULL, out),
              "vkCreateSwapchainKHR")
        self.swapchain = out[0]
        self._keep.append(out)
        self._create_images()
        self._create_image_views()
        self._create_depth()
        print("[OpnGL] Swapchain creada: {}x{} | format={} | present={}".format(
            width, height, self.format.format, self.present_mode))

    def _create_images(self):
        get_fn = self.device.devn["vkGetSwapchainImagesKHR"]
        count = ffi.new("uint32_t*")
        check(get_fn(self.device.device, self.swapchain, count, ffi.NULL), "getSwapchainImages")
        arr = ffi.new("VkImage[]", count[0])
        check(get_fn(self.device.device, self.swapchain, count, arr), "getSwapchainImages")
        self.images = list(arr)[:count[0]]
        self._keep.append(arr)

    def _create_image_views(self):
        for image in self.images:
            iv = vk.VkImageViewCreateInfo()
            iv.sType = vk.VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
            iv.image = image
            iv.viewType = vk.VK_IMAGE_VIEW_TYPE_2D
            iv.format = self.format.format
            iv.components.r = vk.VK_COMPONENT_SWIZZLE_IDENTITY
            iv.components.g = vk.VK_COMPONENT_SWIZZLE_IDENTITY
            iv.components.b = vk.VK_COMPONENT_SWIZZLE_IDENTITY
            iv.components.a = vk.VK_COMPONENT_SWIZZLE_IDENTITY
            iv.subresourceRange.aspectMask = vk.VK_IMAGE_ASPECT_COLOR_BIT
            iv.subresourceRange.baseMipLevel = 0
            iv.subresourceRange.levelCount = 1
            iv.subresourceRange.baseArrayLayer = 0
            iv.subresourceRange.layerCount = 1
            self.image_views.append(vk.vkCreateImageView(self.device.device, iv, None))

    def _create_depth(self):
        w, h = self.extent
        i_ci = vk.VkImageCreateInfo()
        i_ci.sType = vk.VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
        i_ci.imageType = vk.VK_IMAGE_TYPE_2D
        i_ci.format = self.depth_format
        i_ci.extent.width = w
        i_ci.extent.height = h
        i_ci.extent.depth = 1
        i_ci.mipLevels = 1
        i_ci.arrayLayers = 1
        i_ci.samples = vk.VK_SAMPLE_COUNT_1_BIT
        i_ci.tiling = vk.VK_IMAGE_TILING_OPTIMAL
        i_ci.usage = vk.VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT
        i_ci.sharingMode = vk.VK_SHARING_MODE_EXCLUSIVE
        i_ci.initialLayout = vk.VK_IMAGE_LAYOUT_UNDEFINED
        self.depth_image = vk.vkCreateImage(self.device.device, i_ci, None)

        reqs = vk.vkGetImageMemoryRequirements(self.device.device, self.depth_image)
        self.depth_memory = self.device.allocate_memory(
            reqs.size, reqs.memoryTypeBits, vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)
        vk.vkBindImageMemory(self.device.device, self.depth_image, self.depth_memory, 0)

        iv = vk.VkImageViewCreateInfo()
        iv.sType = vk.VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
        iv.image = self.depth_image
        iv.viewType = vk.VK_IMAGE_VIEW_TYPE_2D
        iv.format = self.depth_format
        iv.subresourceRange.aspectMask = vk.VK_IMAGE_ASPECT_DEPTH_BIT
        iv.subresourceRange.levelCount = 1
        iv.subresourceRange.layerCount = 1
        self.depth_view = vk.vkCreateImageView(self.device.device, iv, None)

    # ------------------------------------------------------------------ #
    def recreate(self, renderer):
        """Recrea la swapchain (resize de ventana) y los framebuffers."""
        self.device.wait_idle()
        for v in self.image_views:
            vk.vkDestroyImageView(self.device.device, v, None)
        self.image_views = []
        vk.vkDestroyImageView(self.device.device, self.depth_view, None)
        vk.vkDestroyImage(self.device.device, self.depth_image, None)
        vk.vkFreeMemory(self.device.device, self.depth_memory, None)
        destroy_fn = self.device.devn["vkDestroySwapchainKHR"]
        destroy_fn(self.device.device, self.swapchain, ffi.NULL)
        self._create()
        renderer.rebuild_framebuffers()
        print("[OpnGL] Swapchain recreada tras resize: {}x{}".format(*self.extent))

    # ------------------------------------------------------------------ #
    def destroy(self):
        if self.device and self.device.device:
            for v in self.image_views:
                vk.vkDestroyImageView(self.device.device, v, None)
            self.image_views = []
            if self.depth_view:
                vk.vkDestroyImageView(self.device.device, self.depth_view, None)
            if self.depth_image:
                vk.vkDestroyImage(self.device.device, self.depth_image, None)
            if self.depth_memory:
                vk.vkFreeMemory(self.device.device, self.depth_memory, None)
            if self.swapchain:
                destroy_fn = self.device.devn.get("vkDestroySwapchainKHR")
                if destroy_fn:
                    destroy_fn(self.device.device, self.swapchain, ffi.NULL)
                self.swapchain = None
