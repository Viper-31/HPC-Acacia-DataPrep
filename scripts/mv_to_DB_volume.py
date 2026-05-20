import os
import yaml
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from databricks.sdk import WorkspaceClient

def yaml_load(path: Path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def upload_single_file(w: WorkspaceClient, local_path: str, target_path: str):
    # Upload file. Unity Catalog creates parent directories automatically.
    w.files.upload_from(
        target_path,
        local_path,
        overwrite=True,
        use_parallel=False
    )
    return target_path

def main():
    myscratch_env = os.environ.get("MYSCRATCH")
    if not myscratch_env:
        raise ValueError("MYSCRATCH environment variable is not set.")

    yaml_path = Path(myscratch_env) / "mv_to_databricks.yml"
    storage_dict = yaml_load(yaml_path)

    databricks_path_cfg = storage_dict["storages"]["databricks-volume"]
    catalog = databricks_path_cfg["catalog"]
    schema = databricks_path_cfg["schema"]
    volume = databricks_path_cfg["volume"]
    volume_target_folder = databricks_path_cfg["volume_target_folder"]

    databricks_destination_folder = f"/Volumes/{catalog}/{schema}/{volume}/{volume_target_folder}"

    setonix_path_cfg = storage_dict["storages"]["setonix-scratch"]
    zarr_folder = setonix_path_cfg["zarr_folder"]
    zarr_objects = setonix_path_cfg["zarr_objects"]

    setonix_zarr_object_path = Path(myscratch_env) / zarr_folder

    # Initialise Databricks Workspace client
    w = WorkspaceClient()
      
    w.files.create_directory(databricks_destination_folder)

    files_to_upload= []
    for zarr_name in zarr_objects:
        zarr_source_path = setonix_zarr_object_path / zarr_name

        if not zarr_source_path.exists() or not zarr_source_path.is_dir():
            print(f"Directory {zarr_source_path} not found or not a .zarr. Skipping")
            continue

        for local_file_path in zarr_source_path.rglob('*'):
            if local_file_path.is_file():
                rel_path = local_file_path.relative_to(setonix_zarr_object_path)
                # Combine using f-strings to ensure correct POSIX formatting for Databricks
                db_target_file_path = f"{databricks_destination_folder}/{rel_path.as_posix()}"
                files_to_upload.append((str(local_file_path), db_target_file_path))

    if not files_to_upload:
        raise FileNotFoundError("No files found to transfer")

    print(f"Found {len(files_to_upload)} files to upload to {databricks_destination_folder}")
    
    slurm_cpus= os.environ.get("SLURM_CPUS_PER_TASK")
    max_workers= int(slurm_cpus) if slurm_cpus else 4

    print(f"Using {max_workers} worker threads for multi-threaded file uploads ...")
    with ThreadPoolExecutor(max_workers= max_workers) as executor:
        futures= {
            executor.submit(upload_single_file, w, local, target): (local, target)
            for local, target in files_to_upload
        }

        for i, future in enumerate(as_completed(futures), 1):
            local, target= futures[future]
            try:
                future.result()
                # Print progress periodically
                if i % 100== 0 or i== len(files_to_upload):
                    print(f"Uploaed {i}/{len(files_to_upload)} files ...")
            except Exception as e:
                print(f"Error uploading {local} to {target}: {e}")
    print("Transfer complete")

if __name__ == '__main__':
    main()