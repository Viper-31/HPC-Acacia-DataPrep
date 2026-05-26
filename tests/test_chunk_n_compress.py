import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_ROOT = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)


def _write_contract(tmp_path):
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
        output_root: vz_kerchunk
        chunk_map: {station: 96, time: 52624}
        complevel: 5
  ecmwf:
    stages:
      chunk_n_compress:
        input_root: acacia_clean_data
        input_pattern: ECMWF/**/*.nc
        output_root: vz_kerchunk
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
        self.attrs = {"source": "keep-or-clear"}
        self.chunk_map = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def chunk(self, chunk_map):
        self.chunk_map = chunk_map
        return self


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


def test_output_path_for_preserves_input_relative_layout(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "ECMWF/2025/01/31.nc"

    out_path = module.output_path_for(in_path, module.STAGES["ecmwf"], input_root)

    assert out_path == tmp_path / "vz_kerchunk/ECMWF/2025/01/31.nc"


def test_process_file_clears_dpird_attrs_and_writes_atomic(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "DPIRD/DPIRD_final_stations.nc"
    fake_ds = FakeDataset()
    calls = {}

    def open_dataset(path, engine):
        calls["open_dataset"] = (path, engine)
        return fake_ds

    def build_encoding(ds, chunk_map, complevel):
        calls["build_encoding"] = (ds, chunk_map, complevel)
        return {"encoded": {}}

    def write_atomic(ds, out_path, encoding):
        calls["write_atomic"] = (ds, out_path, encoding)
        return out_path

    monkeypatch.setattr(module.xr, "open_dataset", open_dataset)
    monkeypatch.setattr(module, "build_netcdf_encoding", build_encoding)
    monkeypatch.setattr(module, "write_netcdf_atomic", write_atomic)

    result = module.process_file(in_path, module.STAGES["dpird"], input_root, "dpird")

    assert result.ok is True
    assert result.out_path == tmp_path / "vz_kerchunk/DPIRD/DPIRD_final_stations.nc"
    assert fake_ds.attrs == {}
    assert fake_ds.chunk_map == {"station": 96, "time": 52624}
    assert calls["open_dataset"] == (in_path, "h5netcdf")
    assert calls["build_encoding"] == (fake_ds, {"station": 96, "time": 52624}, 5)
    assert calls["write_atomic"] == (fake_ds, result.out_path, {"encoded": {}})


def test_process_file_keeps_ecmwf_attrs_and_writes_input_relative_output(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "ECMWF/2024/02/06.nc"
    fake_ds = FakeDataset()

    monkeypatch.setattr(module.xr, "open_dataset", lambda path, engine: fake_ds)
    monkeypatch.setattr(module, "build_netcdf_encoding", lambda ds, chunk_map, complevel: {"encoded": {}})
    monkeypatch.setattr(module, "write_netcdf_atomic", lambda ds, out_path, encoding: out_path)

    result = module.process_file(in_path, module.STAGES["ecmwf"], input_root, "ecmwf")

    assert result.ok is True
    assert result.out_path == tmp_path / "vz_kerchunk/ECMWF/2024/02/06.nc"
    assert fake_ds.attrs == {"source": "keep-or-clear"}
    assert fake_ds.chunk_map == {"time": 4, "step": 113, "latitude": 111, "longitude": 151}


def test_process_file_returns_failure_result_without_raising(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    in_path = input_root / "ECMWF/2024/02/06.nc"

    def open_dataset(path, engine):
        raise OSError("cannot read")

    monkeypatch.setattr(module.xr, "open_dataset", open_dataset)

    result = module.process_file(in_path, module.STAGES["ecmwf"], input_root, "ecmwf")

    assert result.ok is False
    assert result.in_path == in_path
    assert result.out_path == tmp_path / "vz_kerchunk/ECMWF/2024/02/06.nc"
    assert "cannot read" in result.message


@pytest.mark.integration
def test_write_netcdf_atomic_replaces_existing_output_after_success(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ECMWF/2024/02/06.nc"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("old failed output", encoding="utf-8")

    result = module.write_netcdf_atomic(ds, out_path, encoding={})

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > len("old failed output")
    assert not (out_path.parent / ".06.nc.tmp").exists()


@pytest.mark.integration
def test_write_netcdf_atomic_removes_stale_temp_before_writing(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "DPIRD/DPIRD_final_stations.nc"
    tmp_path_nc = out_path.parent / ".DPIRD_final_stations.nc.tmp"
    tmp_path_nc.parent.mkdir(parents=True)
    tmp_path_nc.write_text("stale temp", encoding="utf-8")

    def write_replacement(self, path, *args, **kwargs):
        assert not Path(path).exists()
        Path(path).write_text("new complete output", encoding="utf-8")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", write_replacement)

    module.write_netcdf_atomic(ds, out_path, encoding={})

    assert out_path.read_text(encoding="utf-8") == "new complete output"
    assert not tmp_path_nc.exists()


@pytest.mark.integration
def test_write_netcdf_atomic_removes_temp_and_keeps_existing_output_on_failure(
    tmp_path,
    monkeypatch,
):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ECMWF/2024/02/06.nc"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("previous complete output", encoding="utf-8")

    def fail_to_netcdf(self, path, *args, **kwargs):
        Path(path).write_text("partial output", encoding="utf-8")
        raise OSError("boom")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail_to_netcdf)

    with pytest.raises(RuntimeError, match="Failed writing NetCDF artifact"):
        module.write_netcdf_atomic(ds, out_path, encoding={})

    assert out_path.read_text(encoding="utf-8") == "previous complete output"
    assert not (out_path.parent / ".06.nc.tmp").exists()


def test_main_submits_all_files_with_client_map_and_closes_cluster(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    dpird_file = input_root / "DPIRD/DPIRD_final_stations.nc"
    ecmwf_file = input_root / "ECMWF/2024/02/06.nc"
    calls = []

    class FakeCluster:
        def __init__(self, **kwargs):
            calls.append(("cluster", kwargs))

        def close(self):
            calls.append("cluster_close")

    class FakeFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            calls.append(("future_result", self._result.message))
            return self._result

    class FakeClient:
        def __init__(self, cluster):
            calls.append(("client", cluster.__class__.__name__))
            self.dashboard_link = "http://localhost:8787/status"

        def scheduler_info(self):
            return {"workers": {"a": {}, "b": {}}}

        def map(self, func, files, specs, roots, dataset_names):
            calls.append(("map", files, specs, roots, dataset_names))
            return [
                FakeFuture(SimpleNamespace(ok=True, message="dpird ok")),
                FakeFuture(SimpleNamespace(ok=True, message="ecmwf ok")),
            ]

        def close(self):
            calls.append("client_close")

    def iter_inputs(spec):
        if spec is module.STAGES["dpird"]:
            return [dpird_file], input_root
        return [ecmwf_file], input_root

    monkeypatch.setattr(module, "LocalCluster", FakeCluster)
    monkeypatch.setattr(module, "Client", FakeClient)
    monkeypatch.setattr(module, "as_completed", lambda futures: futures, raising=False)
    monkeypatch.setattr(module, "_runtime_cluster_config", lambda: (2, "100.00GB"))
    monkeypatch.setattr(module, "iter_inputs", iter_inputs)

    module.main()

    assert calls == [
        ("cluster", {
            "n_workers": 2,
            "threads_per_worker": 1,
            "processes": True,
            "memory_limit": "100.00GB",
            "dashboard_address": ":8787",
        }),
        ("client", "FakeCluster"),
        ("map", [dpird_file, ecmwf_file], [module.STAGES["dpird"], module.STAGES["ecmwf"]], [input_root, input_root], ["dpird", "ecmwf"]),
        ("future_result", "dpird ok"),
        ("future_result", "ecmwf ok"),
        "client_close",
        "cluster_close",
    ]


def test_main_exits_nonzero_after_all_futures_when_any_file_fails(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    calls = []

    class FakeCluster:
        def __init__(self, **kwargs):
            pass

        def close(self):
            calls.append("cluster_close")

    class FakeFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            calls.append(self._result.message)
            return self._result

    class FakeClient:
        dashboard_link = "http://localhost:8787/status"

        def __init__(self, cluster):
            pass

        def scheduler_info(self):
            return {"workers": {"a": {}}}

        def map(self, func, files, specs, roots, dataset_names):
            return [
                FakeFuture(SimpleNamespace(ok=False, message="first failed")),
                FakeFuture(SimpleNamespace(ok=True, message="second succeeded")),
            ]

        def close(self):
            calls.append("client_close")

    monkeypatch.setattr(module, "LocalCluster", FakeCluster)
    monkeypatch.setattr(module, "Client", FakeClient)
    monkeypatch.setattr(module, "as_completed", lambda futures: futures, raising=False)
    monkeypatch.setattr(module, "_runtime_cluster_config", lambda: (1, "100.00GB"))
    monkeypatch.setattr(module, "iter_inputs", lambda spec: ([input_root / "file.nc"], input_root))

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 1
    assert calls == ["first failed", "second succeeded", "client_close", "cluster_close"]


def test_main_returns_without_error_when_no_files_found(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    calls = []

    class FakeCluster:
        def __init__(self, **kwargs):
            pass

        def close(self):
            calls.append("cluster_close")

    class FakeClient:
        dashboard_link = "http://localhost:8787/status"

        def __init__(self, cluster):
            pass

        def close(self):
            calls.append("client_close")

    monkeypatch.setattr(module, "LocalCluster", FakeCluster)
    monkeypatch.setattr(module, "Client", FakeClient)
    monkeypatch.setattr(module, "_runtime_cluster_config", lambda: (1, "100.00GB"))
    monkeypatch.setattr(module, "iter_inputs", lambda spec: ([], tmp_path / "acacia_clean_data"))

    module.main()

    assert calls == ["client_close", "cluster_close"]


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
