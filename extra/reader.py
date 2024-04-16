import json
from configparser import ConfigParser

import yaml
from loguru import logger


def read_txt_file(file_name: str, file_path: str) -> list:
    with open(file_path, "r") as file:
        items = [line.strip() for line in file]

    logger.success(f"Successfully loaded {len(items)} {file_name}.")
    return items


def read_config() -> dict:
    with open('config.yaml', 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)

    return config


def read_abi(path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def no_proxies() -> bool:
    user_choice = int(input("No proxies were detected. Do you want to continue without proxies? (1 or 2)\n"
                            "[1] Yes\n"
                            "[2] No\n>> ").strip())

    return True if user_choice == 1 else False
