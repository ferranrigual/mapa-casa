#!/usr/bin/env bash
# Paso 1: convierte los vídeos y fotos de data/raw/<escena>/ en fotogramas
# en data/work/<escena>/images/<origen>/ (una subcarpeta por vídeo, para que
# COLMAP use un modelo de cámara por vídeo).
#
# Uso (dentro del contenedor):  scripts/01_frames.sh <escena> [fps] [ancho_max]
#   fps        fotogramas por segundo extraídos de cada vídeo (por defecto 2)
#   ancho_max  lado largo máximo en píxeles (por defecto 1920)
set -euo pipefail
SCENE=${1:?Falta el nombre de la escena (carpeta en data/raw/)}
FPS=${2:-2}
MAXDIM=${3:-1920}
RAW="data/raw/$SCENE"
OUT="data/work/$SCENE/images"
[ -d "$RAW" ] || { echo "No existe $RAW"; exit 1; }
mkdir -p "$OUT"

scale="scale='if(gt(iw,ih),min($MAXDIM,iw),-2)':'if(gt(iw,ih),-2,min($MAXDIM,ih))'"

shopt -s nullglob nocaseglob
for v in "$RAW"/*.{mp4,mov,mkv,avi,webm,m4v}; do
    name=$(basename "${v%.*}")
    mkdir -p "$OUT/$name"
    echo ">> Vídeo $v -> $OUT/$name ($FPS fps)"
    ffmpeg -loglevel error -y -i "$v" -vf "fps=$FPS,$scale" -q:v 2 "$OUT/$name/%05d.jpg"
done

photos=("$RAW"/*.{jpg,jpeg,png,heic,webp})
if [ ${#photos[@]} -gt 0 ]; then
    mkdir -p "$OUT/fotos"
    for p in "${photos[@]}"; do
        name=$(basename "${p%.*}")
        ffmpeg -loglevel error -y -i "$p" -vf "$scale" -q:v 2 "$OUT/fotos/$name.jpg"
    done
    echo ">> ${#photos[@]} fotos -> $OUT/fotos"
fi

echo "Total fotogramas: $(find "$OUT" -name '*.jpg' | wc -l)"
