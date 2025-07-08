"""
S3 Credential Service - Infrastructure Layer

Generates temporary AWS credentials scoped to user-specific S3 buckets/paths
based on JupyterHub authentication.
"""

import boto3
import json
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError

from .jupyterhub_auth import JupyterHubAuthService

log = logging.getLogger("aetherterm.infrastructure.s3_credential")


class S3CredentialService:
    """Service for generating temporary AWS credentials with S3 access scoped to user context."""

    def __init__(
        self,
        aws_region: str = "us-east-1",
        assume_role_arn: Optional[str] = None,
        bucket_prefix: str = "jupyter-user-",
        credential_duration_hours: int = 12,
        jupyterhub_auth: Optional[JupyterHubAuthService] = None,
    ):
        self.aws_region = aws_region
        self.assume_role_arn = assume_role_arn
        self.bucket_prefix = bucket_prefix
        self.credential_duration = timedelta(hours=credential_duration_hours)
        self.jupyterhub_auth = jupyterhub_auth or JupyterHubAuthService()

        # Initialize AWS clients
        try:
            self.sts_client = boto3.client("sts", region_name=aws_region)
            self.s3_client = boto3.client("s3", region_name=aws_region)
        except Exception as e:
            log.error(f"Failed to initialize AWS clients: {e}")
            raise

    async def get_user_s3_credentials(
        self, token: str, bucket_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate temporary S3 credentials for a user based on their JupyterHub token.

        Args:
            token: JupyterHub authentication token
            bucket_name: Optional specific bucket name, otherwise user-scoped bucket

        Returns:
            Dictionary with temporary AWS credentials and S3 access information
        """
        # Validate user token
        user_info = await self.jupyterhub_auth.validate_token(token)
        if not user_info:
            log.warning("Invalid JupyterHub token provided for S3 access")
            return None

        username = user_info.get("username")
        if not username:
            log.error("No username found in user info")
            return None

        try:
            # Determine bucket and path based on user context
            if bucket_name:
                # Use specified bucket with user-scoped path
                user_bucket = bucket_name
                user_path = f"users/{username}/"
            else:
                # Use user-specific bucket
                user_bucket = f"{self.bucket_prefix}{username}"
                user_path = ""

            # Generate scoped IAM policy
            policy = self._create_user_s3_policy(
                username=username,
                bucket_name=user_bucket,
                user_path=user_path,
                is_admin=user_info.get("admin", False),
            )

            # Generate temporary credentials
            session_name = f"s3-browser-{username}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

            if self.assume_role_arn:
                # Use role assumption for more controlled access
                credentials = await self._assume_role_with_policy(
                    role_arn=self.assume_role_arn, session_name=session_name, policy=policy
                )
            else:
                # Use STS federation token
                credentials = await self._get_federation_token(
                    session_name=session_name, policy=policy
                )

            if not credentials:
                return None

            # Ensure bucket exists and user has access
            await self._ensure_user_bucket_access(user_bucket, username)

            return {
                "credentials": {
                    "access_key_id": credentials["AccessKeyId"],
                    "secret_access_key": credentials["SecretAccessKey"],
                    "session_token": credentials["SessionToken"],
                    "expiration": credentials["Expiration"].isoformat(),
                },
                "s3_config": {
                    "region": self.aws_region,
                    "bucket": user_bucket,
                    "prefix": user_path,
                    "read_only": not user_info.get("admin", False),
                },
                "user_info": {
                    "username": username,
                    "is_admin": user_info.get("admin", False),
                    "groups": user_info.get("groups", []),
                },
            }

        except Exception as e:
            log.error(f"Failed to generate S3 credentials for user {username}: {e}")
            return None

    def _create_user_s3_policy(
        self, username: str, bucket_name: str, user_path: str, is_admin: bool = False
    ) -> str:
        """Create IAM policy document for user-scoped S3 access."""

        if is_admin:
            # Admin users get broader access
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:ListAllMyBuckets", "s3:GetBucketLocation"],
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:ListBucket",
                            "s3:GetBucketLocation",
                            "s3:GetBucketVersioning",
                        ],
                        "Resource": f"arn:aws:s3:::{bucket_name}",
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject",
                            "s3:GetObjectVersion",
                            "s3:DeleteObjectVersion",
                        ],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                    },
                ],
            }
        else:
            # Regular users get scoped access
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:ListBucket"],
                        "Resource": f"arn:aws:s3:::{bucket_name}",
                        "Condition": {"StringLike": {"s3:prefix": [f"{user_path}*"]}},
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/{user_path}*"],
                    },
                ],
            }

        return json.dumps(policy)

    async def _assume_role_with_policy(
        self, role_arn: str, session_name: str, policy: str
    ) -> Optional[Dict[str, Any]]:
        """Assume IAM role with inline policy for scoped access."""
        try:
            response = self.sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                Policy=policy,
                DurationSeconds=int(self.credential_duration.total_seconds()),
            )
            return response["Credentials"]
        except ClientError as e:
            log.error(f"Failed to assume role {role_arn}: {e}")
            return None

    async def _get_federation_token(
        self, session_name: str, policy: str
    ) -> Optional[Dict[str, Any]]:
        """Get federation token with inline policy."""
        try:
            response = self.sts_client.get_federation_token(
                Name=session_name,
                Policy=policy,
                DurationSeconds=int(self.credential_duration.total_seconds()),
            )
            return response["Credentials"]
        except ClientError as e:
            log.error(f"Failed to get federation token: {e}")
            return None

    async def _ensure_user_bucket_access(self, bucket_name: str, username: str) -> bool:
        """Ensure user bucket exists and is accessible."""
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            log.info(f"Bucket {bucket_name} exists and is accessible")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "404":
                log.info(f"Bucket {bucket_name} does not exist, creating it...")
                try:
                    if self.aws_region == "us-east-1":
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.aws_region},
                        )

                    # Set bucket policy for user access
                    await self._set_bucket_policy(bucket_name, username)
                    log.info(f"Created bucket {bucket_name} for user {username}")
                    return True
                except ClientError as create_error:
                    log.error(f"Failed to create bucket {bucket_name}: {create_error}")
                    return False
            else:
                log.error(f"Error accessing bucket {bucket_name}: {e}")
                return False

    async def _set_bucket_policy(self, bucket_name: str, username: str) -> None:
        """Set bucket policy to allow user access."""
        try:
            bucket_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": f"UserAccess{username}",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": f"arn:aws:sts::{self._get_account_id()}:federated-user/{username}"
                        },
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject",
                            "s3:ListBucket",
                        ],
                        "Resource": [
                            f"arn:aws:s3:::{bucket_name}",
                            f"arn:aws:s3:::{bucket_name}/*",
                        ],
                    }
                ],
            }

            self.s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(bucket_policy))

        except ClientError as e:
            log.warning(f"Could not set bucket policy for {bucket_name}: {e}")

    def _get_account_id(self) -> str:
        """Get current AWS account ID."""
        try:
            return self.sts_client.get_caller_identity()["Account"]
        except ClientError:
            return "123456789012"  # Fallback for testing

    async def list_user_buckets(self, token: str) -> Optional[list]:
        """List S3 buckets accessible to the user."""
        user_info = await self.jupyterhub_auth.validate_token(token)
        if not user_info:
            return None

        username = user_info.get("username")
        if not username:
            return None

        try:
            response = self.s3_client.list_buckets()
            buckets = response.get("Buckets", [])

            if user_info.get("admin", False):
                # Admin can see all buckets
                return [
                    {"name": bucket["Name"], "created": bucket["CreationDate"].isoformat()}
                    for bucket in buckets
                ]
            else:
                # Regular users see only their buckets
                user_buckets = [
                    {"name": bucket["Name"], "created": bucket["CreationDate"].isoformat()}
                    for bucket in buckets
                    if bucket["Name"].startswith(f"{self.bucket_prefix}{username}")
                ]
                return user_buckets

        except ClientError as e:
            log.error(f"Failed to list buckets for user {username}: {e}")
            return None

    async def check_aws_connectivity(self) -> bool:
        """Check if AWS services are accessible."""
        try:
            self.sts_client.get_caller_identity()
            return True
        except (ClientError, NoCredentialsError):
            return False
