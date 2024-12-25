import datetime
import random
import time
import traceback
import requests as default_requests
from loguru import logger
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from curl_cffi import requests

from extra.client import create_client
from extra.converter import mnemonic_to_private_key
from model import constants, email_parser
from data import chat_messages
from model.binance import withdraw
from model.captcha_solver import CaptchaSolver, TwentyFourCaptchaSolver
from model.gpt import ask_chatgpt


class Xterio:
    def __init__(self, private_key, proxy, config, email):
        self.private_key = private_key
        self.proxy = proxy
        self.config = config
        self.email_login = email.split(":")[0]
        self.email_password = email.split(":")[1]

        self.eth_w3: Web3 | None = None
        self.bsc_w3: Web3 | None = None
        self.address: ChecksumAddress | None = None
        self.client: requests.Session | None = None

        self.is_captcha_solved_for_chat = False
        self.access_token = None

    def init_instance(self):
        for _ in range(5):
            try:
                if len(self.private_key.split()) > 1:
                    self.private_key = mnemonic_to_private_key(self.private_key)

                account = Account.from_key(self.private_key)
                self.address = account.address

                session = default_requests.Session()

                if self.proxy:
                    session.proxies.update(
                        {
                            "http": f"http://{self.proxy}",
                            "https": f"http://{self.proxy}",
                        }
                    )

                self.eth_w3 = Web3(
                    Web3.HTTPProvider(
                        self.config["bridge_to_xterio"]["XTERIO_RPC"], session=session
                    )
                )
                self.eth_w3.middleware_onion.inject(
                    ExtraDataToPOAMiddleware, name="extradata_to_poa", layer=0
                )

                self.bsc_w3 = Web3(
                    Web3.HTTPProvider(
                        self.config["bridge_to_xterio"]["BNB_RPCS"][0], session=session
                    )
                )
                self.bsc_w3.middleware_onion.inject(
                    ExtraDataToPOAMiddleware, name="extradata_to_poa", layer=0
                )

                self.client = create_client(self.proxy)

                self._sign_in()

                return True
            except Exception as err:
                logger.error(f"{self.address} | Failed to init client: {err}")

        return False

    def complete_all_tasks(self):
        tasks = self._get_tasks()

        for task in tasks["list"]:
            if task["ID"] == 16:
                if not task["user_task"]:
                    ref_code = random.choice(self.config["invite"]["invite_codes"])
                    if ref_code:
                        self.apply_invite_code(ref_code)

            if task["ID"] == 11:
                if not task["user_task"]:
                    self.send_chat_messages()
                else:
                    data = task["user_task"][-1]
                    updated = data["UpdatedAt"]
                    date_obj = datetime.datetime.strptime(
                        updated, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc)

                    # Получаем текущее время в UTC
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    today_start = now_utc.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )

                    # Если date_obj меньше ачала текущего дня, значит обновление было не сегодня
                    is_yesterday = date_obj < today_start

                    if is_yesterday:
                        self.send_chat_messages()
                        time.sleep(random.randint(5, 8))
                        self.claim_mission(task["ID"])

            if task["ID"] in [18, 20, 21, 22, 23, 24]:
                if not task["user_task"]:
                    result = self.complete_task(task["ID"])
                    if not result:
                        continue
                elif task["ID"] == 18 and task["user_task"]:
                    data = task["user_task"][-1]
                    updated = data["UpdatedAt"]
                    date_obj = datetime.datetime.strptime(
                        updated, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc)

                    # Получаем текущее время в UTC
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    today_start = now_utc.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )

                    # Если date_obj меньше начала текущего дня, значит обновление было не сегодня
                    is_yesterday = date_obj < today_start

                    if is_yesterday:
                        result = self.complete_task(task["ID"])
                        if not result:
                            continue

                logger.info(f"{self.address} | Completed {task['ID']} mission.")

            time.sleep(
                random.randint(
                    self.config["settings"]["pause_between_tasks"][0],
                    self.config["settings"]["pause_between_tasks"][1],
                )
            )

        tasks = self._get_tasks()
        for task in tasks["list"]:
            if task["user_task"]:
                if not task["user_task"][-1]["tx_hash"]:
                    result = self.claim_mission(task["ID"])
                    if result:
                        logger.success(
                            f"{self.address} | Completed claim {task['ID']} mission."
                        )
                    else:
                        logger.error(
                            f"{self.address} | Failed to claim {task['ID']} mission."
                        )

                time.sleep(
                    random.randint(
                        self.config["settings"]["pause_between_tasks"][0],
                        self.config["settings"]["pause_between_tasks"][1],
                    )
                )

        self.claim_chat_score()

        return True

    def claim_mission(self, task_id):
        for retry in range(self.config["settings"]["claim_retry_attempts"]):
            try:
                contract_address = Web3.to_checksum_address(
                    "0x7bb85350e3a883A1708648AB7e37cEf4651cFd48"
                )

                # Generate function call data with task_id
                function_selector = "0xdc7d41f6"
                # Pad task_id to 32 bytes
                padded_task_id = hex(task_id)[2:].zfill(64)
                # Pad walletType (1) to 32 bytes
                wallet_type = hex(1)[2:].zfill(64)
                # Combine function selector and parameters
                data = function_selector + padded_task_id + wallet_type

                # Get current nonce including pending transactions
                pending_nonce = self.eth_w3.eth.get_transaction_count(
                    self.address, "pending"
                )
                latest_nonce = self.eth_w3.eth.get_transaction_count(
                    self.address, "latest"
                )
                nonce = max(pending_nonce, latest_nonce)

                # Get gas estimate
                gas_estimate = self.eth_w3.eth.estimate_gas(
                    {
                        "from": self.address,
                        "to": contract_address,
                        "data": data,
                        "value": 0,
                    }
                )

                # Calculate gas parameters
                recommended_base_fee = self.eth_w3.eth.fee_history(
                    block_count=1, newest_block="latest"
                )["baseFeePerGas"][0]
                max_priority_fee_per_gas = self.eth_w3.to_wei(0.002, "gwei")
                max_fee_per_gas = recommended_base_fee + max_priority_fee_per_gas

                transaction = {
                    "chainId": 112358,
                    "from": self.address,
                    "to": contract_address,
                    "value": 0,
                    "data": data,
                    "nonce": nonce,
                    "type": "0x2",
                    "maxFeePerGas": max_fee_per_gas,
                    "maxPriorityFeePerGas": max_priority_fee_per_gas,
                    "gas": int(gas_estimate * 1.15),
                }

                signed_transaction = self.eth_w3.eth.account.sign_transaction(
                    transaction, private_key=self.private_key
                )

                tx_hash = self.eth_w3.eth.send_raw_transaction(
                    signed_transaction.raw_transaction
                )
                receipt = self.eth_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(
                        f"{self.address} | Successfully claimed AI mission: {task_id}"
                    )
                else:
                    raise Exception(f"Transaction failed: {tx_hash.hex()}")

                tx = "0x" + tx_hash.hex()

                json_data = {
                    "task_id": task_id,
                    "tx_hash": tx,
                    "is_by_bit": 1,
                }

                response = self.client.post(
                    "https://api.xter.io/ai/v1/user/task", json=json_data
                )

                if response.json()["err_code"] != 0:
                    raise Exception(response.text)
                else:
                    logger.success(
                        f"{self.address} | Complete claim {task_id} mission."
                    )
                    return True

            except Exception as err:
                logger.error(
                    f"{self.address} | Failed to claim mission {retry + 1}/{self.config['settings']['claim_retry_attempts']}: {err}"
                )
                time.sleep(
                    random.randint(
                        self.config["settings"]["pause_between_claim_retries"][0],
                        self.config["settings"]["pause_between_claim_retries"][1],
                    )
                )

        return False

    def claim_chat_score(self):
        for retry in range(self.config["settings"]["claim_retry_attempts"]):
            try:
                response = self.client.get("https://api.xter.io/ai/v1/user/chat")

                if response.json()["err_code"] != 0:
                    raise Exception(response.text)
                else:
                    claim_status = response.json()["data"]["claim_status"]
                    if claim_status == 2:
                        logger.info(f"{self.address} | Already claimed chat score")
                        return True

                contract_address = Web3.to_checksum_address(
                    "0x7bb85350e3a883A1708648AB7e37cEf4651cFd48"
                )

                # Generate function call data
                function_selector = "0x31bf7fe8"
                # Pad walletType (1) to 32 bytes
                wallet_type = hex(1)[2:].zfill(64)
                # Combine function selector and parameter
                data = function_selector + wallet_type

                # Get current nonce including pending transactions
                pending_nonce = self.eth_w3.eth.get_transaction_count(
                    self.address, "pending"
                )
                latest_nonce = self.eth_w3.eth.get_transaction_count(
                    self.address, "latest"
                )
                nonce = max(pending_nonce, latest_nonce)

                # Get gas estimate
                gas_estimate = self.eth_w3.eth.estimate_gas(
                    {
                        "from": self.address,
                        "to": contract_address,
                        "data": data,
                        "value": 0,
                    }
                )

                # Calculate gas parameters
                recommended_base_fee = self.eth_w3.eth.fee_history(
                    block_count=1, newest_block="latest"
                )["baseFeePerGas"][0]
                max_priority_fee_per_gas = self.eth_w3.to_wei(0.002, "gwei")
                max_fee_per_gas = recommended_base_fee + max_priority_fee_per_gas

                transaction = {
                    "chainId": 112358,
                    "from": self.address,
                    "to": contract_address,
                    "value": 0,
                    "data": data,
                    "nonce": nonce,
                    "type": "0x2",
                    "maxFeePerGas": max_fee_per_gas,
                    "maxPriorityFeePerGas": max_priority_fee_per_gas,
                    "gas": int(gas_estimate * 1.15),
                }

                signed_transaction = self.eth_w3.eth.account.sign_transaction(
                    transaction, private_key=self.private_key
                )

                tx_hash = self.eth_w3.eth.send_raw_transaction(
                    signed_transaction.raw_transaction
                )
                receipt = self.eth_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status != 1:
                    raise Exception(f"Transaction failed: {tx_hash.hex()}")
                else:
                    logger.success(f"{self.address} | Successfully claimed chat score")
                    return True

                # tx = "0x" + tx_hash.hex()

                # json_data = {
                #     "eventType": "AiCampaign::*",
                #     "network": "XTERIO",
                #     "txHash": tx,
                # }

                # response = self.client.post(
                #     "https://api.xter.io/baas/v1/event/trigger", json=json_data
                # )
                # print(response.text)
                # if response.json()["err_code"] != 0:
                #     raise Exception(response.text)
                # else:
                #     logger.success(f"{self.address} | Successfully claimed chat score")

                # return True
            except Exception as err:
                logger.error(
                    f"{self.address} | Failed to claim chat score {retry + 1}/{self.config['settings']['claim_retry_attempts']}: {err}"
                )
                time.sleep(
                    random.randint(
                        self.config["settings"]["pause_between_claim_retries"][0],
                        self.config["settings"]["pause_between_claim_retries"][1],
                    )
                )

        return False

    def complete_task(self, task_id):
        try:
            json_data = {
                "task_id": task_id,
            }

            response = self.client.post(
                "https://api.xter.io/ai/v1/user/task/report", json=json_data
            )
            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to complete task: {err}")
            return False

    def apply_invite_code(self, ref_code):
        try:
            json_data = {"code": ref_code}
            response = self.client.post(
                "https://api.xter.io/ai/v1/user/invite/apply", json=json_data
            )

            if response.json()["err_code"] != 0:
                if response.json()["err_code"] == 10003:
                    logger.info(
                        f"{self.address} | Already applied invite code: {ref_code}"
                    )
                    return True
                raise Exception(response.text)
            else:

                logger.success(f"{self.address} | Applied invite code: {ref_code}")
                return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to apply invite code: {err}")
            return False

    def send_chat_messages(self):
        try:
            for attempt in range(3):
                for _ in range(3):
                    if self.config["settings"]["use_chatgpt"]:
                        response = self.client.get(
                            "https://api.xter.io/ai/v1/scene?lang="
                        )
                        if response.json()["err_code"] != 0:
                            logger.error(
                                f"{self.address} | Failed to get chat messages: {response.text}"
                            )
                            continue

                        scene_list = response.json()["data"]["list"]
                        if not scene_list:
                            logger.error(f"{self.address} | Scene list is empty")
                            continue

                        scene = (
                            scene_list[0]["describe"]
                            if len(scene_list) == 1
                            else scene_list[-1]["describe"]
                        )
                        if len(scene_list[0]) == 1:
                            chat_item = scene_list[0]
                        else:
                            chat_item = scene_list[-1]

                        scene = chat_item["describe"]

                        response = self.client.get(
                            "https://api.xter.io/ai/v1/user/chat"
                        )
                        if response.json()["err_code"] != 0:
                            logger.error(
                                f"{self.address} | Failed to get chat messages: {response.text}"
                            )
                            continue

                        message_list = response.json()["data"]["list"]
                        if not message_list:
                            prologue = chat_item["prologue"]
                            placeholder = chat_item["placeholder"]

                            message = (
                                f"Prologue: {prologue}. Placeholder: {placeholder}"
                            )

                        else:
                            last_message = (
                                message_list[0]
                                if len(message_list) == 1
                                else message_list[-1]
                            )

                            ai_answer_text = last_message["extract"]["words"]
                            ai_answer_mood = last_message["extract"]["mood"]

                            message = f"Scene: {scene}. AI mood: {ai_answer_mood}. AI asks you: {ai_answer_text}"

                        message = ask_chatgpt(
                            self.config["settings"]["chat_gpt_api_key"],
                            message,
                            self.config["settings"]["proxy_for_chat_gpt"],
                        )

                        if "Error occurred:" in message:
                            logger.error(
                                f"{self.address} | Failed to send chat message: {message}"
                            )
                            continue

                        if attempt == 0:
                            message = "You all right. " + message

                    else:
                        message = random.choice(chat_messages.CHAT_MESSAGES)

                    json_data = {
                        "answer": message,
                        "lang": "en",
                    }

                    if not self.is_captcha_solved_for_chat:
                        sitekey = "2032769e-62c0-4304-87e4-948e81367fba"
                        pageurl = "https://app.xter.io/activities/ai-campaign"

                        logger.info(
                            f"{self.address} | Solving captcha for chat messages"
                        )

                        if self.config["captcha"]["captcha_service"] == "24captcha":
                            logger.info(f"{self.address} | Using 24captcha")
                            solver = TwentyFourCaptchaSolver(
                                api_key=self.config["captcha"]["captcha_api_key"],
                                proxy=self.config["captcha"]["captcha_proxy"],
                            )
                        else:
                            logger.info(f"{self.address} | Using BestCaptcha")
                            solver = CaptchaSolver(
                                proxy=self.config["captcha"]["captcha_proxy"],
                                api_key=self.config["captcha"]["captcha_api_key"],
                            )

                        for _ in range(
                            self.config["captcha"]["solve_captcha_attempts"]
                        ):
                            result = solver.solve_hcaptcha(sitekey, pageurl)
                            if result:
                                logger.success(
                                    f"{self.address} | Captcha solved for chat"
                                )
                                break
                            else:
                                logger.error(
                                    f"{self.address} | Failed to solve captcha for chat"
                                )

                        if not result:
                            raise Exception("failed to solve captcha for chat 3 times")

                        json_data["h-recaptcha-response"] = result.strip()

                    response = self.client.post(
                        "https://api.xter.io/ai/v1/chat",
                        json=json_data,
                    )

                    if "error" in response.text:
                        logger.error(
                            f"{self.address} | Failed to send chat message: {response.text}"
                        )
                    else:
                        logger.success(f"{self.address} | Sent chat message: {message}")
                        self.is_captcha_solved_for_chat = True

                    time.sleep(random.randint(3, 6))
                    break

                pause = random.randint(
                    self.config["settings"]["pause_between_messages"][0],
                    self.config["settings"]["pause_between_messages"][1],
                )
                logger.info(
                    f"{self.address} | Pausing for {pause} seconds between messages"
                )
                time.sleep(pause)

        except Exception as err:
            logger.error(f"{self.address} | Failed to send chat message: {err}")
            return False

    def collect_invite_code(self):
        try:
            response = self.client.get("https://api.xter.io/ai/v1/user/invite/code")
            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                code = response.json()["data"]["code"]
                logger.success(f"{self.address} | Collected invite code: {code}")
                return code

        except Exception as err:
            logger.error(f"{self.address} | Failed to collect invite code: {err}")
            return ""

    def withdraw_from_binance(self):
        try:
            bnb_balance = self._check_bnb_balance()
            if not bnb_balance:
                raise Exception("Unable to check the BNB balance")

            amount_to_withdraw = random.uniform(
                self.config["binance"]["withdraw_amount"][0],
                self.config["binance"]["withdraw_amount"][1],
            )

            if bnb_balance < self.config["binance"]["min_bnb_balance"]:
                result = withdraw(
                    self.config["binance"]["BINANCE_API_KEY"],
                    self.config["binance"]["BINANCE_API_SECRET"],
                    "BNB",
                    amount_to_withdraw,
                    self.address,
                    "BSC",
                )
                if not result:
                    raise Exception("Failed to withdraw from Binance")
                else:
                    logger.success(
                        f"{self.address} | Withdrew {amount_to_withdraw} BNB from Binance"
                    )
                    return True
            else:
                logger.info(f"{self.address} | BNB balance is enough")
                return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to withdraw from Binance: {err}")
            return False

    def connect_email(self):
        try:
            response = self.client.get("https://api.xter.io/account/v1/user/2fa?")
            try:
                response_data = response.json()
                if response_data.get("err_code") != 0:
                    raise Exception(response.text)

                data = response_data.get("data", {})
                if not isinstance(data, dict):
                    logger.info(f"{self.address} | No email connected yet")
                else:
                    email = data.get("email")
                    if email is not None and email.strip():
                        logger.info(
                            f"{self.address} | Email already connected: {email}"
                        )
                        return True

                    logger.info(f"{self.address} | No email connected yet")

            except ValueError as e:
                logger.error(f"{self.address} | Invalid 2FA check response: {e}")
                return False

            except Exception as e:
                if "2fa configuration error" in str(e):
                    pass
                else:
                    logger.error(f"{self.address} | Error checking 2FA status: {e}")
                    return False

            logger.info(f"{self.address} | Trying to connect email...")

            response = self.client.post(
                "https://api.xter.io/account/v1/user/2fa/email",
                json={"email": self.email_login},
            )

            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                logger.success(f"{self.address} | Email code sent!")

            email_checker = email_parser.SyncEmailChecker(
                email=self.email_login, password=self.email_password
            )

            if email_checker.check_if_email_valid():
                # Search for verification code
                logger.info(f"{self.address} | Searching for email code...")
                code = email_checker.check_email_for_code()
                if code:
                    logger.success(f"{self.address} | Email code: {code}")
                else:
                    raise Exception("Failed to get email code")
            else:
                logger.error(f"{self.address} | Invalid email credentials")
                return False

            response = self.client.post(
                "https://api.xter.io/account/v1/user/2fa/email/set", json={"code": code}
            )

            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                logger.success(f"{self.address} | Email code set!")

            response = self.client.get("https://api.xter.io/account/v1/user/2fa?")
            if response.json()["err_code"] != 0:
                raise Exception(response.text)

            data = response.json()["data"]
            if data["email"] != "":
                logger.success(f"{self.address} | Email {data['email']} connected!")
                return True
            else:
                raise Exception("Failed to connect email")

        except Exception as err:
            logger.error(f"{self.address} | Failed to connect email: {err}")
            return False

    def connect_email_tasks(self):
        try:
            logger.info(f"{self.address} | Trying to connect tasks email...")

            json_data = {
                    "email": self.email_login,
                    "access_token": self.access_token,
                }

            response = self.client.post(
                "https://api.xter.io/account/v1/user/email",
                json=json_data,
            )
            if "forbidden" in response.text:
                logger.info(f"{self.address} | Email already connected!")
                return True
            
            if response.json()["err_code"] != 0:
                if "reqeust too frequently" in response.text:
                    logger.info(f"{self.address} | Request too frequently. Wait like 20 minutes, please :)")
                    return False
                
                else:
                    raise Exception(response.text)
            else:
                logger.success(f"{self.address} | Email code sent!")

            email_checker = email_parser.SyncEmailChecker(
                email=self.email_login, password=self.email_password
            )

            if email_checker.check_if_email_valid():
                # Search for verification code
                logger.info(f"{self.address} | Searching for email code...")
                code = email_checker.check_email_for_code()
                if code:
                    logger.success(f"{self.address} | Email code: {code}")
                else:
                    raise Exception("Failed to get email code")
            else:
                logger.error(f"{self.address} | Invalid email credentials")
                return False

            response = self.client.post(
                "https://api.xter.io/account/v1/user/email/verify",
                json={
                    "code": code,
                    "access_token": self.access_token,
                    "subscribe": 0,
                },
            )

            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                logger.success(f"{self.address} | Email {self.email_login} connected!")
                return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to connect email: {err}")
            return False

    def check_account_score(self):
        try:
            response = self.client.get("https://api.xter.io/ai/v1/user/score")
            if response.json()["err_code"] != 0:
                raise Exception(response.text)

            data = response.json()["data"]
            multiply = data.get("multiply", "?")
            task = data.get("task", "?")
            base = data.get("base", "?")

            logger.success(
                f"{self.address} | Account score: Task: {task} | Multiply: {multiply} | Base: {base}"
            )

            return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to check account score: {err}")
            return False

    def _check_bnb_balance(self):
        for _ in range(5):
            try:
                balance_wei = self.bsc_w3.eth.get_balance(self.address)
                return float(Web3.from_wei(balance_wei, "ether"))
            except Exception as err:
                logger.error(f"{self.address} | Failed to get BNB balance: {err}")

        raise Exception("Failed to get BNB balance")

    def _get_tasks(self):
        try:
            response = self.client.get("https://api.xter.io/ai/v1/task")
            if response.json()["err_code"] != 0:
                raise Exception(response.text)
            else:
                return response.json()["data"]

            # 18: share ai mission
            # 20: telegram mission

        except Exception as err:
            logger.error(f"{self.address} | Failed to get tasks: {err}")
            raise err

    def _get_challenge(self) -> str:
        for _ in range(5):
            try:
                response = self.client.get(
                    f"https://api.xter.io/account/v1/login/wallet/{self.address.upper()}",
                )

                res = response.json()

                if res["err_code"] != 0:
                    raise Exception(res)

                else:
                    return res["data"]["message"]

            except Exception as err:
                logger.error(f"{self.address} Failed to get challange: {err}")

        return ""

    def _get_signature(self):
        message = self._get_challenge()
        encoded_msg = encode_defunct(text=message)
        signed_msg = Web3().eth.account.sign_message(
            encoded_msg, private_key=self.private_key
        )
        signature = signed_msg.signature.hex()

        return signature

    def _sign_in(self) -> tuple[bool, bool]:
        try:
            signature = self._get_signature()
            json_data = {
                "address": self.address,
                "type": "eth",
                "sign": "0x" + signature,
                "provider": "BYBIT",
                "invite_code": "",
            }
            response = self.client.post(
                "https://api.xter.io/account/v1/login/wallet", json=json_data
            )
            res = response.json()

            is_new = True if int(res["data"]["is_new"]) == 1 else False

            if res["err_code"] != 0:
                raise Exception(res)

            else:
                logger.success(f"{self.address} | Sign into Xterio account.")
                self.client.headers.update({"authorization": res["data"]["id_token"]})
                self.access_token = res["data"]["access_token"]
                return True, is_new

        except Exception as err:
            logger.error(f"{self.address} | Failed to Sign in Xterio account: {err}")

        return False, False

    def bridge_eth(self):
        for rpc in self.config["bridge_to_xterio"]["BNB_RPCS"]:
            try:
                # Get random amount between config values with random decimal places (8-18)
                amount = round(
                    random.uniform(
                        self.config["bridge_to_xterio"]["AMOUNT"][0],
                        self.config["bridge_to_xterio"]["AMOUNT"][1],
                    ),
                    random.randint(8, 18),
                )
                amount_wei = Web3.to_wei(amount, "ether")
                bnb_w3 = Web3(Web3.HTTPProvider(rpc))

                contract_address = Web3.to_checksum_address(constants.CONTRACT_ADDRESS)
                contract = bnb_w3.eth.contract(
                    address=contract_address, abi=constants.CONTRACT_ABI
                )

                # Get current nonce including pending transactions
                nonce = bnb_w3.eth.get_transaction_count(self.address, "latest")
                # Build transaction using contract function
                transaction = contract.functions.bridgeETHTo(
                    self.address,
                    200000,  # _minGasLimit
                    bytes.fromhex("7375706572627269646765"),  # _extraData
                ).build_transaction(
                    {
                        "from": self.address,
                        "value": amount_wei,
                        "nonce": nonce,
                        "gasPrice": bnb_w3.to_wei(1, "gwei"),
                    }
                )
                # Estimate gas
                gas_estimate = bnb_w3.eth.estimate_gas(transaction)
                transaction["gas"] = int(gas_estimate * 1.15)  # Add 15% buffer

                signed_transaction = bnb_w3.eth.account.sign_transaction(
                    transaction, private_key=self.private_key
                )
                tx_hash = bnb_w3.eth.send_raw_transaction(
                    signed_transaction.raw_transaction
                )
                receipt = bnb_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(
                        f"{self.address} | Successfully bridged {amount} BNB using RPC {rpc} https://bscscan.com/tx/0x{tx_hash.hex()}"
                    )
                    return True
                else:
                    # logger.error(f"Bridge transaction failed with RPC {rpc}: {tx_hash.hex()}")
                    continue

            except Exception as err:
                # logger.error(f"{self.address} | Failed to bridge BNB with RPC {rpc}: {err}")
                continue

        logger.error(f"{self.address} | All RPCs failed to bridge BNB")
        return False
