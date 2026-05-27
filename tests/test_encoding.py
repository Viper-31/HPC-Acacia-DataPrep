import pytest
import numpy as np
import xarray as xr
import sys
import os

# Adjust import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.lib.encoding import build_netcdf_encoding, resolve_fill_value

def test_resolve_fill_value_nan_float32():
    val = resolve_fill_value("nan", "float32")
    assert type(val) == np.float32
    assert np.isnan(val)

def test_resolve_fill_value_nan_float64():
    val = resolve_fill_value(np.nan, "float64")
    assert type(val) == np.float64
    assert np.isnan(val)

def test_resolve_fill_value_0_str_pass():
    val = resolve_fill_value("0", "str")
    assert isinstance(val, (str, np.str_))
    assert val == "0"

def test_resolve_fill_value_int_pass():
    val = resolve_fill_value(0, "int")
    assert np.issubdtype(type(val), np.integer)
    assert val == 0

def test_resolve_fill_value_int_to_str_fails():
    with pytest.raises((TypeError, ValueError)):
        resolve_fill_value(0, "str")

def test_resolve_fill_value_float_pass():
    val = resolve_fill_value(9.969209968386869e+36, "float64")
    assert np.issubdtype(type(val), np.floating)
    assert np.isclose(val, 9.969209968386869e+36)

def test_resolve_fill_value_word_str_pass():
    val = resolve_fill_value("Amongus", "str")
    assert isinstance(val, (str, np.str_))
    assert val == "Amongus"


@pytest.mark.integration
def test_build_netcdf_encoding_sets_compression_for_data_vars_only():
    ds = xr.Dataset(
        data_vars={
            "airTemperature": (("station", "time"), np.ones((2, 3))),
        },
        coords={
            "station": ["a", "b"],
            "time": np.arange(3),
        },
    )

    encoding = build_netcdf_encoding(ds, {"time": 2}, complevel=5)

    assert set(encoding) == {"airTemperature"}
    assert encoding["airTemperature"]["chunksizes"] == (2, 2)
    assert encoding["airTemperature"]["shuffle"] is True
    assert any(
        key in encoding["airTemperature"]
        for key in ("compression", "compression_opts", "zlib", "lzf")
    )


def test_build_netcdf_encoding_uses_full_dimension_when_chunk_missing():
    ds = xr.Dataset(
        data_vars={
            "t2m": (("time", "latitude", "longitude"), np.ones((4, 2, 3))),
        }
    )

    encoding = build_netcdf_encoding(ds, {"time": 2}, complevel=5)

    assert encoding["t2m"]["chunksizes"] == (2, 2, 3)


def test_build_netcdf_encoding_empty_dataset_returns_empty_mapping():
    assert build_netcdf_encoding(xr.Dataset(), {"time": 4}, complevel=5) == {}


def test_build_zarr_encoding_applies_chunks_shards_and_fill_value_to_data_vars_only():
    from scripts.lib.encoding import build_zarr_encoding

    compressors = [object()]
    fill_value = np.float32(np.nan)
    ds = xr.Dataset(
        data_vars={
            "t2m": (("time", "latitude"), np.ones((6, 2), dtype=np.float32)),
        },
        coords={"time": np.arange(6), "latitude": [-31.0, -32.0]},
    )

    encoding = build_zarr_encoding(
        ds,
        chunk_map={"time": 2},
        shard_map={"time": 6},
        fill_value=fill_value,
        compressors=compressors,
    )

    assert set(encoding) == {"t2m"}
    assert encoding["t2m"] == {
        "chunks": (2, 2),
        "shards": (6, 2),
        "compressors": compressors,
        "fill_value": fill_value,
    }


def test_build_zarr_encoding_empty_dataset_returns_empty_mapping():
    from scripts.lib.encoding import build_zarr_encoding

    assert build_zarr_encoding(
        xr.Dataset(),
        chunk_map={"time": 1},
        shard_map={"time": 2},
        fill_value=None,
        compressors=[],
    ) == {}
