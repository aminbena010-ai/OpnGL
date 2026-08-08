<div align="center">

![Texto alternativo de la imagen](assets/logo.png)

**Motor gráfico sobre Vulkan puro, escrito en Python.**

![Vulkan](https://img.shields.io/badge/Vulkan-1.0-purple)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Licencia](https://img.shields.io/badge/Licencia-MIT%20%2B%20BluePanda-brightgreen)

<sub>Proyecto de [BluePanda](https://github.com/aminbena010-ai) — ver [Licencia](#licencia).</sub>

</div>

---

## Instalación

Requiere Python **3.9+**, drivers de **Vulkan** (`libvulkan.so.1`) y
`glslangValidator` en el `PATH`.

```bash
pip install opngl                       # sonido opcional: pip install "opngl[audio]"
```

Para instalarlo desde este repositorio:

```bash
git clone https://github.com/aminbena010-ai/OpnGL.git
cd OpnGL
pip install .
```

---

## Uso mínimo

```python
from opngl import App

app = App(title="Mi App")
app.label(text="Motor OpnGL activo (Vulkan puro)", font_size=22)
app.button(text="Cerrar", id="btn_close")
app.on_click("btn_close", lambda b: app.quit())
app.run()
```

También puedes definir la UI declarativamente desde XML: `App("ui.xml")`.
Demo integrada: `python -m opngl` o el comando `opngl`.

---

## Licencia

**OpnGL** se distribuye bajo la **Licencia MIT con cláusula de atribución a
BluePanda**. Texto completo en [`LICENSE`](LICENSE).

```text
Copyright (c) 2026 BluePanda
```
