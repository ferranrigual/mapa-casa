#!/usr/bin/env python3
"""Genera los recursos de la página de resultados en output/<escena>/report/:
  points.bin  nube submuestreada: N x (int16 x,y,z en mm + uint8 r,g,b) = 9 bytes/punto
  cams.json   centros y direcciones de las cámaras en metros
  top.jpg, sides.jpg, frames.jpg, plan.png
Uso (en el contenedor): python scripts/make_report_assets.py <escena> [max_puntos]
"""
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402

sys.path.insert(0, "/opt/gsplat/examples")
from pycolmap import SceneManager  # noqa: E402

scene = sys.argv[1]
maxp = int(sys.argv[2]) if len(sys.argv) > 2 else 250000
W = Path("data/work") / scene
out = Path("output") / scene
rep = out / "report"
rep.mkdir(parents=True, exist_ok=True)

# ---- nube ----
pcd = o3d.io.read_point_cloud(str(out / "nube.ply"))
pcd, _ = pcd.remove_statistical_outlier(20, 2.0)
P, C = np.asarray(pcd.points), np.asarray(pcd.colors)
keep = P[:, 2] < np.percentile(P[:, 2], 99.7)
P, C = P[keep], C[keep]
if len(P) > maxp:
    i = np.random.default_rng(0).choice(len(P), maxp, replace=False)
    P, C = P[i], C[i]
rec = np.zeros(len(P), dtype=[("p", "<i2", 3), ("c", "u1", 3)])
rec["p"] = np.round(P * 1000).astype(np.int16)
rec["c"] = np.round(C * 255).astype(np.uint8)
rec.tofile(rep / "points.bin")
print(f"points.bin: {len(P)} puntos, {(rep / 'points.bin').stat().st_size / 1e6:.1f} MB")

# ---- cámaras ----
T = json.loads((W / "align.json").read_text())
s, R, t = T["s"], np.array(T["R"]), np.array(T["t"])
m = SceneManager(str(W / "dense" / "sparse"))
m.load_cameras()
m.load_images()
cams = []
for img in sorted(m.images.values(), key=lambda i: i.name):
    Rc = img.R()
    c = -Rc.T @ img.tvec
    d = Rc.T @ np.array([0, 0, 1.0])
    cams.append({"n": img.name.split("/")[-1], "c": (s * R @ c + t).round(3).tolist(),
                 "d": (R @ d).round(3).tolist()})
(rep / "cams.json").write_text(json.dumps(cams))
print(f"cams.json: {len(cams)} cámaras")

# ---- imágenes ----
o = np.argsort(P[:, 2])
fig, ax = plt.subplots(figsize=(7, 7))
mm = P[o, 2] < 2.2
ax.scatter(P[o][mm, 0], P[o][mm, 1], s=0.6, c=C[o][mm], lw=0)
cc = np.array([c["c"] for c in cams])
ax.plot(cc[:, 0], cc[:, 1], "-", c="#d9480f", lw=1.2)
ax.scatter(cc[:, 0], cc[:, 1], s=6, c="#d9480f", zorder=3)
ax.set_aspect("equal")
ax.grid(lw=0.3)
ax.set_xlabel("m")
fig.tight_layout()
fig.savefig(rep / "top.jpg", dpi=110)
plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
for a, (u, title) in zip(axs, [(0, "Corte lateral X-Z"), (1, "Corte lateral Y-Z")]):
    a.scatter(P[:, u], P[:, 2], s=0.3, c=C, lw=0)
    a.axhline(0, c="#d9480f", lw=0.8)
    a.set_aspect("equal")
    a.grid(lw=0.3)
    a.set_title(title)
fig.tight_layout()
fig.savefig(rep / "sides.jpg", dpi=100)
plt.close(fig)

frames = sorted(glob.glob(str(W / "images" / "*" / "*.jpg")))
pick = frames[:: max(1, len(frames) // 8)][:8]
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *sum([["-i", f] for f in pick], []),
                "-filter_complex",
                "".join(f"[{k}]scale=240:-2[v{k}];" for k in range(len(pick)))
                + "".join(f"[v{k}]" for k in range(len(pick))) + f"hstack=inputs={len(pick)}",
                "-q:v", "4", str(rep / "frames.jpg")], check=True)
shutil.copy(out / "plano.png", rep / "plan.png")
print("Imágenes listas en", rep)
