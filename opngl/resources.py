# helpers.py: resolución de rutas de recursos (imágenes, sonidos, fuentes).
#
# Un recurso se busca, en este orden:
#   1. Tal cual la ruta dada (absoluta o relativa al directorio de trabajo, CWD).
#   2. Relativa al directorio del SCRIPT lanzado (el .py del usuario, sys.argv[0]):
#      así `app.load_image("logo.png")` encuentra `logo.png` junto al .py aunque
#      se ejecute desde otra carpeta.
#   3. Dentro de `opngl/resources/<subdir>` (recursos del propio motor).
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.join(ROOT, "resources")


def script_dir():
    """Directorio del script principal (sys.argv[0]), o None si no aplica
    (modo interactivo, -c, …)."""
    try:
        argv0 = sys.argv[0] or ""
    except (AttributeError, IndexError):
        return ""
    if not argv0 or argv0 == "-c" or argv0 == "-m":
        return ""
    return os.path.dirname(os.path.abspath(argv0))


def search_locations(path, subdir):
    """Devuelve la lista de rutas candidatas, en orden de búsqueda."""
    locs = [os.path.abspath(path)]
    sd = script_dir()
    if sd and sd not in locs:
        locs.append(os.path.join(sd, path))
    locs.append(os.path.join(RESOURCES_DIR, subdir, path))
    return locs


def resolve(path, subdir):
    """Devuelve la primera ruta de <path> que existe, o None."""
    if path is None:
        return None
    for c in search_locations(path, subdir):
        if os.path.exists(c):
            return os.path.abspath(c)
    return None
