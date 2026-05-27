#!/bin/bash
#SBATCH --job-name=to_zarr_dry_run
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=50G
#SBATCH --time=01:00:00
#SBATCH --output=to_zarr_dry_run_%j.log
#SBATCH --error=to_zarr_dry_run_%j.err

set -euo pipefail

module load python/3.11.6
cd $MYSCRATCH
source zarr_venv/bin/activate

export REPO_ROOT="$MYSCRATCH"
export PYTHONPATH="$REPO_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"

echo "Starting to Zarr conversion at $(date)"

python -u scripts/to_zarr.py --dry-run

echo "Finished at $(date)"