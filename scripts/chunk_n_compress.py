import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any

import xarray as xr
from dask.distributed import Client, LocalCluster, as_completed

from lib._contracts import load_contracts, stage_spec, scratch_path
from lib.encoding import build_netcdf_encoding

DATASETS= load_contracts()
STAGES= {
    "dpird": stage_spec(DATASETS, "dpird", "chunk_n_compress"),
    "ecmwf": stage_spec(DATASETS, "ecmwf", "chunk_n_compress")
}

@dataclass(frozen=True)
class ProcessResult:
    ok: bool
    in_path: Path
    out_path: Path
    message: str


def iter_inputs(spec: Mapping[str, Any]) -> tuple[list[Path], Path]:
    in_root = scratch_path(spec["input_root"])
    files = list(in_root.glob(spec["input_pattern"]))
    return files, in_root


def output_path_for(in_path: Path, spec: Mapping[str, Any], in_root: Path) -> Path:
    out_root = scratch_path(spec["output_root"])
    rel_path = in_path.relative_to(in_root)
    return out_root / rel_path

def write_netcdf_atomic(
    ds: xr.Dataset,
    out_path: Path | str,
    encoding: Mapping[str, Mapping[str,Any]] | None,
    *,
    engine: str = "h5netcdf",
    netcdf_format: str = "NETCDF4"
) -> Path:
    final_path = Path(out_path)
    tmp_path= final_path.with_name(f".{final_path.name}.tmp")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    # Clear artefacts from old (failed) runs
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        ds.to_netcdf(
            path=tmp_path,
            engine=engine,
            format=netcdf_format,
            encoding=encoding
        )
    
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Failed writing NetCDF artifact {final_path}: {exc}") from exc
    
    # If to_netcdf() suceeeds with no Exception, return final path to print Sucess
    tmp_path.replace(final_path)
    return final_path


def process_file(
    in_path: Path, 
    spec: Mapping[str, Any], 
    in_root: Path, 
    dataset_name: str
) -> ProcessResult:
    out_path = output_path_for(in_path, spec, in_root)
    
    try:
        with xr.open_dataset(in_path, engine="h5netcdf") as ds:
            if dataset_name == "dpird":
                # Strip global dataset attribute from dprid ds. Removes GMT+8 mention
                ds.attrs.clear()
            
            ds=ds.chunk(spec["chunk_map"])
            encoding= build_netcdf_encoding(ds, spec["chunk_map"], complevel=spec["complevel"])
            write_netcdf_atomic(ds, out_path, encoding=encoding)
        
        return ProcessResult(
            ok=True,
            in_path=in_path,
            out_path=out_path,
            message=f"Completed: {in_path} -> {out_path}"
        )
    
    except Exception as exc:
        return ProcessResult(
            ok=False,
            in_path=in_path,
            out_path=out_path,
            message=f"Error preparing: {in_path}: {exc}"
        )
        

def _runtime_cluster_config() -> tuple[int, str]:
    workers_raw= os.getenv("NUM_OF_CORES") or os.getenv("WORKERS") or os.getenv("SLURM_CPUS_PER_TASK")
    if not workers_raw:
        raise RuntimeError("Set NUM_OF_CORES/WORKERS so Dask client can initialise with proper worker count")
    
    workers= int(workers_raw)
    # Prefer explicit MEMORY_LIMIT in GB (e.g. "160GB")
    mem_limit_raw = os.getenv("MEMORY_LIMIT")
    if mem_limit_raw:
        mem_limit_raw = mem_limit_raw.strip().upper()
        total_gb = float(mem_limit_raw[:-2]) if mem_limit_raw.endswith("GB") else float(mem_limit_raw)
    else:
        # Fallback from Slurm MB units
        mem_per_node_mb = os.getenv("SLURM_MEM_PER_NODE")
        if mem_per_node_mb:
            total_gb = float(mem_per_node_mb) / 1024.0
        else:
            mem_per_cpu_mb = os.getenv("SLURM_MEM_PER_CPU")
            if not mem_per_cpu_mb:
                raise RuntimeError("Set MEMORY_LIMIT (GB) or request Slurm memory so SLURM_MEM_PER_NODE/CPU is available.")
            total_gb = (float(mem_per_cpu_mb) * workers) / 1024.0

    mem_per_worker_gb = max(total_gb / workers, 1.0)
    return workers, f"{mem_per_worker_gb:.2f}GB"

def main() -> None:
    workers, mem_limit = _runtime_cluster_config()

    cluster = LocalCluster(
        n_workers=workers,
        threads_per_worker=1,
        processes=True,
        memory_limit=mem_limit,
        dashboard_address=":8787"
    )

    client = Client(cluster)
    print(f"workers={workers}, memory_limit_per_worker={mem_limit}, dashboard={client.dashboard_link}")

    failures = 0

    try:
        all_files: list[Path] = []
        all_specs: list[Mapping[str, Any]] = []
        all_roots: list[Path] = []
        all_dataset_names: list[str] = []

        for dataset_name, spec in STAGES.items():
            files, in_root = iter_inputs(spec)
            for file_path in files:
                # Do not have workers race to mkdir
                out_path =  output_path_for(file_path, spec, in_root)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                all_files.append(file_path)
                all_specs.append(spec)
                all_roots.append(in_root)
                all_dataset_names.append(dataset_name)
        
        if not all_files:
            print("No files found to process. Check staged inputs in $MYSCRATCH/acacia_clean_data")
            return
        
        print(
            f"Submitting {len(all_files)} tasks across "
            f"{len(client.scheduler_info()['workers'])} workers on cluster ..."
        )

        futures = client.map(process_file, all_files, all_specs, all_roots, all_dataset_names)

        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                failures += 1
                print(f"Task failed before returning a result: {exc}")
                continue
            
            print(result.message)
            if not result.ok:
                failures += 1
        
        if failures:
            raise SystemExit(1)
    finally:
        client.close()
        cluster.close()


if __name__ == "__main__":
    main()
