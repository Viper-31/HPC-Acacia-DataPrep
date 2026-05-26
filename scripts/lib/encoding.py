from typing import Any, Mapping, Sequence

import numpy as np
import xarray as xr
import hdf5plugin

EncodingMap= dict[str, dict[str, Any]]

def resolve_fill_value(value: object, dtype: np.dtype | str) -> object:
    if value == "nan" or (isinstance(value, float) and np.isnan(value)):
        return np.dtype(dtype).type(np.nan)
        
    target_dtype = np.dtype(dtype)
    
    # Strictly prevent int/float being silently cast to string
    if target_dtype.kind in ('U', 'S', 'O') and not isinstance(value, str):
        raise TypeError(f"Type mismatch: dtype is {dtype} but fill_value is {type(value).__name__}")
        
    return target_dtype.type(value)

def build_netcdf_encoding(
        ds: xr.Dataset, 
        chunk_map: Mapping[str, int],
        complevel: int
        ) -> EncodingMap:
    enc = {}
    for var in ds.data_vars:
        var_dims= ds[var].dims
        var_chunks= tuple(chunk_map.get(dim, ds[var].sizes[dim]) for dim in var_dims)

        zstd_params = hdf5plugin.Zstd(clevel=complevel)

        enc[var] = {
            **zstd_params,
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
