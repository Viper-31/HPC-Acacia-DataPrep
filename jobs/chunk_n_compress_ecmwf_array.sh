#!/bin/bash
#SBATCH --job-name=chunk_n_compress_ecmwf
#SBATCH --partition=work
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
#SBATCH --mem=200G
#SBATCH --time=08:00:00
#SBATCH --array=0-1
#SBATCH --output=chunk_compress_ecmwf_%A_%a.log
#SBATCH --error=chunk_compress_ecmwf_%A_%a.err

module load python/3.11.6
cd $MYSCRATCH
source zarr_venv/bin/activate

export NUM_OF_CORES="${SLURM_CPUS_PER_TASK}"
export MEMORY_LIMIT="200GB"
export REPO_ROOT="$MYSCRATCH"
export PYTHONPATH="$MYSCRATCH/scripts:$PYTHONPATH"

YEARS=(2024 2025)
YEAR="${YEARS[$SLURM_ARRAY_TASK_ID]}"

if [ -z "${YEAR}" ]; then
  echo "Invalid SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}; expected 0..$(( ${#YEARS[@]} - 1 ))"
  exit 1
fi

echo "Starting ECMWF chunk+compress for year ${YEAR} at $(date)"

python -u scripts/chunk_n_compress.py --ecmwf-year "${YEAR}"

echo "Finished ECMWF year ${YEAR} at $(date)"
