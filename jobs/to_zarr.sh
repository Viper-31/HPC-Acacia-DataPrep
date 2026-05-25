#!/bin/bash
#SBATCH --job-name=to_zarr
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=200G
#SBATCH --time=02:00:00
#SBATCH --output=to_zarr_%j.log
#SBATCH --error=to_zarr_%j.err

module load python/3.11.6
REPO_DIR="$MYSCRATCH/HPC-Acacia-DataPrep"
cd "$REPO_DIR"
source "$MYSCRATCH/zarr_venv/bin/activate"

export REPO_ROOT="$REPO_DIR"
export PYTHONPATH="$REPO_DIR/scripts:$PYTHONPATH"

echo "Starting to Zarr conversion at $(date)"

python -u scripts/to_zarr.py

echo "Finished at $(date)"
