import json
import logging
from pathlib import Path
from typing import Any

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)

class StorageClient:
    """Wrapper around MinIO client."""

    def __init__(self) -> None:
        self.bucket = settings.minio_bucket
        # Remove http:// or https:// from endpoint for the Minio client constructor if present
        endpoint = settings.minio_endpoint
        if endpoint.startswith("http://"):
            endpoint = endpoint[len("http://"):]
        elif endpoint.startswith("https://"):
            endpoint = endpoint[len("https://"):]

        self.client = Minio(
            endpoint=endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def initialize(self) -> None:
        """Create the bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("Created MinIO bucket: %s", self.bucket)
        except S3Error as e:
            logger.error("MinIO connection error: %s", e)
            raise

    def upload_file(self, object_name: str, file_path: Path) -> None:
        """Upload a local file to MinIO."""
        logger.info("Uploading %s to MinIO path %s", file_path, object_name)
        self.client.fput_object(self.bucket, object_name, str(file_path))

    def download_file(self, object_name: str, file_path: Path) -> None:
        """Download an object from MinIO to a local file."""
        logger.info("Downloading MinIO path %s to %s", object_name, file_path)
        self.client.fget_object(self.bucket, object_name, str(file_path))

    def get_file_stream(self, object_name: str) -> Any:
        """Get a file stream from MinIO. Returns None if object doesn't exist."""
        logger.info("Streaming file from MinIO: %s", object_name)
        try:
            response = self.client.get_object(self.bucket, object_name)
            return response
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning("Object not found in MinIO: %s", object_name)
                return None
            logger.error("MinIO error streaming %s: %s", object_name, e)
            raise

    def upload_json(self, object_name: str, data: dict[str, Any] | list[Any]) -> None:
        """Upload a Python dictionary/list as a JSON object to MinIO."""
        import tempfile
        logger.debug("Uploading JSON to MinIO: %s", object_name)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = Path(tmp.name)
            
        try:
            self.upload_file(object_name, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
            
    def upload_text(self, object_name: str, text: str) -> None:
        """Upload a text string to MinIO."""
        import tempfile
        logger.debug("Uploading text (%d chars) to MinIO: %s", len(text), object_name)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
            
        try:
            self.upload_file(object_name, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects matching a prefix (e.g., a whole project directory)."""
        logger.info("Deleting all MinIO objects under prefix: %s", prefix)
        objects_to_delete = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        for obj in objects_to_delete:
            self.client.remove_object(self.bucket, obj.object_name)

# Global singleton
storage_client = StorageClient()
