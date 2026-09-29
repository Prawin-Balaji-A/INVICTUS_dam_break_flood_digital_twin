import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Dam Break Inundation Modelling System"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'dam_break.db'}"

    DATA_DIR: Path = BASE_DIR / "data"
    MODELS_DIR: Path = BASE_DIR / "models"
    SIMULATIONS_DIR: Path = BASE_DIR / "data" / "simulations"

    DELFT3D_PATH: str = ""
    DELFT3D_WORKING_DIR: Path = BASE_DIR / "data" / "delft3d_runs"

    GEE_PROJECT_ID: str = ""
    GEE_SERVICE_ACCOUNT_JSON: str = ""
    OPENTOPOGRAPHY_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def is_delft3d_available(self) -> bool:
        if self.DELFT3D_PATH and os.path.exists(self.DELFT3D_PATH):
            return True
        import shutil
        if shutil.which("d_flow") or shutil.which("d_flow.exe") or shutil.which("dimr"):
            return True
        return False

    def is_gee_available(self) -> bool:
        return bool(self.GEE_PROJECT_ID or (self.GEE_SERVICE_ACCOUNT_JSON and os.path.exists(self.GEE_SERVICE_ACCOUNT_JSON)))

settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
settings.SIMULATIONS_DIR.mkdir(parents=True, exist_ok=True)
(settings.DATA_DIR / "dem").mkdir(parents=True, exist_ok=True)
(settings.DATA_DIR / "rivers").mkdir(parents=True, exist_ok=True)
(settings.DATA_DIR / "buildings").mkdir(parents=True, exist_ok=True)
(settings.DATA_DIR / "satellite").mkdir(parents=True, exist_ok=True)
