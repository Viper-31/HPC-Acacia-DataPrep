#!/bin/bash
#SBATCH --job-name=chunk_n_compress
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=200G
#SBATCH --time=04:00:00
#SBATCH --output=chunk_compress_%j.log
#SBATCH --error=chunk_compress_%j.err

set -euo pipefail

module load python/3.11.6
REPO_DIR="$MYSCRATCH/HPC-Acacia-DataPrep"
cd "$REPO_DIR"
source "$MYSCRATCH/zarr_venv/bin/activate"

export NUM_OF_CORES="${SLURM_CPUS_PER_TASK}"
export MEMORY_LIMIT="200GB"
export REPO_ROOT="$REPO_DIR"
export PYTHONPATH="$REPO_DIR/scripts:${PYTHONPATH:+:$PYTHONPATH}"

echo "Starting Chunking and Compression at $(date)"

python -u scripts/chunk_n_compress.py 

echo "Finished at $(date)"
