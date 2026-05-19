import argparse
import warnings

import xarray as xr
from zarr.codecs import Blosc

from lib._contracts import load_contracts, stage_spec, scratch_path
from lib.encoding import build_zarr_encoding, resolve_fill_value

warnings.filterwarnings(
    "ignore",
    message=".*Numcodecs codecs are not in the Zarr version 3 specification.*"
)

DATASETS = load_contracts()
DPIRD_SPEC = stage_spec(DATASETS, "dpird", "to_zarr")
ECMWF_SPEC = stage_spec(DATASETS, "ecmwf", "to_zarr")
compressors= [Blosc(cname="zstd", clevel= 5, shuffle= 1)]

def parse_args():
    """--dry-run flag gets the first 8 ecmwf files to build 1 shard"""
    parser= argparse.ArgumentParser()
    parser.add_argument("--dry-run", action= "store_true", help= "Limit ECMWF to 10 .nc sample and write to seperate .zarr store")
    
    return parser.parse_args()

def dpird_to_zarr(dry_run: bool = False):
    in_root = scratch_path(DPIRD_SPEC["input_root"])
    dpird_path = in_root / DPIRD_SPEC["input_pattern"]

    if not dpird_path.exists():
        raise FileNotFoundError(f"chunk_n_compress.sh should have ran to produce: {dpird_path}")
    
    out_root = scratch_path(DPIRD_SPEC["output_root"])
    out_path = out_root / ("dpird_dryrun.zarr" if dry_run else "dpird.zarr")
    out_root.mkdir(parents=True, exist_ok=True)

    fill_value = resolve_fill_value(DPIRD_SPEC["fill_value"], DPIRD_SPEC["fill_value_dtype"])

    with xr.open_dataset(dpird_path, engine="h5netcdf") as ds:
        encoding = build_zarr_encoding(
            ds,
            chunk_map = DPIRD_SPEC["chunk_map"],
            shard_map = DPIRD_SPEC["shard_map"],
            fill_value = fill_value,
            compressors = compressors
        )
        ds.to_zarr(out_path, zarr_format=3, encoding=encoding, mode="w", consolidated=False)

def ecmwf_to_zarr(dry_run: bool = False):
    in_root = scratch_path(ECMWF_SPEC["input_root"])
    pattern = ECMWF_SPEC["input_pattern"]
    ecmwf_files = sorted(in_root.glob(pattern))

    if not ecmwf_files or len(ecmwf_files) <= 1:
        raise FileNotFoundError(f"Not enough ECMWF files found at {in_root} with pattern {pattern}")
    
    if dry_run:
        ecmwf_files=[ecmwf_files[9]]     

    out_root = scratch_path(ECMWF_SPEC["output_root"])
    out_path = out_root / ("ecmwf_dryrun.zarr" if dry_run else "ecmwf.zarr")
    out_root.mkdir(parents=True, exist_ok=True)

    fill_value = resolve_fill_value(ECMWF_SPEC["fill_value"], ECMWF_SPEC["fill_value_dtype"])

    with xr.open_mfdataset(
        ecmwf_files,
        concat_dim="time",
        combine="nested",
        parallel=True,
        engine="h5netcdf",
    ) as ds:
        # On disk chunk must match (120, 113, 111, 151) shard boundaries
        ds = ds.chunk(ECMWF_SPEC["shard_map"])

        # chunk_map in encoding will tell Zarr V3 to write specified chunks inside shards
        encoding = build_zarr_encoding(
            ds,
            chunk_map = ECMWF_SPEC["chunk_map"],
            shard_map = ECMWF_SPEC["shard_map"],
            fill_value = fill_value,
            compressors= compressors
        )

        ds.to_zarr(out_path, zarr_format=3, encoding=encoding, mode="w", consolidated=False)

def main():
    args= parse_args()

    print("Starting DPIRD -> Zarr")
    dpird_to_zarr(dry_run=args.dry_run)
    print("DPIRD complete")

    print("Starting ECMWF -> Zarr")
    ecmwf_to_zarr(dry_run=args.dry_run)
    print("ECMWF complete")

if __name__ == "__main__":
    main()