import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME)

def validate_api_key(api_key: str = Security(api_key_header)):
    master_key = os.getenv("API_MASTER_KEY")

    if not master_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error (API_MASTER_KEY is missing)."
        )

    if api_key != master_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid or missing API key."
        )
    return api_key