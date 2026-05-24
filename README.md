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
│   pyproject.toml
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

## Interactive job scheduling workflow

### 1. Request Allocation
```bash
salloc --account=your-project-account -p work --nodes=1 --ntasks=32 --cpus-per-task=1 --mem=58G --time=00:30:00
```

### 2. Run Test Environment
Once the terminal prompt changes to `setonix@nidXXXXX`, paste these:
```bash
cd \$MYSCRATCH/my_project_dir
module load gcc/12.2.0
srun -n 4 ./my_binary.x
```

### 3. Cleanup
Type `exit` to release the compute node resource.
