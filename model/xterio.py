import traceback
from typing import Tuple

from web3.middleware import geth_poa_middleware
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress
import requests as default_requests
from eth_account import Account
from curl_cffi import requests
from web3.types import Wei
from loguru import logger
from web3 import Web3
import random
import time

from extra.client import create_client
from extra.converter import mnemonic_to_private_key
from model import constants


class Xterio:
    def __init__(self, private_key, proxy, config):
        self.private_key = private_key
        self.proxy = proxy
        self.config = config

        self.xter_w3: Web3 | None = None
        self.bsc_w3: Web3 | None = None
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
                session.proxies.update({
                    'http': f'http://{self.proxy}',
                    'https': f'http://{self.proxy}',
                })

                self.xter_w3 = Web3(Web3.HTTPProvider(self.config['XTERIO_RPC'], session=session))
                self.xter_w3.middleware_onion.inject(geth_poa_middleware, layer=0)

                self.bsc_w3 = Web3(Web3.HTTPProvider(self.config['BSC_RPC'], session=session))
                self.bsc_w3.middleware_onion.inject(geth_poa_middleware, layer=0)

                self.client = create_client(self.proxy)

                return True
            except Exception as err:
                logger.error(f"{self.address} | Failed to init client: {err}")

        return False

    def register_account(self):
        sign = False
        claim_egg = False
        invited = False
        reported = False
        claim_chat_nft = False

        for retry in range(self.config['attempts']):
            try:
                balance = self.check_xter_balance()

                if balance is False:
                    raise Exception("unable to check the balance")

                if balance == 0:
                    random_amount = round(random.uniform(0.015, 0.02), 3)
                    ok = self.deposit_to_xter(random_amount)
                    if not ok:
                        raise Exception("failed to deposit to xterio")

                    count = 0
                    while balance == 0 and count < 30:
                        time.sleep(6)
                        balance = self.check_xter_balance()
                        count += 1

                    if balance == 0:
                        raise Exception("Failed to deposit BNB")

                if not sign:
                    ok = self.sign_in()
                    if not ok:
                        raise Exception("unable to sign in")

                    random_pause(3, 5)

                sign = True

                if not claim_egg:
                    ok = self.claim_egg()
                    if not ok:
                        raise Exception("unable to claim an egg")

                    random_pause(3, 5)

                claim_egg = True

                if not invited:
                    if self.config['referral_code'] != "no":
                        ok = self.apply_invite(self.config['referral_code'])
                        if not ok:
                            raise Exception("unable to apply invite")
                invited = True

                if not reported:
                    social_task_ids = [13, 14, 17]
                    for social_task_id in social_task_ids:
                        ok = self.report(social_task_id)
                        if not ok:
                            raise Exception("unable to complete tasks")

                        random_pause(3, 5)
                reported = True

                if not claim_chat_nft:
                    ok = self.claim_chat_nft()
                    if not ok:
                        raise Exception("unable to claim chat NFT")

                return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to register new account ({retry + 1}/{self.config['attempts']}): {err}")
                time.sleep(10)

        return False

    def daily_actions(self):
        sign = False
        utility = False
        prop = False
        tasks = False
        vote = False

        for retry in range(self.config['attempts']):
            try:
                if not sign:
                    ok = self.sign_in()
                    if not ok:
                        raise Exception("unable to sign in")
                    random_pause(3, 5)

                sign = True

                if not utility:
                    for type_num in [1, 2, 3]:
                        ok, tx_hash = self.claim_utility(type_num)
                        if not ok:
                            raise Exception("unable to claim utility")

                        if tx_hash == "claimed":
                            continue

                        ok = self.trigger(tx_hash)
                        if not ok:
                            raise Exception("failed to trigger transaction")

                        random_pause(3, 5)
                utility = True

                random_pause(3, 5)

                if not prop:
                    for type_num in [1, 2, 3]:
                        self.prop(type_num)
                        random_pause(3, 5)

                prop = True

                if not tasks:
                    task_list = self.get_task_list()
                    if not task_list:
                        raise Exception("unable to get task list")

                    for task in task_list:
                        task_id = task['ID']
                        for user_task in task['user_task']:
                            if user_task['status'] == 1:
                                ok = self.task(task_id)
                                if not ok:
                                    raise Exception("unable to do the task")

                                random_pause(3, 5)

                tasks = True

                if not vote:
                    ticket_num = self.get_ticket()

                    if not ticket_num:
                        raise Exception("unable to get ticket")

                    if ticket_num > 0:
                        ok = self.vote(ticket_num, 0)
                        if not ok:
                            raise Exception("unable to vote")

                return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to do daily tasks ({retry + 1}/{self.config['attempts']}): {err}")
                time.sleep(10)

        return False

    def check_xter_balance(self) -> Wei | bool:
        for _ in range(5):
            try:
                return self.xter_w3.eth.get_balance(self.address)
            except Exception as err:
                logger.error(f"{self.address} | Failed to get Xterio balance: {err}")

        return False

    def deposit_to_xter(self, amount):
        for _ in range(5):
            try:
                contract_address = Web3.to_checksum_address(constants.XTERIO_DEPOSIT_ADDRESS)

                contract = self.bsc_w3.eth.contract(address=contract_address, abi=self.config['abi']['deposit']['abi'])
                amount = self.bsc_w3.to_wei(amount, 'ether')

                gas = contract.functions.depositETH(200000, '0x').estimate_gas(
                    {
                        'from': self.address,
                        'value': amount,
                        'nonce': self.bsc_w3.eth.get_transaction_count(account=self.address)
                    }
                )
                transaction = contract.functions.depositETH(200000, '0x').build_transaction({
                    'from': self.address,
                    'gasPrice': self.bsc_w3.eth.gas_price,
                    'nonce': self.bsc_w3.eth.get_transaction_count(account=self.address),
                    'gas': gas,
                    'value': amount,
                })
                signed_transaction = self.bsc_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.bsc_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
                receipt = self.bsc_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Deposit to Xterio: {constants.BSC_EXPLORER_TX}{tx_hash.hex()}")
                    return True
                else:
                    raise Exception(tx_hash.hex())

            except Exception as err:
                logger.error(f"{self.address} | Failed to deposit to Xterio: {constants.BSC_EXPLORER_TX}{err}")
                time.sleep(5)

        return False

    def get_challenge(self) -> str:
        for _ in range(5):
            try:
                response = self.client.get(
                    f'https://api.xter.io/account/v1/login/wallet/{self.address.upper()}',
                )

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    return res['data']['message']

            except Exception as err:
                logger.error(f"{self.address} Failed to get challange: {err}")

        return ""

    def get_signature(self):
        message = self.get_challenge()

        encoded_msg = encode_defunct(text=message)
        signed_msg = Web3().eth.account.sign_message(encoded_msg, private_key=self.private_key)
        signature = signed_msg.signature.hex()

        return signature

    def sign_in(self) -> bool:
        for _ in range(5):
            try:
                signature = self.get_signature()
                json_data = {
                    'address': self.address.upper(),
                    'type': 'eth',
                    'sign': signature,
                    'provider': 'METAMASK',
                    'invite_code': '',
                }

                response = self.client.post('https://api.xter.io/account/v1/login/wallet', json=json_data)
                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Sign into Xterio account")
                    self.client.headers.update({"authorization": res['data']['id_token']})
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to Sign in Xterio account: {err}")

        return False

    def claim_egg(self):
        for _ in range(5):
            try:
                abi = self.config['abi']['palio_incubator']['abi']
                contract_address = Web3.to_checksum_address(constants.PALIO_INCUBATOR_ADDRESS)

                contract = self.xter_w3.eth.contract(address=contract_address, abi=abi)

                gas = contract.functions.claimEgg().estimate_gas(
                    {
                        'from': self.address,
                        'nonce': self.xter_w3.eth.get_transaction_count(account=self.address)
                    }
                )
                transaction = contract.functions.claimEgg().build_transaction({
                    'gasPrice': self.xter_w3.eth.gas_price,
                    'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                    'gas': gas
                })
                signed_transaction = self.xter_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.xter_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)

                receipt = self.xter_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Egg claimed: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True
                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "already claimed" in err_str:
                    logger.success(f"{self.address} | Egg already claimed!")
                    return True
                else:
                    logger.error(f"{self.address} | Failed to claim an egg: {err_str}")

        return False

    def apply_invite(self, invite_code) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'code': invite_code,
                }

                response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/invite/apply', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Invite applied")
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to apply invite: {err}")

        return False

    def trigger(self, tx_hash) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'eventType': 'PalioIncubator::*',
                    'network': 'XTERIO',
                    'txHash': tx_hash,
                }

                response = self.client.post('https://api.xter.io/baas/v1/event/trigger', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Triggered")
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to trigger: {err}")

        return False

    def claim_utility(self, type_num) -> tuple[bool, str] | bool:
        for _ in range(5):
            try:
                contract_address = Web3.to_checksum_address(constants.PALIO_INCUBATOR_ADDRESS)
                contract = self.xter_w3.eth.contract(address=contract_address, abi=self.config['abi']['palio_incubator']['abi'])

                gas = contract.functions.claimUtility(type_num).estimate_gas(
                    {
                        'from': self.address,
                        'nonce': self.xter_w3.eth.get_transaction_count(account=self.address)
                    }
                )
                transaction = contract.functions.claimUtility(type_num).build_transaction({
                    'gasPrice': self.xter_w3.eth.gas_price,
                    'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                    'gas': gas
                })
                signed_transaction = self.xter_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.xter_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)

                receipt = self.xter_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Utility claimed: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True, tx_hash.hex()
                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "already claimed" in err_str or "utility claim limit exceeded" in err_str:
                    logger.success(f"{self.address} | Utility already claimed!")
                    return True, "claimed"
                else:
                    logger.error(f"{self.address} | Failed to claim utility: {err}")

        return False, ""

    def prop(self, type_num) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'prop_id': type_num,
                }

                response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/prop', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Egg feeding successful ({type_num}/3)")
                    return True

            except Exception as err:
                err_str = str(err)
                if "no balance" in err_str:
                    logger.error(f'{self.address} | Failed to feed an egg: balance is too low')
                    return False
                elif "record not found" in err_str:
                    logger.error(f'{self.address} | Failed to feed an egg: record not found. Probably already fed.')
                    return False
                else:
                    logger.error(f'{self.address} | Failed to feed an egg: {err}')

        return False

    def get_task_list(self) -> dict | bool:
        for _ in range(5):
            try:
                response = self.client.get(f'https://api.xter.io/palio/v1/user/{self.address}/task')

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    return res['data']['list']

            except Exception as err:
                logger.error(f'{self.address} | Failed to get task ID: {err}')

        return False

    def report(self, task_id) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'task_id': task_id,
                }

                response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/task/report', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Completed task {task_id}")
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to complete task {task_id}: {err}")

        return False

    def task(self, task_id) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'task_id': task_id,
                }

                response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/task', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Submit task {task_id}")
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Error submitting task {task_id}: {err}")

        return False

    def get_ticket(self) -> str | bool:
        for _ in range(5):
            try:
                response = self.client.get(f'https://api.xter.io/palio/v1/user/{self.address}/ticket')

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Current number of votes {res['data']['total_ticket']}")
                    return res['data']['total_ticket']

            except Exception as err:
                logger.error(f"{self.address} | Error getting current number of votes: {err}")

        return False

    def vote_onchain(self, vote_param) -> bool:
        for _ in range(5):
            try:
                contract_address = Web3.to_checksum_address(constants.PALIO_VOTER_ADDRESS)

                contract = self.xter_w3.eth.contract(address=contract_address, abi=self.config['abi']['palio_voter']['abi'])

                gas = contract.functions.vote(vote_param['index'], vote_param['num'], vote_param['total_num'],
                                              vote_param['expire_time'], vote_param['sign']).estimate_gas(
                    {
                        'from': self.address,
                        'nonce': self.xter_w3.eth.get_transaction_count(account=self.address)
                    }
                )
                transaction = contract.functions.vote(vote_param['index'], vote_param['num'], vote_param['total_num'],
                                                      vote_param['expire_time'], vote_param['sign']).build_transaction(
                    {
                        'gasPrice': self.xter_w3.eth.gas_price,
                        'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                        'gas': gas
                    }
                )

                signed_transaction = self.xter_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.xter_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
                receipt = self.xter_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | The onchain vote was successful: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True

                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "Not enough votes" in err_str:
                    logger.error(f'{self.address} | Failed to vote onchain: not enough votes')
                    return True

                else:
                    logger.error(f'{self.address} | Failed to vote onchain: {err}')
        return False

    def vote(self, ticket_num, index=0) -> bool:
        for _ in range(5):
            try:
                json_data = {
                    'index': index,
                    'num': ticket_num,
                }

                response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/vote', json=json_data)

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    ok = self.vote_onchain(res['data'])
                    if ok:
                        logger.success(f"{self.address} | Getting the polling parameters was successful")
                        return True

                    else:
                        raise Exception(res)

            except Exception as err:
                logger.error(f'{self.address} | Failed to get vote parameters: {err}')

        return False

    def claim_chat_nft(self) -> bool:
        for _ in range(5):
            try:
                params = {
                    "address": self.address,
                }

                data = '{"answer":"\\nIn the village of Luminia, Elara\'s heart was captivated by a traveler named Orion. Their connection was instant and deep, filled with shared dreams and starlit nights. As Orion left, the sky lit up with shimmering stars, a celestial celebration of their enduring love.\\n\\n\\n\\n\\n\\n"}'

                resp = self.client.post(f'https://3656kxpioifv7aumlcwe6zcqaa0eeiab.lambda-url.eu-central-1.on.aws/', data=data, params=params)

                # get message score

                response = self.client.get(f"https://api.xter.io/palio/v1/user/{self.address}/chat")

                logger.success(f"{self.address} | Chat message score: {response.json()['data']['max_score']} | Claiming NFT...")

                # claiming NFT

                contract_address = Web3.to_checksum_address(constants.PALIO_INCUBATOR_ADDRESS)

                contract = self.xter_w3.eth.contract(address=contract_address, abi=self.config['abi']['palio_incubator']['abi'])

                transaction = contract.functions.claimChatNFT()
                built_transaction = transaction.build_transaction({
                    "from": self.address,
                    'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                    "gas": int(transaction.estimate_gas({"from": self.address}) * 1.2),
                })

                signed_transaction = self.xter_w3.eth.account.sign_transaction(built_transaction, private_key=self.private_key)

                tx_hash = self.xter_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
                receipt = self.xter_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Claimed chat NFT: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True

                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "already claimed" in err_str:
                    logger.success(f"{self.address} | Chat NFT already claimed!")
                    return True
                else:
                    logger.error(f'{self.address} | Failed to claim chat nft: {err}')

        return False


def random_pause(start, end):
    time.sleep(random.randint(start, end))
