from pathlib import Path
from typing import Any

import yaml


def load_project_config() -> dict[str, Any]:
    config_file = Path("config/config.yaml")
    with config_file.open("r") as file:
        config: dict[str, Any] = yaml.safe_load(file)
        return config
