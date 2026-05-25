import importlib
import os
import sys
from types import SimpleNamespace

import pytest


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
        output_pattern: DPIRD/dpird_wa_stations.nc
        chunk_map: {station: 96, time: 52624}
        complevel: 5
  ecmwf:
    stages:
      chunk_n_compress:
        input_root: acacia_clean_data
        output_root: vz_kerchunk
        years:
          - year: 2025
            input_pattern: ECMWF/2025/**/*.nc
            output_pattern: ECMWF/2025/ecmwf_op.nc
          - year: 2024
            input_pattern: ECMWF/2024/**/*.nc
            output_pattern: ECMWF/2024/ecmwf_op.nc
        chunk_map: {time: 4}
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
        self.attrs = {"remove": "me"}
        self.chunk_map = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def chunk(self, chunk_map):
        self.chunk_map = chunk_map
        return self


def test_write_dpird_drops_dataset_attrs_and_writes_atomic(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    in_path = tmp_path / "acacia_clean_data/DPIRD/DPIRD_final_stations.nc"
    in_path.parent.mkdir(parents=True)
    in_path.write_text("placeholder", encoding="utf-8")
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

    monkeypatch.setattr(module.xr, "open_dataset", open_dataset)
    monkeypatch.setattr(module, "build_netcdf_encoding", build_encoding)
    monkeypatch.setattr(module, "write_netcdf_atomic", write_atomic)

    module.write_dpird()

    assert fake_ds.attrs == {}
    assert fake_ds.chunk_map == {"station": 96, "time": 52624}
    assert calls["open_dataset"] == (in_path, "h5netcdf")
    assert calls["build_encoding"] == (fake_ds, {"station": 96, "time": 52624}, 5)
    assert calls["write_atomic"] == (
        fake_ds,
        tmp_path / "vz_kerchunk/DPIRD/dpird_wa_stations.nc",
        {"encoded": {}},
    )


def test_write_dpird_raises_when_input_missing(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError, match="Missing DPIRD input file"):
        module.write_dpird()


def test_write_ecmwf_year_uses_strict_open_mfdataset_and_writes_atomic(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    fake_ds = FakeDataset()
    files = [tmp_path / "acacia_clean_data/ECMWF/2024/02/06.nc"]
    calls = {}

    def sorted_files(input_root, input_pattern, label):
        calls["sorted_files"] = (input_root, input_pattern, label)
        return files

    def open_mfdataset(files_arg, **kwargs):
        calls["open_mfdataset"] = (files_arg, kwargs)
        return fake_ds

    def validate_time(ds, label):
        calls["validate_time"] = (ds, label)

    def build_encoding(ds, chunk_map, complevel):
        calls["build_encoding"] = (ds, chunk_map, complevel)
        return {"encoded": {}}

    def write_atomic(ds, out_path, encoding):
        calls["write_atomic"] = (ds, out_path, encoding)

    monkeypatch.setattr(module, "sorted_ecmwf_input_files", sorted_files)
    monkeypatch.setattr(module.xr, "open_mfdataset", open_mfdataset)
    monkeypatch.setattr(module, "validate_unique_ascending_time", validate_time)
    monkeypatch.setattr(module, "build_netcdf_encoding", build_encoding)
    monkeypatch.setattr(module, "write_netcdf_atomic", write_atomic)

    module.write_ecmwf_year({
        "year": 2024,
        "input_pattern": "ECMWF/2024/**/*.nc",
        "output_pattern": "ECMWF/2024/ecmwf_op.nc",
    })

    assert calls["sorted_files"] == (
        tmp_path / "acacia_clean_data",
        "ECMWF/2024/**/*.nc",
        "ECMWF 2024",
    )
    assert calls["open_mfdataset"] == (
        files,
        {
            "concat_dim": "time",
            "combine": "nested",
            "parallel": True,
            "engine": "h5netcdf",
            "errors": "raise",
            "join": "exact",
            "combine_attrs": "drop_conflicts",
        },
    )
    assert calls["validate_time"] == (fake_ds, "ECMWF 2024")
    assert calls["build_encoding"] == (fake_ds, {"time": 4}, 5)
    assert calls["write_atomic"] == (
        fake_ds,
        tmp_path / "vz_kerchunk/ECMWF/2024/ecmwf_op.nc",
        {"encoded": {}},
    )


def test_main_writes_dpird_then_ecmwf_years_in_sorted_order(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    calls = []

    class FakeCluster:
        def __init__(self, **kwargs):
            calls.append(("cluster", kwargs))

        def close(self):
            calls.append("cluster_close")

    class FakeClient:
        def __init__(self, cluster):
            calls.append(("client", cluster.__class__.__name__))
            self.dashboard_link = "http://localhost:8787/status"

        def close(self):
            calls.append("client_close")

    monkeypatch.setattr(module, "LocalCluster", FakeCluster)
    monkeypatch.setattr(module, "Client", FakeClient)
    monkeypatch.setattr(module, "_runtime_cluster_config", lambda: (4, "8.00GB"))

    monkeypatch.setattr(module, "write_dpird", lambda: calls.append("dpird"))
    monkeypatch.setattr(
        module,
        "write_ecmwf_year",
        lambda spec: calls.append(spec["year"]),
    )

    module.main()

    assert calls == [
        ("cluster", {
            "n_workers": 4,
            "threads_per_worker": 1,
            "processes": True,
            "memory_limit": "8.00GB",
            "dashboard_address": ":8787",
        }),
        ("client", "FakeCluster"),
        "dpird",
        2024,
        2025,
        "client_close",
        "cluster_close",
    ]


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


def test_main_runs_only_requested_ecmwf_year(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    calls = []

    class FakeCluster:
        def __init__(self, **kwargs):
            calls.append(("cluster", kwargs))

        def close(self):
            calls.append("cluster_close")

    class FakeClient:
        def __init__(self, cluster):
            calls.append(("client", cluster.__class__.__name__))
            self.dashboard_link = "http://localhost:8787/status"

        def close(self):
            calls.append("client_close")

    monkeypatch.setattr(module, "LocalCluster", FakeCluster)
    monkeypatch.setattr(module, "Client", FakeClient)
    monkeypatch.setattr(module, "_runtime_cluster_config", lambda: (4, "8.00GB"))
    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(ecmwf_year=2025, dpird_only=False))
    monkeypatch.setattr(module, "write_dpird", lambda: calls.append("dpird"))
    monkeypatch.setattr(module, "write_ecmwf_year", lambda spec: calls.append(spec["year"]))

    module.main()

    assert "dpird" not in calls
    assert 2025 in calls
    assert 2024 not in calls


def test_main_raises_when_dpird_only_and_ecmwf_year_both_set(tmp_path, monkeypatch):
    module = _import_chunk_n_compress(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(ecmwf_year=2024, dpird_only=True))

    with pytest.raises(ValueError, match="either --dpird-only or --ecmwf-year"):
        module.main()
