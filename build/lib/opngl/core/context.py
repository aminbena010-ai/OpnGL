# Contexto y Máquina de estados global estilo OpenGL
class OpnGLContext:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpnGLContext, cls).__new__(cls)
            cls._instance.current_shader = None
        return cls._instance

    def clear_color(self, r, g, b, a):
        # Lógica para limpiar el framebuffer de Vulkan
        pass
