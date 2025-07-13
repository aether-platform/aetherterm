"""
S3 Browser API Endpoints

FastAPI routes for S3 file browser functionality with JupyterHub authentication.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from aetherterm.agentserver.infrastructure.config.di_container import get_container

log = logging.getLogger("aetherterm.endpoint.s3_browser")

router = APIRouter(prefix="/api/s3", tags=["s3-browser"])


class S3Credentials(BaseModel):
    """S3 credentials response model."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: str


class S3Config(BaseModel):
    """S3 configuration response model."""

    region: str
    bucket: str
    prefix: str
    read_only: bool


class S3CredentialsResponse(BaseModel):
    """Complete S3 credentials response."""

    credentials: S3Credentials
    s3_config: S3Config
    user_info: Dict[str, Any]


class S3Object(BaseModel):
    """S3 object metadata."""

    key: str
    size: int
    last_modified: str
    etag: str
    storage_class: str
    is_folder: bool = False


class S3ListResponse(BaseModel):
    """S3 list objects response."""

    objects: List[S3Object]
    folders: List[str]
    prefix: str
    has_more: bool = False
    next_marker: Optional[str] = None


def extract_jupyterhub_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract JupyterHub token from Authorization header."""
    if not authorization:
        return None

    if authorization.startswith("Bearer "):
        return authorization[7:]
    if authorization.startswith("token "):
        return authorization[6:]

    return authorization


@router.get("/credentials", response_model=S3CredentialsResponse)
async def get_s3_credentials(
    bucket: Optional[str] = Query(None, description="Specific bucket name"),
    authorization: Optional[str] = Header(None),
):
    """
    Get temporary S3 credentials for the authenticated user.

    Generates scoped AWS credentials based on JupyterHub user authentication.
    """
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        credentials = await s3_service.get_user_s3_credentials(token, bucket)
        if not credentials:
            raise HTTPException(status_code=403, detail="Failed to generate S3 credentials")

        return S3CredentialsResponse(**credentials)

    except Exception as e:
        log.error(f"Error generating S3 credentials: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/buckets")
async def list_buckets(authorization: Optional[str] = Header(None)):
    """List S3 buckets accessible to the user."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        buckets = await s3_service.list_user_buckets(token)
        if buckets is None:
            raise HTTPException(status_code=403, detail="Failed to list buckets")

        return {"buckets": buckets}

    except Exception as e:
        log.error(f"Error listing buckets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/objects/{bucket_name:path}", response_model=S3ListResponse)
async def list_objects(
    bucket_name: str,
    prefix: str = Query("", description="Object prefix/folder path"),
    max_keys: int = Query(100, description="Maximum number of objects to return"),
    marker: Optional[str] = Query(None, description="Continuation marker"),
    authorization: Optional[str] = Header(None),
):
    """List objects in an S3 bucket with optional prefix filtering."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        # Get user credentials to access S3
        credentials_data = await s3_service.get_user_s3_credentials(token, bucket_name)
        if not credentials_data:
            raise HTTPException(status_code=403, detail="Access denied to bucket")

        # Use the temporary credentials to list objects
        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials_data["credentials"]["access_key_id"],
            aws_secret_access_key=credentials_data["credentials"]["secret_access_key"],
            aws_session_token=credentials_data["credentials"]["session_token"],
            region_name=credentials_data["s3_config"]["region"],
        )

        # List objects with pagination
        list_params = {
            "Bucket": bucket_name,
            "Prefix": prefix,
            "MaxKeys": max_keys,
            "Delimiter": "/",  # This helps separate folders from files
        }

        if marker:
            list_params["Marker"] = marker

        response = s3_client.list_objects_v2(**list_params)

        # Process objects
        objects = []
        for obj in response.get("Contents", []):
            objects.append(
                S3Object(
                    key=obj["Key"],
                    size=obj["Size"],
                    last_modified=obj["LastModified"].isoformat(),
                    etag=obj["ETag"].strip('"'),
                    storage_class=obj.get("StorageClass", "STANDARD"),
                    is_folder=False,
                )
            )

        # Process folders (common prefixes)
        folders = [prefix["Prefix"] for prefix in response.get("CommonPrefixes", [])]

        return S3ListResponse(
            objects=objects,
            folders=folders,
            prefix=prefix,
            has_more=response.get("IsTruncated", False),
            next_marker=response.get("NextContinuationToken"),
        )

    except Exception as e:
        log.error(f"Error listing objects in bucket {bucket_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list objects")


@router.get("/object/{bucket_name:path}")
async def get_object_url(
    bucket_name: str,
    key: str = Query(..., description="Object key"),
    expires_in: int = Query(3600, description="URL expiration time in seconds"),
    authorization: Optional[str] = Header(None),
):
    """Generate a presigned URL for downloading an S3 object."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        # Get user credentials
        credentials_data = await s3_service.get_user_s3_credentials(token, bucket_name)
        if not credentials_data:
            raise HTTPException(status_code=403, detail="Access denied to bucket")

        # Generate presigned URL
        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials_data["credentials"]["access_key_id"],
            aws_secret_access_key=credentials_data["credentials"]["secret_access_key"],
            aws_session_token=credentials_data["credentials"]["session_token"],
            region_name=credentials_data["s3_config"]["region"],
        )

        presigned_url = s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket_name, "Key": key}, ExpiresIn=expires_in
        )

        return {"download_url": presigned_url, "expires_in": expires_in}

    except Exception as e:
        log.error(f"Error generating presigned URL for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.post("/upload/{bucket_name:path}")
async def upload_object(
    bucket_name: str,
    key: str = Query(..., description="Object key/path"),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """Upload a file to S3 bucket."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        # Get user credentials
        credentials_data = await s3_service.get_user_s3_credentials(token, bucket_name)
        if not credentials_data:
            raise HTTPException(status_code=403, detail="Access denied to bucket")

        if credentials_data["s3_config"]["read_only"]:
            raise HTTPException(status_code=403, detail="Read-only access to this bucket")

        # Upload file
        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials_data["credentials"]["access_key_id"],
            aws_secret_access_key=credentials_data["credentials"]["secret_access_key"],
            aws_session_token=credentials_data["credentials"]["session_token"],
            region_name=credentials_data["s3_config"]["region"],
        )

        # Read file content
        file_content = await file.read()

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=file_content,
            ContentType=file.content_type or "application/octet-stream",
        )

        return {
            "message": "File uploaded successfully",
            "bucket": bucket_name,
            "key": key,
            "size": len(file_content),
        }

    except Exception as e:
        log.error(f"Error uploading file {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.delete("/object/{bucket_name:path}")
async def delete_object(
    bucket_name: str,
    key: str = Query(..., description="Object key"),
    authorization: Optional[str] = Header(None),
):
    """Delete an object from S3 bucket."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        # Get user credentials
        credentials_data = await s3_service.get_user_s3_credentials(token, bucket_name)
        if not credentials_data:
            raise HTTPException(status_code=403, detail="Access denied to bucket")

        if credentials_data["s3_config"]["read_only"]:
            raise HTTPException(status_code=403, detail="Read-only access to this bucket")

        # Delete object
        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials_data["credentials"]["access_key_id"],
            aws_secret_access_key=credentials_data["credentials"]["secret_access_key"],
            aws_session_token=credentials_data["credentials"]["session_token"],
            region_name=credentials_data["s3_config"]["region"],
        )

        s3_client.delete_object(Bucket=bucket_name, Key=key)

        return {"message": "Object deleted successfully", "bucket": bucket_name, "key": key}

    except Exception as e:
        log.error(f"Error deleting object {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete object")


@router.post("/folder/{bucket_name:path}")
async def create_folder(
    bucket_name: str,
    folder_path: str = Query(..., description="Folder path (must end with /)"),
    authorization: Optional[str] = Header(None),
):
    """Create a folder (empty object) in S3 bucket."""
    token = extract_jupyterhub_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    if not folder_path.endswith("/"):
        folder_path += "/"

    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        # Get user credentials
        credentials_data = await s3_service.get_user_s3_credentials(token, bucket_name)
        if not credentials_data:
            raise HTTPException(status_code=403, detail="Access denied to bucket")

        if credentials_data["s3_config"]["read_only"]:
            raise HTTPException(status_code=403, detail="Read-only access to this bucket")

        # Create folder by putting empty object
        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials_data["credentials"]["access_key_id"],
            aws_secret_access_key=credentials_data["credentials"]["secret_access_key"],
            aws_session_token=credentials_data["credentials"]["session_token"],
            region_name=credentials_data["s3_config"]["region"],
        )

        s3_client.put_object(Bucket=bucket_name, Key=folder_path, Body=b"")

        return {
            "message": "Folder created successfully",
            "bucket": bucket_name,
            "folder": folder_path,
        }

    except Exception as e:
        log.error(f"Error creating folder {folder_path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.get("/status")
async def get_s3_status():
    """Check S3 service status and AWS connectivity."""
    container = get_container()
    s3_service = container.infrastructure.s3_credential_service()

    try:
        aws_available = await s3_service.check_aws_connectivity()
        return {
            "status": "ok" if aws_available else "error",
            "aws_available": aws_available,
            "message": "S3 service is operational" if aws_available else "AWS services unavailable",
        }
    except Exception as e:
        log.error(f"Error checking S3 status: {e}")
        return {"status": "error", "aws_available": False, "message": f"S3 service error: {e!s}"}
