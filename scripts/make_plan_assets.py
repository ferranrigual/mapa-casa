#!/usr/bin/env python3
"""Rasteriza el plano 2D para el visor web (escala exacta, para medir).

Salida en output/<escena>/report/:
  plan_ortho.jpg  vista cenital en color (lo más alto de cada celda, sin techo)
  plan_cut.png    corte horizontal: puntos entre 0,9 y 1,6 m en oscuro, fondo transparente
  plan_meta.json  origen y resolución: x = x0 + col*res ; y = y1 - fila*res ; paredes detectadas
Uso (en el contenedor): python scripts/make_plan_assets.py <escena> [res_m]
"""
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image
from scipy import ndimage

scene = sys.argv[1]
res = float(sys.argv[2]) if len(sys.argv) > 2 else 0.005
out = Path("output") / scene
rep = out / "report"
meta_w = json.loads((out / "muros.json").read_text())
ceil = meta_w["ceiling"]

pcd = o3d.io.read_point_cloud(str(out / "nube.ply"))
pcd, _ = pcd.remove_statistical_outlier(20, 2.0)
P, C = np.asarray(pcd.points), np.asarray(pcd.colors)
m = (P[:, 2] > -0.05) & (P[:, 2] < ceil - 0.25)
P, C = P[m], C[m]

pad = 0.3
x0, y0 = np.percentile(P[:, 0], 0.5) - pad, np.percentile(P[:, 1], 0.5) - pad
x1, y1 = np.percentile(P[:, 0], 99.5) + pad, np.percentile(P[:, 1], 99.5) + pad
W, H = int(np.ceil((x1 - x0) / res)), int(np.ceil((y1 - y0) / res))
col = ((P[:, 0] - x0) / res).astype(int)
row = ((y1 - P[:, 1]) / res).astype(int)
ok = (col >= 0) & (col < W) & (row >= 0) & (row < H)
col, row, Z, Cc = col[ok], row[ok], P[ok, 2], C[ok]

# ---- ortofoto: el punto más alto gana; huecos rellenados con el vecino más cercano ----
order = np.argsort(Z)
img = np.zeros((H, W, 3), np.float32)
has = np.zeros((H, W), bool)
img[row[order], col[order]] = Cc[order]
has[row[order], col[order]] = True
dist, (ri, ci) = ndimage.distance_transform_edt(~has, return_indices=True)
filled = img[ri, ci]
bg = np.array([0.93, 0.94, 0.93])
alpha = np.clip(1.0 - (dist - 2) / 4, 0, 1)[..., None]   # rellena huecos de hasta ~2-3 cm
ortho = filled * alpha + bg * (1 - alpha)
Image.fromarray((ortho * 255).astype(np.uint8)).save(rep / "plan_ortho.jpg", quality=88)

# ---- corte a la altura de las paredes (0,9-1,6 m): densidad en oscuro ----
cm = (Z > 0.9) & (Z < 1.6)
dens = np.zeros((H, W), np.float32)
np.add.at(dens, (row[cm], col[cm]), 1)
dens = ndimage.gaussian_filter(dens, 1.2)
a = np.clip(dens / (np.percentile(dens[dens > 0], 70) + 1e-6), 0, 1)
cut = np.zeros((H, W, 4), np.uint8)
cut[..., :3] = (29, 35, 38)
cut[..., 3] = (a * 255).astype(np.uint8)
Image.fromarray(cut, "RGBA").save(rep / "plan_cut.png", optimize=True)

meta = {"x0": x0, "y1": y1, "res": res, "w": W, "h": H, "ceiling": ceil, "walls": meta_w["walls"]}
(rep / "plan_meta.json").write_text(json.dumps(meta))
print(f"Plano {W}x{H} px a {res * 1000:.0f} mm/px ({W * res:.2f} x {H * res:.2f} m)")
