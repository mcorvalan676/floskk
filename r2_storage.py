import boto3
from botocore.config import Config as BotoConfig

from config import Config


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{Config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=Config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=Config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def save_cv_object(key, contents):
    _client().put_object(
        Bucket=Config.R2_BUCKET,
        Key=key,
        Body=contents,
        ContentType="application/pdf",
    )


def load_cv_object(key):
    response = _client().get_object(Bucket=Config.R2_BUCKET, Key=key)
    body = response["Body"]
    try:
        return body.read()
    finally:
        body.close()
