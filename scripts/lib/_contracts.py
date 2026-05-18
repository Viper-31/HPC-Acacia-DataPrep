from pathlib import Path
import yaml
import os

def load_contracts():
    root = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[2]))
    contracts_path = root / "contracts" / "datasets.yml"
    with open(contracts_path, "r") as f:
        return yaml.safe_load(f)["datasets"]

def stage_spec(datasets, dataset_name, stage):
    return datasets[dataset_name]["stages"][stage]

def scratch_path(*parts):
    scratch = Path(os.environ.get("MYSCRATCH", "/tmp"))
    return scratch.joinpath(*parts)