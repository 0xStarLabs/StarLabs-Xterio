import queue
import random
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from loguru import logger
import threading

import extra
import model


def start():
    extra.show_logo()
    extra.show_dev_info()

    task = int(
        input(
            "Choose what to do: \n\n"
            "[1] Xterio tasks\n"
            "[2] Withdraw from Binance\n"
            "[3] Bridge to Xterio from BNB\n"
            "[4] Collect invite codes\n"
            "[5] Connect email\n"
            "[6] Check account score\n\n>> "
        ).strip()
    )

    def launch_wrapper(index, proxy, private_key, email):
        if index <= threads:
            delay = random.uniform(1, threads)
            logger.info(f"Thread {index} starting with delay {delay:.1f}s")
            time.sleep(delay)

        account_flow(lock, index, proxy, private_key, config, task, email)

    threads = int(input("\nHow many threads do you want: ").strip())

    config = extra.read_config()
    config["abi"] = extra.read_abi("extra/abi.json")

    proxies = extra.read_txt_file("proxies", "data/proxies.txt")
    private_keys = extra.read_txt_file("private keys", "data/private_keys.txt")
    indexes = [i + 1 for i in range(len(private_keys))]

    if task == 5:
        emails = extra.read_txt_file("emails", "data/emails.txt")
    else:
        emails = [":" for _ in range(len(private_keys))]

    if config["settings"]["shuffle_accounts"]:
        combined = list(zip(indexes, proxies, private_keys))
        random.shuffle(combined)
        indexes, proxies, private_keys = zip(*combined)

    use_proxy = True
    if len(proxies) == 0:
        if not extra.no_proxies():
            return
        else:
            use_proxy = False

    lock = threading.Lock()

    if not use_proxy:
        proxies = ["" for _ in range(len(private_keys))]
    elif len(proxies) < len(private_keys):
        proxies = [proxies[i % len(proxies)] for i in range(len(private_keys))]

    logger.info("Starting...")
    with ThreadPoolExecutor(max_workers=threads) as executor:
        executor.map(launch_wrapper, indexes, proxies, private_keys, emails)

    logger.success("Saved accounts and private keys to a file.")


def account_flow(
    lock: threading.Lock,
    account_index: int,
    proxy: str,
    private_key: str,
    config: dict,
    task: int,
    email: str,
):
    try:
        xterio_instance = model.xterio.Xterio(private_key, proxy, config, email)

        ok = wrapper(xterio_instance.init_instance, 1)

        if not ok:
            raise Exception("unable to init xterio instance")

        if task == 1:
            ok = wrapper(xterio_instance.complete_all_tasks, 1)
            if not ok:
                raise Exception("unable to complete all tasks")

        elif task == 2:
            ok = wrapper(xterio_instance.withdraw_from_binance, 1)
            if not ok:
                raise Exception("unable to withdraw from binance")

        elif task == 3:
            ok = wrapper(xterio_instance.bridge_eth, 1)
            if not ok:
                raise Exception("unable to bridge to xterio")

        elif task == 4:
            invite_code = xterio_instance.collect_invite_code()
            if invite_code:
                with lock:
                    with open("data/invite_codes.txt", "a") as f:
                        f.write(f"{private_key}|{invite_code}\n")

        elif task == 5:
            ok = wrapper(xterio_instance.connect_email, 1)
            if not ok:
                raise Exception("unable to connect email")

        elif task == 6:
            ok = wrapper(xterio_instance.check_account_score, 1)
            if not ok:
                raise Exception("unable to check account score")

        if task == 5:
            with lock:
                with open("data/success_data.txt", "a") as f:
                    f.write(f"{private_key}:{proxy}:{email}\n")
        else:
            with lock:
                with open("data/success_data.txt", "a") as f:
                    f.write(f"{private_key}:{proxy}\n")

        time.sleep(
            random.randint(
                config["settings"]["pause_between_accounts"][0],
                config["settings"]["pause_between_accounts"][1],
            )
        )
        logger.success(f"{account_index} | Account flow completed successfully")

    except Exception as err:
        logger.error(f"{account_index} | Account flow failed: {err}")
        with lock:
            report_failed_key(private_key, proxy)


def wrapper(function, attempts: int, *args, **kwargs):
    for _ in range(attempts):
        result = function(*args, **kwargs)
        if isinstance(result, tuple) and result and isinstance(result[0], bool):
            if result[0]:
                return result
        elif isinstance(result, bool):
            if result:
                return True

    return result


def report_failed_key(private_key: str, proxy: str):
    try:
        with open("data/failed_keys.txt", "a") as file:
            file.write(private_key + ":" + proxy + "\n")

    except Exception as err:
        logger.error(f"Error while reporting failed account: {err}")
