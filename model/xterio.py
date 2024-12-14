import datetime
import random
import time
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
from model import constants
from data import chat_messages


class Xterio:
    def __init__(self, private_key, proxy, config):
        self.private_key = private_key
        self.proxy = proxy
        self.config = config

        self.eth_w3: Web3 | None = None
        self.address: ChecksumAddress | None = None
        self.client: requests.Session | None = None

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
                    Web3.HTTPProvider(self.config["XTERIO_RPC"], session=session)
                )
                self.eth_w3.middleware_onion.inject(
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
                    ref_code = random.choice(self.config["invite_codes"])
                    if ref_code:
                        self.apply_invite_code(ref_code)
            
            if task["ID"] == 11:
                if not task["user_task"]:
                    self.send_chat_messages()
                else:
                    data = task["user_task"][-1]
                    updated = data['UpdatedAt']
                    date_obj = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

                    # Получаем текущее время в UTC
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    yesterday_start = (now_utc - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    yesterday_end = yesterday_start + datetime.timedelta(days=1)

                    is_yesterday = yesterday_start <= date_obj < yesterday_end
                    
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
                    updated = data['UpdatedAt']
                    date_obj = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

                    # Получаем текущее время в UTC
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    yesterday_start = (now_utc - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    yesterday_end = yesterday_start + datetime.timedelta(days=1)

                    is_yesterday = yesterday_start <= date_obj < yesterday_end
                    
                    if is_yesterday:
                        result = self.complete_task(task["ID"])
                        if not result:
                            continue

                logger.info(f"{self.address} | Completed {task['ID']} mission.")

            time.sleep(
                random.randint(
                    self.config["pause_between_tasks"][0],
                    self.config["pause_between_tasks"][1],
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
                        self.config["pause_between_tasks"][0],
                        self.config["pause_between_tasks"][1],
                    )
                )

        self.claim_chat_score()

        return True

    def claim_mission(self, task_id):
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
            latest_nonce = self.eth_w3.eth.get_transaction_count(self.address, "latest")
            nonce = max(pending_nonce, latest_nonce)

            # Get gas estimate
            gas_estimate = self.eth_w3.eth.estimate_gas(
                {"from": self.address, "to": contract_address, "data": data, "value": 0}
            )

            # Calculate gas parameters
            recommended_base_fee = self.eth_w3.eth.fee_history(
                block_count=1, newest_block="latest"
            )["baseFeePerGas"][0]
            max_priority_fee_per_gas = self.eth_w3.to_wei(2, "gwei")
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
                logger.success(f"{self.address} | Complete claim {task_id} mission.")
                return True

        except Exception as err:
            logger.error(f"{self.address} | Failed to claim mission: {err}")
            return False

    def claim_chat_score(self):
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
            latest_nonce = self.eth_w3.eth.get_transaction_count(self.address, "latest")
            nonce = max(pending_nonce, latest_nonce)

            # Get gas estimate
            gas_estimate = self.eth_w3.eth.estimate_gas(
                {"from": self.address, "to": contract_address, "data": data, "value": 0}
            )

            # Calculate gas parameters
            recommended_base_fee = self.eth_w3.eth.fee_history(
                block_count=1, newest_block="latest"
            )["baseFeePerGas"][0]
            max_priority_fee_per_gas = self.eth_w3.to_wei(2, "gwei")
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
            logger.error(f"{self.address} | Failed to claim chat score: {err}")
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
            for _ in range(3):
                message = random.choice(chat_messages.CHAT_MESSAGES)

                json_data = {"answer": message, "lang": "en"}
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

                time.sleep(random.randint(3, 6))

        except Exception as err:
            logger.error(f"{self.address} | Failed to send chat message: {err}")
            return False

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
                return True, is_new

        except Exception as err:
            logger.error(f"{self.address} | Failed to Sign in Xterio account: {err}")

        return False, False
