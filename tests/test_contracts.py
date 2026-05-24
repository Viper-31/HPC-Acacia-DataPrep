import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.lib._contracts import load_contracts, scratch_path, stage_spec


def test_load_contracts_reads_datasets_from_repo_root_env(tmp_path, monkeypatch):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "datasets.yml").write_text(
        """
datasets:
  dpird:
    stages:
      chunk_n_compress:
        input_root: acacia_clean_data
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPO_ROOT", str(tmp_path))

    assert load_contracts() == {
        "dpird": {
            "stages": {
                "chunk_n_compress": {
                    "input_root": "acacia_clean_data",
                }
            }
        }
    }


def test_stage_spec_returns_named_stage():
    datasets = {
        "ecmwf": {
            "stages": {
                "chunk_n_compress": {
                    "chunk_map": {"time": 4},
                }
            }
        }
    }

    assert stage_spec(datasets, "ecmwf", "chunk_n_compress") == {
        "chunk_map": {"time": 4},
    }


def test_stage_spec_raises_key_error_for_unknown_stage():
    datasets = {"dpird": {"stages": {}}}

    with pytest.raises(KeyError):
        stage_spec(datasets, "dpird", "chunk_n_compress")


def test_scratch_path_uses_myscratch_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MYSCRATCH", str(tmp_path))

    assert scratch_path("vz_kerchunk", "DPIRD") == tmp_path / "vz_kerchunk" / "DPIRD"


def test_scratch_path_defaults_to_tmp_when_myscratch_unset(monkeypatch):
    monkeypatch.delenv("MYSCRATCH", raising=False)

    assert scratch_path("acacia_clean_data") == Path("/tmp") / "acacia_clean_data"
