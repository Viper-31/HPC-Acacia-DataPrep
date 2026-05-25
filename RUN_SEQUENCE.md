# Run Sequence (Setonix)

## Prerequisites

- Repository is staged under `$MYSCRATCH` so that `jobs/` and `scripts/` are directly available at `$MYSCRATCH/
jobs` and `$MYSCRATCH/scripts`.
- Required modules/venv match the job scripts (e.g., `python/3.11.6`, `zarr_venv`).
- `rclone` is configured for the Pawsey remote used in the stage-in/out scripts.

## Execution Order

1. **Stage in (copy raw data into scratch)**

```bash
sbatch jobs/stage_in.sh

Writes: $MYSCRATCH/acacia_clean_data/DPIRD and $MYSCRATCH/acacia_clean_data/ECMWF

2. Chunk + compress NetCDF
sbatch jobs/chunk_n_compress.sh
sbatch jobs/chunk_n_compress_ecmwf_array.sh
Writes: $MYSCRATCH/vz_kerchunk/...

3. Convert to Zarr
sbatch jobs/to_zarr.sh
(Dry run)
sbatch jobs/to_zarr_dry_run.sh
Writes: $MYSCRATCH/zarr_objects/...

Note: DPIRD Zarr reads from $MYSCRATCH/vz_kerchunk/DPIRD/...
while ECMWF Zarr reads from $MYSCRATCH/acacia_clean_data/ECMWF/...

4. Optional checks
sbatch jobs/checks/check_enc_zarr.sh
(or run manually)
python -u scripts/checks/check_enc_zarr.py

5. Stage-out to acacia (copy chunked NetCDF back to ObjectStore)
sbatch jobs/stage_out.sh
Note: stage-out targets $MYSCRATCH/vz_kerchunk (not Zarr output).
```
