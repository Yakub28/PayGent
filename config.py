from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    lexe_client_credentials: str
    consumer_lexe_credentials: str
    anthropic_api_key: str
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"

settings = Settings()
