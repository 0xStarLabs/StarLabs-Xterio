import json
from configparser import ConfigParser

from loguru import logger


def read_txt_file(file_name: str, file_path: str) -> list:
    with open(file_path, "r") as file:
        items = [line.strip() for line in file]

    logger.success(f"Successfully loaded {len(items)} {file_name}.")
    return items


def read_config() -> dict:
    settings = {}
    config = ConfigParser()
    config.read('config.ini')
    # INFO
    settings["referral_code"] = str(config['info']['referral_code'])
    settings["XTERIO_RPC"] = str(config['info']['XTERIO_RPC'])
    settings["BSC_RPC"] = str(config['info']['BSC_RPC'])
    settings['attempts'] = int(config['info']['attempts'])
    settings['LAUNCH_TIME'] = int(config['info']['LAUNCH_TIME'])
    settings["mobile_proxy"] = str(config['info']['mobile_proxy'])
    settings['change_ip_pause'] = int(config['info']['change_ip_pause'])

    return settings


def read_abi(path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def no_proxies() -> bool:
    user_choice = int(input("No proxies were detected. Do you want to continue without proxies? (1 or 2)\n"
                            "[1] Yes\n"
                            "[2] No\n>> ").strip())

    return True if user_choice == 1 else False
