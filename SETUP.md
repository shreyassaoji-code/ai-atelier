# Setup

## Python to use

```
/usr/local/bin/python3
```

Python 3.13.18, the system interpreter. It is also on PATH as `python3` and `python`, so bare `python` works. bpy needs Python 3.13, which this already is, so no virtual environment was created.

## Packages

Installed with `pip install --break-system-packages shapely matplotlib pypdf pillow numpy bpy`:

| Package | Version |
|---|---|
| shapely | 2.2.0 |
| matplotlib | 3.11.2 |
| pypdf | 6.17.0 |
| pillow | 12.3.0 |
| numpy | 2.5.3 |
| bpy | 5.3.0 |

Check:

```bash
python -c "import shapely, matplotlib, pypdf, PIL, numpy, bpy"
```

Note: the unpinned install gives bpy 5.3.0, not 5.2.3. To pin it, use `pip install --break-system-packages bpy==5.2.3`.

Recorded 2026-11-25. See `setup.sh` for the environment setup script.
