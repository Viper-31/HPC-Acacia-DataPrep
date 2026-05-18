import os
from pathlib import Path
import warnings
from dask.distributed import Client, LocalCluster, as_completed
import xarray as xr

from lib._contracts import load_contracts, stage_spec, scratch_path
from lib.encoding import build_netcdf_encoding

warnings.filterwarnings(
    "ignore",
    message="Numcodecs codecs are not in the Zarr version 3 specification*",
    category=UserWarning
)

DATASETS= load_contracts()
STAGES= {
    "dpird": stage_spec(DATASETS, "dpird", "chunk_n_compress"),
    "ecmwf": stage_spec(DATASETS, "dpird", "chunk_n_compress")
}

def iter_inputs(spec):
    in_root = scratch_path(spec["input_root"])
    files = list(in_root.glob(spec["input_pattern"]))
    return files, in_root

def process_file(in_path, spec, in_root):
    """Chunks and compresses a single NetCDF file according to contracts/datasets.yml specs."""
    out_root= scratch_path(spec["output_root"])
    rel_path= in_path.relative_to(in_root)
    out_path= out_root / rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with xr.open_dataset(in_path, engine="h5netcdf") as ds:
            ds = ds.chunk(spec["chunks"])
            encoding = build_netcdf_encoding(ds, spec["chunk_map"], complevel=spec["complevel"])
        
            ds.to_netcdf(
                path=out_path,
                engine="h5netcdf",
                format="NETCDF4",
                encoding=encoding
            )
        return f"Completed: {in_path} -> {out_path}"
    except Exception as e:
        print(f"Error preparing {in_path}: {e}")
        return None

def main():  
    # Initialize Dask LocalCluster for Setonix Node (180GB/24 workers= 11.25GB per worker)
    cluster = LocalCluster(
        n_workers=24, 
        threads_per_worker=1, # n_workers x threads_per_worker = SBATCH cpus
        memory_limit="8GB",
        dashboard_address=":8787"
    )
    client = Client(cluster)
    print(f"Dask Dashboard available at: {client.dashboard_link}")

    all_files = []
    all_specs = []
    all_roots = []

    for spec in STAGES.values():
        files, in_root= iter_inputs(spec)
        for f in files:
            all_files.append(f)
            all_specs.append(spec)
            all_roots.append(in_root)

    if not all_files:
        print("No files found to process. Check staged inputs in $MYSCRATCH")
        client.close()
        cluster.close()
        return

    print(f"Submitting {len(all_files)} tasks across {len(client.scheduler_info()['workers'])} workers on cluster ...")
    
    futures= client.map(process_file, all_files, all_specs, all_roots)
    
    for future in as_completed(futures):
        print(future.result())

    client.close()
    cluster.close()

if __name__ == "__main__":
    main()
