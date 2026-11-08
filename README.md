# mapa-casa

Pipeline 100 % de software libre para pasar de vídeos y fotos de una casa a:

1. **Plano 2D medible** (DXF/SVG), que se abre en LibreCAD o Inkscape.
2. **Modelo 3D inmersivo** tipo "Street View" (Gaussian Splatting, `.ply`), que se ve en SuperSplat o en el visor de gsplat.
3. **Malla 3D** con textura, que se abre en MeshLab, CloudCompare o Blender.

## Pipeline

```
vídeos/fotos ──FFmpeg──► fotogramas ──COLMAP──► cámaras + nube densa
                                         │
                                         ├──gsplat──► splat .ply (visita inmersiva)
                                         └──Open3D──► corte horizontal ──► plano DXF/SVG
```

| Paso | Herramienta | Licencia |
|---|---|---|
| Fotogramas | FFmpeg | LGPL/GPL |
| Reconstrucción | COLMAP 4.2.1 | BSD |
| Gaussian Splatting | gsplat | Apache-2.0 |
| Plano 2D | Open3D + shapely + ezdxf (scripts propios) | MIT/BSD |
| Ver/editar | CloudCompare, MeshLab, LibreCAD, Inkscape, Blender, SuperSplat | GPL/MIT |

Nota: la aceleración por GPU usa CUDA y el driver de NVIDIA, que son propietarios.

## Estructura

- `container/`: Containerfile con todo el entorno (COLMAP, gsplat, Open3D)
- `scripts/`: scripts del pipeline
- `data/raw/`: vídeos y fotos originales (no van a git)
- `data/work/`: resultados intermedios
- `output/`: planos y modelos finales

## Instalación (Fedora 43)

```bash
# 1. Herramientas de escritorio y soporte de GPU para podman
sudo dnf install -y cloudcompare meshlab librecad inkscape f3d blender \
    golang-github-nvidia-container-toolkit uv
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# 2. Construir la imagen (sin sudo, entre 30 y 60 min)
podman build -t mapa-casa -f container/Containerfile container/

# 3. Comprobar
./scripts/run.sh nvidia-smi
./scripts/run.sh colmap -h
```
