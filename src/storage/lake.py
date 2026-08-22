

from __future__ import annotations

import os

from dotenv import load_dotenv
from pyarrow.fs import S3FileSystem

load_dotenv()

LAYERS = ("bronze", "silver", "gold")


def get_lake_filesystem() -> S3FileSystem:
  
    return S3FileSystem(
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        endpoint_override=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        scheme=os.getenv("MINIO_SCHEME", "http"),
    )


def lake_path(layer: str, dataset: str) -> str:
    
    if layer not in LAYERS:
        raise ValueError(f"Couche inconnue : {layer!r}. Attendu : {LAYERS}")
    return f"{layer}/{dataset}"