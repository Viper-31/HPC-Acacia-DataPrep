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
      to_zarr:
        input_root: acacia_clean_data
        input_pattern: DPIRD/DPIRD_final_stations.nc
        output_root: zarr_objects
        chunk_map: {station: 192, time: 26312}
        shard_map: {station: 192, time: 52624}
        fill_value: "nan"
        fill_value_dtype: "float64"
  ecmwf:
    stages:
      to_zarr:
        input_root: acacia_clean_data
        input_pattern: ECMWF/**/*.nc
        output_root: zarr_objects
        chunk_map: {time: 6, step: 113, latitude: 111, longitude: 151}
        shard_map: {time: 120, step: 113, latitude: 111, longitude: 151}
        fill_value: "nan"
        fill_value_dtype: "float32"
""".strip(),
        encoding="utf-8",
    )


def _import_to_zarr(tmp_path, monkeypatch):
    _write_contract(tmp_path)
    monkeypatch.setenv("REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("MYSCRATCH", str(tmp_path))
    sys.modules.pop("to_zarr", None)
    return importlib.import_module("to_zarr")


class FakeDataset:
    def __init__(self):
        self.chunk_map = None
        self.zarr_call = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def chunk(self, chunk_map):
        self.chunk_map = chunk_map
        return self

    def to_zarr(self, out_path, **kwargs):
        self.zarr_call = (out_path, kwargs)


def test_dpird_to_zarr_builds_encoding_and_writes_zarr(tmp_path, monkeypatch):
    module = _import_to_zarr(tmp_path, monkeypatch)
    dpird_path = tmp_path / "acacia_clean_data/DPIRD/DPIRD_final_stations.nc"
    dpird_path.parent.mkdir(parents=True)
    dpird_path.write_text("placeholder", encoding="utf-8")
    fake_ds = FakeDataset()
    calls = {}

    def open_dataset(path, engine):
        calls["open_dataset"] = (path, engine)
        return fake_ds

    def resolve_fill_value(value, dtype):
        calls["resolve_fill_value"] = (value, dtype)
        return "resolved-fill"

    def build_encoding(ds, chunk_map, shard_map, fill_value, compressors):
        calls["build_encoding"] = (ds, chunk_map, shard_map, fill_value, compressors)
        return {"encoded": {}}

    monkeypatch.setattr(module.xr, "open_dataset", open_dataset)
    monkeypatch.setattr(module, "resolve_fill_value", resolve_fill_value)
    monkeypatch.setattr(module, "build_zarr_encoding", build_encoding)

    module.dpird_to_zarr()

    assert calls["open_dataset"] == (dpird_path, "h5netcdf")
    assert calls["resolve_fill_value"] == ("nan", "float64")
    assert calls["build_encoding"] == (
        fake_ds,
        {"station": 192, "time": 26312},
        {"station": 192, "time": 52624},
        "resolved-fill",
        module.compressors,
    )
    assert fake_ds.zarr_call == (
        tmp_path / "zarr_objects/dpird.zarr",
        {
            "zarr_format": 3,
            "encoding": {"encoded": {}},
            "mode": "w",
            "consolidated": False,
        },
    )


def test_dpird_to_zarr_raises_when_input_missing(tmp_path, monkeypatch):
    module = _import_to_zarr(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError, match="chunk_n_compress.sh should have ran"):
        module.dpird_to_zarr()


def test_ecmwf_to_zarr_opens_mfdataset_chunks_and_writes_zarr(tmp_path, monkeypatch):
    module = _import_to_zarr(tmp_path, monkeypatch)
    input_root = tmp_path / "acacia_clean_data"
    files = [
        input_root / "ECMWF/2024/01/01.nc",
        input_root / "ECMWF/2024/01/02.nc",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    fake_ds = FakeDataset()
    calls = {}

    def open_mfdataset(files_arg, **kwargs):
        calls["open_mfdataset"] = (files_arg, kwargs)
        return fake_ds

    def resolve_fill_value(value, dtype):
        calls["resolve_fill_value"] = (value, dtype)
        return "resolved-fill"

    def build_encoding(ds, chunk_map, shard_map, fill_value, compressors):
        calls["build_encoding"] = (ds, chunk_map, shard_map, fill_value, compressors)
        return {"encoded": {}}

    monkeypatch.setattr(module.xr, "open_mfdataset", open_mfdataset)
    monkeypatch.setattr(module, "resolve_fill_value", resolve_fill_value)
    monkeypatch.setattr(module, "build_zarr_encoding", build_encoding)

    module.ecmwf_to_zarr()

    assert calls["open_mfdataset"] == (
        sorted(files),
        {
            "concat_dim": "time",
            "combine": "nested",
            "parallel": True,
            "engine": "h5netcdf",
        },
    )
    assert fake_ds.chunk_map == {"time": 120, "step": 113, "latitude": 111, "longitude": 151}
    assert calls["resolve_fill_value"] == ("nan", "float32")
    assert calls["build_encoding"] == (
        fake_ds,
        {"time": 6, "step": 113, "latitude": 111, "longitude": 151},
        {"time": 120, "step": 113, "latitude": 111, "longitude": 151},
        "resolved-fill",
        module.compressors,
    )
    assert fake_ds.zarr_call == (
        tmp_path / "zarr_objects/ecmwf.zarr",
        {
            "zarr_format": 3,
            "encoding": {"encoded": {}},
            "mode": "w",
            "consolidated": False,
        },
    )


def test_ecmwf_to_zarr_raises_when_not_enough_inputs(tmp_path, monkeypatch):
    module = _import_to_zarr(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError, match="Not enough ECMWF files"):
        module.ecmwf_to_zarr()


def test_main_runs_dpird_then_ecmwf_with_dry_run_flag(tmp_path, monkeypatch):
    module = _import_to_zarr(tmp_path, monkeypatch)
    calls = []

    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(dry_run=True))
    monkeypatch.setattr(module, "dpird_to_zarr", lambda dry_run: calls.append(("dpird", dry_run)))
    monkeypatch.setattr(module, "ecmwf_to_zarr", lambda dry_run: calls.append(("ecmwf", dry_run)))

    module.main()

    assert calls == [("dpird", True), ("ecmwf", True)]
