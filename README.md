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

## Uso

Cada "escena" es una carpeta con los vídeos/fotos de una zona de la casa. Todos los pasos
se ejecutan dentro del contenedor con `./scripts/run.sh` desde la raíz del proyecto.

```bash
# 0. Copiar los vídeos/fotos a data/raw/<escena>/
#    (o subirlos desde el móvil por la red local; se guardan en data/raw/<escena>/)
python3 scripts/upload_server.py <escena> 8000     # abrir http://<ip-del-ordenador>:8000/ en el móvil

# 1. Fotogramas (2 fps, lado largo máx. 1920 px)
./scripts/run.sh scripts/01_frames.sh <escena> [fps] [ancho_max]

# 2. Reconstrucción COLMAP: cámaras + nube densa (data/work/<escena>/dense/fused.ply)
./scripts/run.sh scripts/02_colmap.sh <escena> [--no-dense] [--global]

# 3. Gaussian Splatting -> output/<escena>/splat.ply
./scripts/run.sh scripts/03_splat.sh <escena> [pasos]

# 4. Nivelar, orientar y escalar a metros (necesita data/work/<escena>/refs.json, ver abajo)
./scripts/run.sh python scripts/04_align.py <escena>

# 5. Plano 2D -> output/<escena>/plano.dxf, plano.svg, plano.png, muros.json
./scripts/run.sh python scripts/05_plan.py <escena>

# Opcional: splat compacto en metros para visores web (.splat) y recursos rasterizados
./scripts/run.sh python scripts/splat_export.py <escena> [max_gaussianas]
./scripts/run.sh python scripts/make_report_assets.py <escena>
./scripts/run.sh python scripts/make_plan_assets.py <escena>
```

### Escala real (`refs.json`)

COLMAP no conoce la escala. Hay que medir con cinta al menos una cosa visible en el vídeo
(p. ej. la altura del marco de una puerta) y marcar ese punto en dos o más imágenes de
`data/work/<escena>/dense/images/` (coordenadas en píxeles, se pueden leer con GIMP):

```json
{
  "points": {
    "puerta_sup_der": {"<video>/00012.jpg": [640, 210], "<video>/00015.jpg": [702, 198]}
  },
  "heights":   [{"point": "puerta_sup_der", "m": 2.10}],
  "distances": [{"a": "p1", "b": "p2", "m": 0.80}]
}
```

Con varias medidas se usa la mediana y se muestra la dispersión entre ellas.

### Ver los resultados

- `plano.dxf`: LibreCAD / QCAD / FreeCAD (unidades en metros, capas MUROS, COTAS, PUNTOS, ESCALA)
- `plano.svg`: Inkscape o el navegador
- `nube.ply`: CloudCompare / MeshLab
- `splat.ply` / `.splat`: [SuperSplat](https://superspl.at/editor) o el visor de gsplat

### Consejos para grabar

- Moverse despacio, con el móvil derecho y sin girar sobre uno mismo en el sitio.
- Buena luz y mucho solape entre fotogramas; recorrer las paredes y las esquinas.
- Evitar espejos, ventanas a contraluz y paredes lisas sin textura.
