#!/bin/bash
# Setup script for the AI Atelier environment (cached after the first run)
python3 --version
pip install --break-system-packages shapely matplotlib pypdf pillow numpy bpy || echo "bpy needs Python 3.13 - see page note"
python3 -c "import shapely, matplotlib, pypdf, PIL, numpy, bpy; print('imports ok')"
