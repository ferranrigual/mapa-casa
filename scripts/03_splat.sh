#!/usr/bin/env bash
# Paso 3: entrena el modelo 3D inmersivo (Gaussian Splatting) con gsplat.
# Usa las imágenes ya sin distorsión de data/work/<escena>/dense (paso 2).
# Resultado: output/<escena>/splat.ply  (abrir con SuperSplat o el visor de gsplat)
#
# Uso: scripts/03_splat.sh <escena> [pasos]   (por defecto 30000)
set -euo pipefail
SCENE=${1:?Falta la escena}
STEPS=${2:-30000}
DATA="data/work/$SCENE/dense"
RES="data/work/$SCENE/splat"
[ -d "$DATA/sparse" ] || { echo "Falta $DATA/sparse: ejecuta antes 02_colmap.sh"; exit 1; }

python /opt/gsplat/examples/simple_trainer.py default \
    --data-dir "$DATA" --data-factor 1 --result-dir "$RES" \
    --max-steps "$STEPS" --save-steps "$STEPS" --ply-steps "$STEPS" --eval-steps "$STEPS" \
    --save-ply --disable-viewer --disable-video \
    --antialiased --use-bilateral-grid --pose-opt

mkdir -p "output/$SCENE"
ply=$(ls -t "$RES"/ply/*.ply 2>/dev/null | head -1)
[ -n "$ply" ] || { echo "ERROR: el entrenamiento no generó ningún .ply"; exit 1; }
cp "$ply" "output/$SCENE/splat.ply"
echo "Hecho: output/$SCENE/splat.ply"
