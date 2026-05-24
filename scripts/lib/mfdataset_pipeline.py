from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
import re

import xarray as xr


_ECMWF_PATH_RE = re.compile(r"^ECMWF/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})\.nc$")


def sort_and_validate_ecmwf_paths(
    paths: Iterable[Path | str],
    input_root: Path | str,
    label: str,
) -> list[Path]:
    root = Path(input_root)
    sorted_paths = sorted(Path(path) for path in paths)

    if not sorted_paths:
        raise FileNotFoundError(f"No ECMWF input files provided for {label}")

    seen_dates: dict[str, Path] = {}
    for path in sorted_paths:
        try:
            rel_path = path.relative_to(root).as_posix()
        except ValueError:
            rel_path = path.as_posix()

        match = _ECMWF_PATH_RE.fullmatch(rel_path)
        if match is None:
            raise ValueError(
                f"Invalid ECMWF input path for {label}: {rel_path}. "
                "Expected ECMWF/YYYY/MM/DD.nc"
            )

        date_key = "-".join(match.group(part) for part in ("year", "month", "day"))
        if date_key in seen_dates:
            raise ValueError(
                f"Duplicate ECMWF input date for {label}: {date_key} "
                f"({seen_dates[date_key]} and {path})"
            )
        seen_dates[date_key] = path

    return sorted_paths


def sorted_ecmwf_input_files(
    input_root: Path | str,
    input_pattern: str,
    label: str,
) -> list[Path]:
    root = Path(input_root)
    files = list(root.glob(input_pattern))

    if not files:
        raise FileNotFoundError(
            f"No ECMWF input files found for {label}: {root}/{input_pattern}"
        )

    return sort_and_validate_ecmwf_paths(files, root, label)


def validate_unique_ascending_time(ds: xr.Dataset, label: str) -> None:
    if "time" not in ds.indexes:
        raise ValueError(f"{label} must have an indexed 'time' coordinate")

    time_index = ds.indexes["time"]
    if not time_index.is_unique:
        raise ValueError(f"{label} time coordinate must be unique")

    if not time_index.is_monotonic_increasing:
        raise ValueError(f"{label} time coordinate must be strictly ascending")


def write_netcdf_atomic(
    ds: xr.Dataset,
    out_path: Path | str,
    encoding: Mapping[str, Mapping[str, Any]] | None,
    *,
    engine: str = "h5netcdf",
    netcdf_format: str = "NETCDF4",
) -> Path:
    final_path = Path(out_path)
    tmp_path = final_path.with_name(f".{final_path.name}.tmp")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if tmp_path.exists():
        tmp_path.unlink()

    try:
        ds.to_netcdf(
            path=tmp_path,
            engine=engine,
            format=netcdf_format,
            encoding=encoding,
        )
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Failed writing NetCDF artifact {final_path}: {exc}") from exc

    tmp_path.replace(final_path)
    return final_path
