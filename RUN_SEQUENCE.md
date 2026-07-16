# Run Sequence (Setonix)

## Prerequisites

- Repository is staged under `$MYSCRATCH` so that `jobs/` and `scripts/` are directly available at `$MYSCRATCH/
jobs` and `$MYSCRATCH/scripts`.
- `rclone` is configured for the Pawsey remote used in the stage-in/out scripts.

## Execution Order
1. Clone repo to $MYSCRATCH and prepare uv .venv in $MYSOFTWARE
```bash
cd $MYSCRATCH
git clone
sbatch HPC-Acacia-DataPrep/jobs/uv_setup.sh
```

The .venv lives on /software and survives scratch purges.
Re-run uv_setup.sh only after pulling dependency changes.

2. Stage in (copy raw data into scratch)

```bash
sbatch jobs/stage_in.sh
```
Writes: $MYSCRATCH/acacia_clean_data/DPIRD and $MYSCRATCH/acacia_clean_data/ECMWF

3. Chunk + compress NetCDF
```bash
sbatch jobs/chunk_n_compress_dpird.sh
sbatch jobs/chunk_n_compress_ecmwf_array.sh
```
Writes: $MYSCRATCH/vz_kerchunk/...

4. Convert to Zarr

```bash
(Dry run)
sbatch jobs/to_zarr_dry_run.sh
sbatch jobs/to_zarr.sh
```
Writes: $MYSCRATCH/zarr_objects/...

5. Stage-out to acacia
```bash
sbatch jobs/stage_out.sh
```
Note: stage-out targets $MYSCRATCH/vz_kerchunk (not Zarr output).

**Note**: DPIRD Zarr reads from $MYSCRATCH/vz_kerchunk/DPIRD/...
while ECMWF Zarr reads from $MYSCRATCH/acacia_clean_data/ECMWF/...

Optional checks
`sbatch jobs/checks/check_enc_zarr.sh`
Or run manually:
`python -u scripts/checks/check_enc_zarr.py`