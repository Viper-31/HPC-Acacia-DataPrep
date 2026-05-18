from typing import Any, Mapping, Sequence
import numpy as np
import xarray as xr

EncodingMap= dict[str, dict[str, Any]]

def resolve_fill_value(value: object, dtype: np.dtype | str) -> object:
    if value == "nan":
        return np.array(np.nan, dtype=dtype).item()
    return value

def build_netcdf_encoding(
        ds: xr.Dataset, 
        chunk_map: Mapping[str, int],
        complevel: int
        ) -> EncodingMap:
    enc = {}
    for var in ds.data_vars:
        var_dims= ds[var].dims
        var_chunks= tuple(chunk_map.get(dim, ds[var].sizes[dim]) for dim in var_dims)
        enc[var] = {
            "zlib": True,
            "complevel": complevel,
            "shuffle": True,
            "chunksizes": var_chunks
        }
    return enc

def build_zarr_encoding(
        ds: xr.Dataset,
        chunk_map: Mapping[str, int], 
        shard_map: Mapping[str, int],
        fill_value: object, 
        compressors: Sequence[Any]
        ) -> EncodingMap:
    enc = {}
    for var in ds.data_vars:
        var_dims= ds[var].dims
        var_chunks = tuple(chunk_map.get(dim, ds[var].sizes[dim]) for dim in var_dims)
        var_shards = tuple(shard_map.get(dim, ds[var].sizes[dim]) for dim in var_dims)
        enc[var] = {
            "chunks": var_chunks,
            "shards": var_shards,
            "compressors": compressors,
            "fill_value": fill_value,
        }
    return enc