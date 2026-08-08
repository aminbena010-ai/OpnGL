# Layout: aplica medición + posicionamiento al árbol de widgets
# en función del tamaño de la ventana.
def apply_layout(root, window_width, window_height):
    """Mide y posiciona el árbol desde el widget raíz."""
    root.width = window_width
    root.height = window_height
    root.measure(window_width, window_height)
    root.layout(0, 0)
    return root
