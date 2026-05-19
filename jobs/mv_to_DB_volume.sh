#!/bin/bash
#SBATCH --job-name=mv_to_DB_volume
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=200G
#SBATCH --time=02:00:00
#SBATCH --output=mv_to_DB_volume_%j.log
#SBATCH --error=mv_to_DB_volume_%j.err

module load python/3.11.6
cd $MYSCRATCH
source zarr_venv/bin/activate

echo "Starting to Zarr conversion at $(date)"

export MYSCRATCH="$MYSCRATCH"

python -u mv_to_DB_volume.py

echo "Finished at $(date)"