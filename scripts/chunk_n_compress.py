import xarray as xr

from lib._contracts import load_contracts, stage_spec, scratch_path
from lib.encoding import build_netcdf_encoding
from lib.mfdataset_pipeline import sorted_ecmwf_input_files, validate_unique_ascending_time, write_netcdf_atomic

DATASETS= load_contracts()
DPIRD_SPEC= stage_spec(DATASETS, "dpird", "chunk_n_compress")
ECMWF_SPEC= stage_spec(DATASETS, "ecmwf", "chunk_n_compress")


def write_dpird():
    in_path = scratch_path(DPIRD_SPEC["input_root"]) / DPIRD_SPEC["input_pattern"]
    out_path = scratch_path(DPIRD_SPEC["output_root"]) / DPIRD_SPEC["output_pattern"]
    dpird_chunk_map = DPIRD_SPEC["chunk_map"]
    dpird_complevel = DPIRD_SPEC["complevel"]

    if not in_path.exists():
        raise FileNotFoundError(f"Missing DPIRD input file: {in_path}")
    
    with xr.open_dataset(in_path, engine= "h5netcdf") as ds:
        ds.attrs.clear()
        ds = ds.chunk(dpird_chunk_map)
        dpird_encoding= build_netcdf_encoding(ds, dpird_chunk_map, dpird_complevel)
        write_netcdf_atomic(ds, out_path, encoding= dpird_encoding)
    print(f"Completed DPIRD: {in_path} -> {out_path}")


def write_ecmwf_year(ecmwf_year_spec):
    year = ecmwf_year_spec["year"]
    label = f"ECMWF {year}"
    input_root = scratch_path(ECMWF_SPEC["input_root"])
    input_pattern = ecmwf_year_spec["input_pattern"]
    out_path = scratch_path(ECMWF_SPEC["output_root"]) / ecmwf_year_spec["output_pattern"]
    ecmwf_chunk_map = ECMWF_SPEC["chunk_map"]
    ecmwf_complevel = ECMWF_SPEC["complevel"]

    files = sorted_ecmwf_input_files(input_root, input_pattern, label)
    
    with xr.open_mfdataset(
        files,
        concat_dim="time",
        combine="nested",
        parallel=True,
        engine="h5netcdf",
        errors="raise",
        join="exact",
        combine_attrs="drop_conflicts", # If dataset/dataarray attrs name:value don't match they are dropped 
    ) as ds:
        validate_unique_ascending_time(ds,label)
        ds = ds.chunk(ecmwf_chunk_map)
        ecmwf_encoding = build_netcdf_encoding(ds, ecmwf_chunk_map, ecmwf_complevel)
        write_netcdf_atomic(ds, out_path, encoding=ecmwf_encoding)

    print(f"Completed {label}: {len(files)} inputs -> {out_path}")

def main():  
    write_dpird()

    for ecmwf_year_spec in sorted(ECMWF_SPEC["years"], key=lambda item: item["year"]):
        write_ecmwf_year(ecmwf_year_spec)

if __name__ == "__main__":
    main()
