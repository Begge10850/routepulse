USE ROLE ACCOUNTADMIN;

-- Replace <AWS_ACCOUNT_ID> with the AWS account that owns the IAM role before
-- running this worksheet. Never commit AWS credentials or temporary tokens.
CREATE STORAGE INTEGRATION IF NOT EXISTS ROUTEPULSE_S3_INTEGRATION
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'S3'
    ENABLED = TRUE
    STORAGE_AWS_ROLE_ARN =
        'arn:aws:iam::<AWS_ACCOUNT_ID>:role/RoutePulseSnowflakeRole'
    STORAGE_ALLOWED_LOCATIONS = (
        's3://routepulse-raw-eu-central-1-9b355f4a/processed/realtime/'
    )
    COMMENT = 'Read-only integration for RoutePulse processed Parquet data';

DESC INTEGRATION ROUTEPULSE_S3_INTEGRATION;
