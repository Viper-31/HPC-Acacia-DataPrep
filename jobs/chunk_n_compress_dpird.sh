#!/bin/bash
#SBATCH --job-name=chunk_n_compress_dpird
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=chunk_compress_dpird_%j.log
#SBATCH --error=chunk_compress_dpird_%j.err

module load python/3.11.6
REPO_DIR="$MYSCRATCH/HPC-Acacia-DataPrep"
cd "$REPO_DIR"
source "$MYSCRATCH/zarr_venv/bin/activate"

export NUM_OF_CORES="${SLURM_CPUS_PER_TASK}"
export MEMORY_LIMIT="16GB"
export REPO_ROOT="$REPO_DIR"
export PYTHONPATH="$REPO_DIR/scripts:$PYTHONPATH"

echo "Starting Chunking and Compression at $(date)"

python -u scripts/chunk_n_compress.py --dpird-only

OUT_FILE="$MYSCRATCH/vz_kerchunk/DPIRD/dpird_wa_stations.nc"
if [ ! -s "$OUT_FILE" ]; then
  echo "ERROR: Expected output file missing or empty: $OUT_FILE" >&2
  exit 1
fi

echo "Finished at $(date)"
