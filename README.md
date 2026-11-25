# AI Atelier

Workspace for AI-assisted architectural visualisation: reading floor plans and producing consistent, plan-faithful 3D interior renders.

## Environment setup

Cloud sessions run this setup script (cached after the first run):

```bash
#!/bin/bash
python3 --version
pip install --break-system-packages shapely matplotlib pypdf pillow numpy bpy || echo "bpy needs Python 3.13"
python3 -c "import shapely, matplotlib, pypdf, PIL, numpy, bpy; print('imports ok')"
```

| Package | Purpose |
|---|---|
| shapely | Wall, room and opening geometry from the plan |
| matplotlib | Plan previews and checks |
| pypdf | Reading floor-plan PDFs |
| pillow | Image handling |
| numpy | Numerics |
| bpy | Blender as a Python module: modelling and rendering (needs Python 3.13) |
