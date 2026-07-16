import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any, Literal

import xarray as xr
from dask.distributed import Client, LocalCluster, as_completed

from lib._contracts import load_contracts, stage_spec, scratch_path
from lib.encoding import build_netcdf_encoding

DATASETS = load_contracts()
STAGES = {
    "dpird": stage_spec(DATASETS, "dpird", "chunk_n_compress"),
    "ecmwf": stage_spec(DATASETS, "ecmwf", "chunk_n_compress"),
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProcessResult:
    ok: bool
    in_path: Path
    out_path: Path
    message: str


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def iter_inputs(spec: Mapping[str, Any]) -> tuple[list[Path], Path]:
    in_root = scratch_path(spec["input_root"])
    files = list(in_root.glob(spec["input_pattern"]))
    return files, in_root


def build_output_path_per_dataset(
    in_path: Path, spec: Mapping[str, Any], in_root: Path
) -> Path:
    out_root = scratch_path(spec["output_root"])
    rel_path = in_path.relative_to(in_root)
    return out_root / rel_path


def create_directory_paths(out_paths: list[Path]) -> None:
    """Create output directories and clean stale temp files"""
    for out_path in out_paths:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(f".{out_path.name}.tmp")
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Dataset preprocessing
# ---------------------------------------------------------------------------


def preprocess_dataset(ds: xr.Dataset, dataset_name: str) -> None:
    """Apply dataset-specific mutations in-place before chunking."""
    if dataset_name == "dpird":
        ds.attrs.clear()  # Strip global attributes (e.g. removes GMT+8 mention)


# ---------------------------------------------------------------------------
# Atomic NetCDF write
# ---------------------------------------------------------------------------


def write_netcdf_atomic(
    ds: xr.Dataset,
    out_path: Path | str,
    encoding: Mapping[str, Mapping[str, Any]] | None,
    *,
    engine: Literal["h5netcdf", "netcdf4", "scipy"] = "h5netcdf",
    netcdf_format: Literal[
        "NETCDF4", "NETCDF4_CLASSIC", "NETCDF3_64BIT", "NETCDF3_CLASSIC"
    ] = "NETCDF4",
) -> Path:
    final_path = Path(out_path)
    tmp_path = final_path.with_name(f".{final_path.name}.tmp")

    try:
        write_task = ds.to_netcdf(
            path=tmp_path,
            engine=engine,
            format=netcdf_format,
            encoding=encoding,
            compute=False,
        )
        write_task.compute(scheduler="single-threaded")

    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(
            f"Failed writing NetCDF artifact {final_path}: {exc}"
        ) from exc

    # If to_netcdf() suceeds with no Exception, return final path to print Success
    tmp_path.replace(final_path)
    return final_path


# ---------------------------------------------------------------------------
# Per-file chunking and writing (1 worker = 1 file)
# ---------------------------------------------------------------------------
def process_file(
    in_path: Path, spec: Mapping[str, Any], in_root: Path, dataset_name: str
) -> ProcessResult:
    out_path = build_output_path_per_dataset(in_path, spec, in_root)

    try:
        with xr.open_dataset(in_path, engine="h5netcdf") as ds:
            preprocess_dataset(ds, dataset_name)
            ds = ds.chunk(spec["chunk_map"])
            encoding = build_netcdf_encoding(
                ds, chunk_map=spec["chunk_map"], complevel=spec["complevel"]
            )
            write_netcdf_atomic(ds, out_path, encoding=encoding)

        return ProcessResult(
            ok=True,
            in_path=in_path,
            out_path=out_path,
            message=f"Completed: {in_path} -> {out_path}",
        )
    except Exception as exc:
        return ProcessResult(
            ok=False,
            in_path=in_path,
            out_path=out_path,
            message=f"Error preparing: {in_path}: {exc}",
        )


# ---------------------------------------------------------------------------
# Cluster configuration
# ---------------------------------------------------------------------------
def _runtime_cluster_config() -> tuple[int, str]:
    workers_raw = (
        os.getenv("NUM_OF_CORES")
        or os.getenv("WORKERS")
        or os.getenv("SLURM_CPUS_PER_TASK")
    )
    if not workers_raw:
        raise RuntimeError(
            "Set NUM_OF_CORES/WORKERS so Dask client can initialise with proper worker count"
        )

    workers = int(workers_raw)
    mem_limit_raw = os.getenv("MEMORY_LIMIT")
    if mem_limit_raw:
        mem_limit_raw = mem_limit_raw.strip().upper()
        total_gb = (
            float(mem_limit_raw[:-2])
            if mem_limit_raw.endswith("GB")
            else float(mem_limit_raw)
        )
    else:
        # Fallback from Slurm MB units
        mem_per_node_mb = os.getenv("SLURM_MEM_PER_NODE")
        if mem_per_node_mb:
            total_gb = float(mem_per_node_mb) / 1024.0
        else:
            mem_per_cpu_mb = os.getenv("SLURM_MEM_PER_CPU")
            if not mem_per_cpu_mb:
                raise RuntimeError(
                    "Set MEMORY_LIMIT (GB) or request Slurm memory so SLURM_MEM_PER_NODE/CPU is available."
                )
            total_gb = (float(mem_per_cpu_mb) * workers) / 1024.0

    mem_per_worker_gb = max(total_gb / workers, 1.0)
    return workers, f"{mem_per_worker_gb:.2f}GB"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _start_cluster(workers: int, mem_limit: str) -> tuple[Client, LocalCluster]:
    print("Starting Dask LocalCluster...", flush=True)
    cluster = LocalCluster(
        n_workers=workers,
        threads_per_worker=1,
        processes=True,
        memory_limit=mem_limit,
        dashboard_address=":8787",
    )
    print("Connecting Dask Client ...", flush=True)
    client = Client(cluster)
    print(
        f"workers={workers}, memory_limit_per_worker={mem_limit}, "
        f"dashboard={client.dashboard_link}"
    )
    return client, cluster


def _prepare_paths() -> tuple[
    list[Path], list[Mapping[str, Any]], list[Path], list[str]
]:
    """Discover input files and pre-create all output directories.

    Returns four parallel lists for ``client.map(process_file, ...)``.
    Raises :exc:`SystemExit` (code 0) when no files are found.
    """
    all_files: list[Path] = []
    all_specs: list[Mapping[str, Any]] = []
    all_roots: list[Path] = []
    all_dataset_names: list[str] = []

    out_paths: list[Path] = []

    for dataset_name, spec in STAGES.items():
        files, in_root = iter_inputs(spec)
        for file_path in files:
            all_files.append(file_path)
            all_specs.append(spec)
            all_roots.append(in_root)
            all_dataset_names.append(dataset_name)

            out_path = build_output_path_per_dataset(file_path, spec, in_root)
            if out_path.exists():
                continue  # Skip already-processed files on re-run
            out_paths.append(out_path)

    if not all_files:
        print(
            "No files found to process. Check staged inputs in "
            "$MYSCRATCH/acacia_clean_data"
        )
        raise SystemExit(0)

    # Pre-create all output directories and clean stale temps BEFORE any Dask worker starts
    create_directory_paths(out_paths)

    return all_files, all_specs, all_roots, all_dataset_names


# ---------------------------------------------------------------------------
# Task execution (fail-fast loop)
# ---------------------------------------------------------------------------


def _execute_tasks(
    client: Client,
    all_files: list[Path],
    all_specs: list[Mapping[str, Any]],
    all_roots: list[Path],
    all_dataset_names: list[str],
) -> None:
    """Submit one task per file, fail-fast on any error.

    Raises :exc:`SystemExit` (code 1) if any task fails.
    """
    print(
        f"Submitting {len(all_files)} tasks across "
        f"{len(client.scheduler_info()['workers'])} workers on cluster ..."
    )

    futures = client.map(
        process_file, all_files, all_specs, all_roots, all_dataset_names
    )
    pending = set(futures)

    for future in as_completed(futures):
        pending.discard(future)

        try:
            result = future.result()
        except Exception as exc:
            print(f"Task failed before returning a result: {exc}")
            client.cancel(list(pending), force=True)
            raise SystemExit(1) from exc

        print(result.message)

        if not result.ok:
            client.cancel(list(pending), force=True)
            raise SystemExit(1)


def main() -> None:
    workers, mem_limit = _runtime_cluster_config()
    client, cluster = _start_cluster(workers, mem_limit)

    try:
        all_files, all_specs, all_roots, all_dataset_names = _prepare_paths()
        _execute_tasks(client, all_files, all_specs, all_roots, all_dataset_names)
        print(f"All {len(all_files)} files committed.", flush=True)
    finally:
        client.close()
        cluster.close()


if __name__ == "__main__":
    main()
