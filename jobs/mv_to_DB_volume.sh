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

export REPO_ROOT="$MYSCRATCH"
export PYTHONPATH="$MYSCRATCH/scripts:$PYTHONPATH"
export DATABRIRCKS_CONFIG_FILE= "$MYSCRATCH/.databrickscfg"

echo "Starting to Zarr conversion at $(date)"

python -u scripts/to_zarr.py

echo "Finished at $(date)"