# HPC-Acacia-DataPrep

This repo contains Python and Bash scripts to be run on the Pawsey Setonix supercomputer to prepare DPIRD and ECMWF data before it can be virtualised by [S3-Kerchunk-Streamer](https://github.com/Viper-31/S3-Kerchunk-streamer)

## NextFlow integration (future)

Planned next steps to orchestrate the Slurm pipeline with [NextFlow: Reproducible Scientific workflows](https://www.nextflow.io/):

- Define a NextFlow workflow that wraps the existing `jobs/*.sh` stages in order.
- Add a minimal NextFlow config tuned for Setonix (queues/partitions, resource labels, and module/venv setup).
- Document how to run the pipeline locally (dry run) vs on Setonix.

```
HPC-Acacia-DataPrep
│   README.md
│   setonix_requirement.txt
│
└───jobs/                   <-- .sh slurm wrappers
│      stage_in.sh
│      chunk_n_compress.sh

└───scripts/                <-- .py mutators
│      stage_in.sh
│      chunk_n_compress.sh
|
└───NextFlow/
```
