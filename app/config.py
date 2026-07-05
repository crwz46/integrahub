from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "IntegraHub"
    app_version: str = "1.0.0"
    debug: bool = True

    # Auth
    jwt_secret: str = "integrahub-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # Webhook
    webhook_retry_max_attempts: int = 5
    webhook_retry_base_delay_seconds: int = 2
    webhook_signature_header: str = "x-integrahub-signature"

    # File storage
    upload_dir: str = "./data/uploads"
    max_file_size_mb: int = 10
    presigned_url_expiry_minutes: int = 30

    # Queue
    queue_max_retries: int = 3
    queue_poll_interval_seconds: int = 5

    # Storage
    data_path: str = "./data"


settings = Settings()
