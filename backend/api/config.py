import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Settings
    api_title: str = "Medical Terminology Standardization Engine API"
    api_version: str = "1.0.0"
    api_description: str = "API for mapping medical terms to standardized terminologies"
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    workers: int = 1
    
    # CORS Settings
    cors_origins: list = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]
    
    # Security Settings
    allowed_hosts: list = ["*"]
    
    # File Upload Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    upload_dir: str = "uploads"
    results_dir: str = "results"
    
    # Batch Processing Settings  
    batch_size: int = 1000  # Increased from 50 to eliminate chunking issues
    max_batch_terms: int = 2000  # Increased to handle larger batches
    
    # Cache Settings
    enable_cache: bool = True
    cache_ttl: int = 3600  # 1 hour
    
    # Database Settings
    db_dir: str = "data/terminology/db"
    
    # Logging Settings
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/api.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Create settings instance
settings = Settings()

# Create directories if they don't exist
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.results_dir, exist_ok=True)
if settings.log_file:
    os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)