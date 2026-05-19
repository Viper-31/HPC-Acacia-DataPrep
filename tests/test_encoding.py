import pytest
import numpy as np
import sys
import os

# Adjust import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from lib.encoding import resolve_fill_value

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
