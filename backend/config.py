from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import Field
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / '.env'), extra='ignore')
    ai_mode: Literal['mock','live'] = 'mock'
    ai_provider: str = 'ollama'
    openai_api_key: str = Field(default='',repr=False,exclude=True)
    openai_model: str = 'gpt-6-luna'
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen3:1.7b'
    ollama_tool_format: Literal['native','json'] = 'json'
    ollama_num_ctx: int = Field(default=8192,ge=2048,le=32768)
    ollama_num_predict: int = Field(default=1000,ge=128,le=4096)
    ollama_num_batch: int = Field(default=128,ge=32,le=512)
    ollama_timeout: int = Field(default=600,ge=10,le=900)
    max_agent_steps: int = 12
    allow_external_ai: bool = False
    data_dir: str = str(ROOT / 'data')
    max_upload_mb: int = 100

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # Keys come only from the project's .env, without shell interpolation.
        # Explicit constructor injection remains available for offline tests.
        def without_key(source):
            def read():
                values=source();values.pop('openai_api_key',None)
                return values
            return read
        def key_from_file():
            value=dotenv_values(ROOT/'.env',interpolate=False).get('OPENAI_API_KEY')
            return {'openai_api_key':value or ''}
        return (init_settings,key_from_file,without_key(env_settings),without_key(dotenv_settings),without_key(file_secret_settings))

settings = Settings()
