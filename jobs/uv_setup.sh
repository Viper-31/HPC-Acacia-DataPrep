#!/bin/bash
#SBATCH --job-name=uv-setup
#SBATCH --time=00:30:00
#SBATCH --partition=work
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

export UV_PROJECT_ENVIRONMENT="$MYSOFTWARE/.venvs/hpc-acacia-dataprep/.venv"

# Navigate to project root (script lives in jobs/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")" || exit 1

uv sync --no-dev