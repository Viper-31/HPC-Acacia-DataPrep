from pathlib import Path
import os
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.lib.pipeline import (
    sort_and_validate_ecmwf_paths,
    sorted_ecmwf_input_files,
    validate_unique_ascending_time,
    write_netcdf_atomic,
)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_sort_and_validate_ecmwf_paths_returns_lexicographic_order(tmp_path):
    root = tmp_path / "acacia_clean_data"
    later = _touch(root / "ECMWF/2024/02/13.nc")
    earlier = _touch(root / "ECMWF/2024/02/06.nc")

    assert sort_and_validate_ecmwf_paths([later, earlier], root, "ECMWF 2024") == [
        earlier,
        later,
    ]


def test_sorted_ecmwf_input_files_raises_when_no_files_match(tmp_path):
    with pytest.raises(FileNotFoundError, match="No ECMWF input files"):
        sorted_ecmwf_input_files(tmp_path, "ECMWF/2024/**/*.nc", "ECMWF 2024")


def test_sort_and_validate_ecmwf_paths_rejects_invalid_path_shape(tmp_path):
    root = tmp_path / "acacia_clean_data"
    invalid = _touch(root / "ECMWF/2024/2/06.nc")

    with pytest.raises(ValueError, match="Invalid ECMWF input path"):
        sort_and_validate_ecmwf_paths([invalid], root, "ECMWF 2024")


def test_sort_and_validate_ecmwf_paths_rejects_duplicate_dates(tmp_path):
    root = tmp_path / "acacia_clean_data"
    path = _touch(root / "ECMWF/2024/02/06.nc")

    with pytest.raises(ValueError, match="Duplicate ECMWF input date"):
        sort_and_validate_ecmwf_paths([path, path], root, "ECMWF 2024")


@pytest.mark.integration
def test_validate_unique_ascending_time_accepts_strictly_increasing_time():
    ds = xr.Dataset(
        {"t2m": ("time", np.array([1.0, 2.0]))},
        coords={"time": np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[D]")},
    )

    validate_unique_ascending_time(ds, "ECMWF 2024")


@pytest.mark.integration
def test_validate_unique_ascending_time_rejects_duplicate_time():
    ds = xr.Dataset(
        {"t2m": ("time", np.array([1.0, 2.0]))},
        coords={"time": np.array(["2024-01-01", "2024-01-01"], dtype="datetime64[D]")},
    )

    with pytest.raises(ValueError, match="must be unique"):
        validate_unique_ascending_time(ds, "ECMWF 2024")


@pytest.mark.integration
def test_validate_unique_ascending_time_rejects_decreasing_time():
    ds = xr.Dataset(
        {"t2m": ("time", np.array([1.0, 2.0]))},
        coords={"time": np.array(["2024-01-02", "2024-01-01"], dtype="datetime64[D]")},
    )

    with pytest.raises(ValueError, match="strictly ascending"):
        validate_unique_ascending_time(ds, "ECMWF 2024")


@pytest.mark.integration
def test_validate_unique_ascending_time_requires_indexed_time_coordinate():
    ds = xr.Dataset({"t2m": ("x", np.array([1.0, 2.0]))})

    with pytest.raises(ValueError, match="indexed 'time' coordinate"):
        validate_unique_ascending_time(ds, "ECMWF 2024")


@pytest.mark.integration
def test_write_netcdf_atomic_replaces_existing_output_after_success(tmp_path):
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ecmwf_op.nc"
    out_path.write_text("old failed output", encoding="utf-8")

    result = write_netcdf_atomic(ds, out_path, encoding={})

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > len("old failed output")
    assert not (tmp_path / ".ecmwf_op.nc.tmp").exists()

 
@pytest.mark.integration
def test_write_netcdf_atomic_removes_temp_and_keeps_existing_output_on_failure(
    tmp_path,
    monkeypatch,
):
    ds = xr.Dataset({"t2m": ("time", np.array([1.0, 2.0]))})
    out_path = tmp_path / "ecmwf_op.nc"
    out_path.write_text("previous complete output", encoding="utf-8")

    def fail_to_netcdf(self, path, *args, **kwargs):
        Path(path).write_text("partial output", encoding="utf-8")
        raise OSError("boom")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail_to_netcdf)

    with pytest.raises(RuntimeError, match="Failed writing NetCDF artifact"):
        write_netcdf_atomic(ds, out_path, encoding={})

    assert out_path.read_text(encoding="utf-8") == "previous complete output"
    assert not (tmp_path / ".ecmwf_op.nc.tmp").exists()
