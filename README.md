# HPC-Acacia-DataPrep

This repo contains Python and Bash scripts to be run on the Pawsey Setonix supercomputer to prepare DPIRD and ECMWF data before it can be virtualised by [S3-Kerchunk-Streamer](https://github.com/Viper-31/S3-Kerchunk-streamer)

## !! IMPORTANT !!: Need to refactor codebase

- Instead of numbering staging and chunking sequence, seperate into jobs/ and scripts/
- Any file reference to 01, 02.1, 02.2, within the scripts themselves need to be edited to match future filenames
- Investigate setting up simple barebones [NextFlow: Reproducible Scientific workflows](https://www.nextflow.io/)

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
