from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    lexe_client_credentials: str = ""
    consumer_lexe_credentials: str = ""
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    # Ollama (remote LLM backend)
    ollama_base_url: str = "http://100.92.119.114:11434"
    ollama_model: str = "qwen3:14b"
    ollama_timeout: float = 120.0

settings = Settings()
