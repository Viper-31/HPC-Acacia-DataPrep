import importlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_ROOT = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


def _write_contract(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "datasets.yml").write_text(
        """
datasets:
  dpird:
    stages:
      chunk_n_compress:
        input_root: acacia_clean_data
        input_pattern: DPIRD/DPIRD_final_stations.nc
        output_root: kerchunk_webviz
        chunk_map: {station: 96, time: 52624}
        complevel: 5
  ecmwf:
    stages:
      chunk_n_compress:
        input_root: acacia_clean_data
        input_pattern: ECMWF/**/*.nc
        output_root: kerchunk_webviz
        chunk_map: {time: 4, step: 113, latitude: 111, longitude: 151}
        complevel: 5
""".strip(),
        encoding="utf-8",
    )


def _import_chunk_n_compress(tmp_path, monkeypatch):
    _write_contract(tmp_path)
    monkeypatch.setenv("REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("MYSCRATCH", str(tmp_path))
    sys.modules.pop("chunk_n_compress", None)
    return importlib.import_module("chunk_n_compress")


class FakeDataset:
    def __init__(self):
        self.attrs: dict = {"source": "keep-or-clear"}
        self.chunk_map: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def chunk(self, chunk_map):
        self.chunk_map = chunk_map
        return self


# ---------------------------------------------------------------------------
# Unit testing
# ---------------------------------------------------------------------------
def test_iter_inputs_returns_matching_files_and_input_root(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    first = input_root / "ECMWF/2024/02/06.nc"
    second = input_root / "ECMWF/2024/02/07.nc"
    ignored = input_root / "README.txt"
    for path in (first, second, ignored):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    files, root = module.iter_inputs(module.STAGES["ecmwf"])

    assert root == input_root
    assert sorted(files) == [first, second]


def test_iter_inputs_returns_empty_when_no_match(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    input_root.mkdir(parents=True)

    files, root = module.iter_inputs(module.STAGES["dpird"])

    assert root == input_root
    assert files == []


def test_build_output_path_per_dataset_preserves_relative_layout(
    tmp_path,
    monkeypatch,
):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "ECMWF/2025/01/31.nc"

    out_path = module.build_output_path_per_dataset(
        in_path,
        module.STAGES["ecmwf"],
        input_root,
    )

    assert out_path == tmp_path / "kerchunk_webviz/ECMWF/2025/01/31.nc"


def test_create_directory_paths_creates_parents(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    out_paths = [
        tmp_path / "kerchunk_webviz" / "ECMWF" / "2024" / "06.nc",
        tmp_path / "kerchunk_webviz" / "DPIRD" / "stations.nc",
    ]

    module.create_directory_paths(out_paths)

    for p in out_paths:
        assert p.parent.exists()


def test_create_directory_paths_cleans_stale_temps(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    out_path = tmp_path / "kerchunk_webviz" / "DPIRD" / "stations.nc"
    stale = out_path.with_name(f".{out_path.name}.tmp")
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    module.create_directory_paths([out_path])

    assert not stale.exists()


def test_preprocess_dataset_clears_attrs_for_dpird(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"foo": ("x", [1, 2])}, attrs={"source": "dpird v3"})

    module.preprocess_dataset(ds, "dpird")

    assert ds.attrs == {}


def test_preprocess_dataset_preserves_attrs_for_non_dpird(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"foo": ("x", [1, 2])}, attrs={"source": "ecmwf era5"})

    module.preprocess_dataset(ds, "ecmwf")

    assert ds.attrs == {"source": "ecmwf era5"}


def test_process_file_delegates_correctly(tmp_path, monkeypatch):
    """process_file opens, preprocesses, chunks, encodes, and writes atomically.

    Assertions use the spec's own values (spec["chunk_map"], spec["complevel"])
    so the test does not break when the contract fixture changes.
    """
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    spec = module.STAGES["dpird"]
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "DPIRD/DPIRD_final_stations.nc"
    fake_ds = FakeDataset()
    calls: dict = {}

    def fake_open_dataset(path, *, engine):
        calls["open_dataset"] = (path, engine)
        return fake_ds

    def fake_build_encoding(ds, chunk_map, *, complevel):
        calls["build_encoding"] = {
            "ds": ds,
            "chunk_map": chunk_map,
            "complevel": complevel,
        }
        return {"encoded": {}}

    def fake_write_atomic(ds, out_path, *, encoding):
        calls["write_atomic"] = {
            "ds": ds,
            "out_path": out_path,
            "encoding": encoding,
        }
        return out_path

    monkeypatch.setattr(module.xr, "open_dataset", fake_open_dataset)
    monkeypatch.setattr(module, "build_netcdf_encoding", fake_build_encoding)
    monkeypatch.setattr(module, "write_netcdf_atomic", fake_write_atomic)

    result = module.process_file(in_path, spec, input_root, "dpird")

    # -- Result shape --
    assert result.ok is True
    assert "Completed" in result.message
    assert result.in_path == in_path
    assert result.out_path == tmp_path / "kerchunk_webviz/DPIRD/DPIRD_final_stations.nc"

    # -- Preprocessing side-effect --
    assert fake_ds.attrs == {}

    # -- Delegation (use spec values, not hardcoded literals) --
    assert calls["open_dataset"] == (in_path, "h5netcdf")
    assert calls["build_encoding"]["ds"] is fake_ds
    assert calls["build_encoding"]["chunk_map"] == spec["chunk_map"]
    assert calls["build_encoding"]["complevel"] == spec["complevel"]
    assert calls["write_atomic"]["ds"] is fake_ds
    assert calls["write_atomic"]["out_path"] == result.out_path
    assert calls["write_atomic"]["encoding"] == {"encoded": {}}

    # -- Chunking used the spec's chunk_map --
    assert fake_ds.chunk_map == spec["chunk_map"]


def test_process_file_returns_failure_result(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    spec = module.STAGES["ecmwf"]
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "ECMWF/2024/02/06.nc"

    def fail_open(path, *, engine):
        raise OSError("cannot read")

    monkeypatch.setattr(module.xr, "open_dataset", fail_open)

    result = module.process_file(in_path, spec, input_root, "ecmwf")

    assert result.ok is False
    assert result.in_path == in_path
    assert result.out_path == tmp_path / "kerchunk_webviz/ECMWF/2024/02/06.nc"
    assert "cannot read" in result.message


def test_runtime_cluster_config_raises_when_workers_missing(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    monkeypatch.delenv("NUM_OF_CORES", raising=False)
    monkeypatch.delenv("WORKERS", raising=False)
    monkeypatch.delenv("SLURM_CPUS_PER_TASK", raising=False)

    with pytest.raises(RuntimeError, match="NUM_OF_CORES/WORKERS"):
        module._runtime_cluster_config()


def test_runtime_cluster_config_uses_explicit_memory_limit(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    monkeypatch.setenv("NUM_OF_CORES", "8")
    monkeypatch.setenv("MEMORY_LIMIT", "160GB")
    monkeypatch.delenv("SLURM_MEM_PER_NODE", raising=False)
    monkeypatch.delenv("SLURM_MEM_PER_CPU", raising=False)

    workers, mem = module._runtime_cluster_config()

    assert workers == 8
    assert mem == "20.00GB"


def test_runtime_cluster_config_raises_when_memory_missing(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    monkeypatch.setenv("NUM_OF_CORES", "4")
    monkeypatch.delenv("MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("SLURM_MEM_PER_NODE", raising=False)
    monkeypatch.delenv("SLURM_MEM_PER_CPU", raising=False)

    with pytest.raises(RuntimeError, match="Set MEMORY_LIMIT"):
        module._runtime_cluster_config()


# ---------------------------------------------------------------------------
# Integration write_netcdf_atomic — real xarray I/O
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_write_netcdf_atomic_writes_and_renames(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ECMWF/2024/02/06.nc"
    out_path.parent.mkdir(parents=True)

    result = module.write_netcdf_atomic(ds, out_path, encoding={})

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    assert not (out_path.parent / ".06.nc.tmp").exists()


@pytest.mark.integration
def test_write_netcdf_atomic_cleans_temp_on_failure(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ECMWF/2024/02/06.nc"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("original", encoding="utf-8")

    def fail_to_netcdf(self, path, *args, **kwargs):
        Path(path).write_text("partial", encoding="utf-8")
        raise OSError("boom")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail_to_netcdf)

    with pytest.raises(RuntimeError, match="Failed writing NetCDF artifact"):
        module.write_netcdf_atomic(ds, out_path, encoding={})

    assert out_path.read_text(encoding="utf-8") == "original"
    assert not (out_path.parent / ".06.nc.tmp").exists()
