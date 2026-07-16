#!/bin/bash
module load python/3.11.6
cd $MYSCRATCH || exit 1
export UV_PROJECT_ENVIRONMENT="$MYSOFTWARE/.venvs/hpc-acacia-dataprep/.venv"
source "$UV_PROJECT_ENVIRONMENT/bin/activate"

echo "Starting file transfer to DB volume at $(date)"
python -u mv_to_DB_volume.py 
echo "Finished at $(date)"