#!/usr/bin/env bash
# Paso 2: reconstrucción 3D con COLMAP (dentro del contenedor).
#   data/work/<escena>/images/   -> fotogramas (paso 1)
#   data/work/<escena>/sparse/0  -> cámaras + nube dispersa (para gsplat)
#   data/work/<escena>/dense/    -> imágenes sin distorsión + nube densa fused.ply (para el plano)
#
# Uso: scripts/02_colmap.sh <escena> [--no-dense] [--global]
set -euo pipefail
SCENE=${1:?Falta la escena}; shift
DENSE=1; MAPPER=mapper
for a in "$@"; do
    case $a in
        --no-dense) DENSE=0 ;;
        --global) MAPPER=global_mapper ;;
    esac
done

W="data/work/$SCENE"
IMG="$W/images"
DB="$W/database.db"
N=$(find "$IMG" -name '*.jpg' | wc -l)
echo "== $N imágenes en $IMG"
log() { echo; echo "== [$(date +%H:%M:%S)] $*"; }

rm -rf "$DB" "$W/sparse" "$W/dense"
mkdir -p "$W/sparse"

log "Extracción de características (SIFT, GPU)"
colmap feature_extractor --log_level 1 \
    --database_path "$DB" --image_path "$IMG" \
    --ImageReader.camera_model OPENCV \
    --ImageReader.single_camera_per_folder 1 \
    --FeatureExtraction.use_gpu 1 \
    --SiftExtraction.max_num_features 8192 \
    --SiftExtraction.estimate_affine_shape 1 \
    --SiftExtraction.domain_size_pooling 1

if [ "$N" -le 400 ]; then
    log "Emparejamiento exhaustivo"
    colmap exhaustive_matcher --log_level 1 --database_path "$DB" \
        --FeatureMatching.use_gpu 1 --FeatureMatching.guided_matching 1
else
    log "Emparejamiento secuencial"
    colmap sequential_matcher --log_level 1 --database_path "$DB" \
        --FeatureMatching.use_gpu 1 --FeatureMatching.guided_matching 1 \
        --SequentialMatching.overlap 20
fi

log "Reconstrucción ($MAPPER)"
colmap $MAPPER --log_level 1 --database_path "$DB" --image_path "$IMG" --output_path "$W/sparse"

# Elige el modelo con más imágenes registradas y lo deja en sparse/0
best=$(for m in "$W"/sparse/*/; do
    n=$(colmap model_analyzer --path "$m" 2>&1 | grep -oP 'Registered images: \K\d+' || echo 0)
    echo "$n $m"; done | sort -rn | head -1)
echo "Mejor modelo: $best"
bm=$(echo "$best" | awk '{print $2}')
if [ "${bm%/}" != "$W/sparse/0" ]; then
    mv "$W/sparse/0" "$W/sparse/_tmp0" 2>/dev/null || true
    mv "$bm" "$W/sparse/0"
fi
colmap model_analyzer --path "$W/sparse/0" 2>&1 | grep -E 'Cameras|Images|Registered|Points|Observations|reprojection' || true

[ $DENSE -eq 1 ] || exit 0

log "Corrección de distorsión"
colmap image_undistorter --log_level 1 --image_path "$IMG" --input_path "$W/sparse/0" \
    --output_path "$W/dense" --output_type COLMAP --max_image_size 1600

log "Estéreo multivista (PatchMatch, GPU)"
colmap patch_match_stereo --log_level 1 --workspace_path "$W/dense" \
    --PatchMatchStereo.geom_consistency true

log "Fusión de la nube densa"
colmap stereo_fusion --log_level 1 --workspace_path "$W/dense" \
    --output_path "$W/dense/fused.ply"

log "Hecho: $W/dense/fused.ply"
