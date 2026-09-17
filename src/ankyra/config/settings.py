"""Dynaconf settings for Ankyra."""

from pathlib import Path

from dynaconf import Dynaconf

PROJECT_ROOT = Path(__file__).resolve().parents[3]

settings = Dynaconf(
    envvar_prefix="ANKYRA",
    load_dotenv=True,
    dotenv_path=PROJECT_ROOT / ".env",
    root_path=PROJECT_ROOT,
)
