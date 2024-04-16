from web3.middleware import geth_poa_middleware
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress
import requests as default_requests
from eth_account import Account
from curl_cffi import requests
from decimal import Decimal
from web3.types import Wei
from loguru import logger
from web3 import Web3
import traceback
import random
import time

from extra.client import create_client
from extra.converter import mnemonic_to_private_key
from model import constants, utils, binance
from data import chat_messages


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

                if self.proxy:
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

    def daily_actions(self):
        sign = False
        utility = False
        feed_the_egg = False
        tasks = False
        vote = False
        claim_egg = False
        for retry in range(self.config['attempts']):
            try:

                if not sign:
                    ok, is_new = self.sign_in()
                    if not ok:
                        raise Exception("unable to sign in")

                    utils.random_pause(3, 5)

                sign = True
                utils.random_pause(5, 10)

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

                if not claim_egg:
                    ok = self.claim_egg()
                    if not ok:
                        raise Exception("unable to claim an egg")

                    utils.random_pause(3, 5)

                claim_egg = True

                if self.config['referral_code']:
                    ok = self.apply_invite(self.config['referral_code'])
                    if not ok:
                        raise Exception("unable to apply invite")

                task_list = self.get_task_list()
                if not task_list:
                    raise Exception("unable to get task list")

                if self.config['claim_boost']:
                    for task in task_list:
                        if task.get("ID") == 12:
                            if not task.get("user_task"):
                                ok = self.claim_boost()
                                if not ok:
                                    raise Exception("unable to claim the boost")
                                utils.random_pause(3, 5)
                            else:
                                logger.success(f"{self.address} | Boost already claimed!")

                for task in task_list:
                    if task.get("ID") == 12:
                        ok = self.claim_chat_nft()
                        if not ok:
                            raise Exception("unable to claim chat NFT")
                        else:
                            logger.success(f"{self.address} | Chat NFT claimed!")

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

                        utils.random_pause(10, 15)

                utility = True

                task_list = self.get_task_list()
                if not task_list:
                    raise Exception("unable to get task list")

                utils.random_pause(3, 5)

                if not feed_the_egg:
                    for type_num in [1, 2, 3]:
                        self.feed_the_egg(type_num)
                        utils.random_pause(3, 5)

                feed_the_egg = True

                if not tasks:
                    for task in task_list:
                        task_id = task['ID']
                        for user_task in task['user_task']:
                            if user_task['status'] == 1:
                                ok = self.task(task_id)
                                if not ok:
                                    raise Exception("unable to do the task")

                                utils.random_pause(3, 5)

                tasks = True

                social_task_ids = [13, 14, 17, 11, 15, 16, 12]
                for social_task_id in social_task_ids:
                    ok = self.report(social_task_id)
                    if not ok:
                        raise Exception("unable to complete tasks")

                    ok = self.task(social_task_id)
                    if not ok:
                        raise Exception("unable to do the task")

                    utils.random_pause(10, 15)

                if not vote:
                    ticket_num = self.get_tickets_number()

                    if ticket_num is False:
                        raise Exception("unable to get number of tickets")

                    if ticket_num > 0:
                        ok = self.vote(ticket_num, 0)
                        if not ok:
                            raise Exception("unable to vote")

                return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to do daily tasks ({retry + 1}/{self.config['attempts']}): {err}")

        return False

    def check_xter_balance(self) -> Wei | bool:
        for _ in range(5):
            try:
                return self.xter_w3.eth.get_balance(self.address)
            except Exception as err:
                logger.error(f"{self.address} | Failed to get Xterio balance: {err}")

        return False

    def check_bnb_balance(self) -> Wei | bool:
        for _ in range(5):
            try:
                return self.bsc_w3.eth.get_balance(self.address)
            except Exception as err:
                logger.error(f"{self.address} | Failed to get BNB balance: {err}")

        return False

    def deposit_to_xter(self, amount_to_deposit):
        for _ in range(5):
            try:
                bnb_balance = self.check_bnb_balance()
                if not bnb_balance:
                    raise Exception("Unable to check the BNB balance")

                # Convert BNB balance from Wei to Ether only once
                bnb_balance_ether = Decimal(self.bsc_w3.from_wei(bnb_balance, 'ether'))
                amount_to_deposit_decimal = Decimal(amount_to_deposit)

                if amount_to_deposit_decimal > bnb_balance_ether:
                    random_buffer = Decimal(random.uniform(0.0052, 0.0065))
                    amount_to_withdraw = amount_to_deposit_decimal - bnb_balance_ether + random_buffer

                    logger.info(f"{self.address} | BNB balance is too low, trying to withdraw from Binance...")
                    ok = binance.withdraw_from_binance(api_key=self.config['binance_api_key'], api_secret=self.config['binance_api_secret'],  asset="BNB", amount=float(amount_to_withdraw), address=self.address, network="BSC")
                    if not ok:
                        return False

                    counter = 0
                    while True:
                        counter += 1
                        bnb_balance_new = self.check_bnb_balance()
                        if bnb_balance_new > bnb_balance:
                            logger.success(f"{self.address} | Received BNB")
                            break
                        else:
                            if counter == 30:
                                raise Exception("Unable to withdraw BNB")
                            logger.info(f"{self.address} | Haven't gotten a BNB yet")
                            utils.random_pause(8, 10)

                contract_address = Web3.to_checksum_address(constants.XTERIO_DEPOSIT_ADDRESS)
                contract = self.bsc_w3.eth.contract(address=contract_address, abi=self.config['abi']['deposit']['abi'])
                amount = self.bsc_w3.to_wei(amount_to_deposit_decimal, 'ether')

                amount_in_wei_80_percent = int(amount * 0.8)

                gas = contract.functions.depositETH(200000, '0x').estimate_gas({
                    'from': self.address,
                    'value': amount_in_wei_80_percent,
                    'nonce': self.bsc_w3.eth.get_transaction_count(account=self.address)
                })
                transaction = contract.functions.depositETH(200000, '0x').build_transaction({
                    'from': self.address,
                    'gasPrice': self.bsc_w3.eth.gas_price,
                    'nonce': self.bsc_w3.eth.get_transaction_count(account=self.address),
                    'gas': gas * int(random.uniform(1.5, 1.6)),
                    'value': amount_in_wei_80_percent,
                })
                signed_transaction = self.bsc_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.bsc_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
                receipt = self.bsc_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Deposit to Xterio successful: {constants.BSC_EXPLORER_TX}{tx_hash.hex()}")
                    return True
                else:
                    raise Exception(f"Transaction failed with hash {tx_hash.hex()}")

            except Exception as err:
                logger.error(f"{self.address} | Failed to deposit to Xterio: {err}")
                time.sleep(15)

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

    def sign_in(self) -> tuple[bool, bool]:
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

                is_new = True if int(res['data']['is_new']) == 1 else False

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Sign into Xterio account.")
                    self.client.headers.update({"authorization": res['data']['id_token']})
                    return True, is_new

            except Exception as err:
                logger.error(f"{self.address} | Failed to Sign in Xterio account: {err}")

        return False, False

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

    def claim_boost(self):
        for _ in range(5):
            try:
                abi = self.config['abi']['palio_incubator']['abi']
                contract_address = Web3.to_checksum_address(constants.PALIO_INCUBATOR_ADDRESS)

                contract = self.xter_w3.eth.contract(address=contract_address, abi=abi)

                value_in_wei = Web3.to_wei(0.01, 'ether')  # 0.01 BNB

                # Максимальная стоимость газа в Wei
                max_gas_fee_in_wei = Web3.to_wei(random.uniform(0.0003, 0.0004), 'ether')

                # Получение текущей цены газа
                current_gas_price = self.xter_w3.eth.gas_price

                max_gas = int(max_gas_fee_in_wei / current_gas_price)

                gas = contract.functions.boost().estimate_gas(
                    {
                        'from': self.address,
                        'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                        'value': value_in_wei
                    }
                )

                gas_limit = min(gas, max_gas)

                transaction = contract.functions.boost().build_transaction({
                    'gasPrice': self.xter_w3.eth.gas_price,
                    'nonce': self.xter_w3.eth.get_transaction_count(account=self.address),
                    'gas': gas_limit,
                    'value': value_in_wei
                })
                signed_transaction = self.xter_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.xter_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)

                receipt = self.xter_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | Boost claimed: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True
                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "already claimed" in err_str:
                    logger.success(f"{self.address} | Boost already claimed!")
                    return True
                else:
                    logger.error(f"{self.address} | Failed to claim the boost: {err_str}")

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
                str_err = str(err)
                if "only one invite code can be used" in str_err:
                    logger.success(f"{self.address} | Invite code applied!")
                    return True
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
                    logger.success(f"{self.address} | Transaction triggered")
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
                    logger.success(f"{self.address} | The food is claimed: {constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")
                    return True, tx_hash.hex()
                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "already claimed" in err_str or "utility claim limit exceeded" in err_str:
                    logger.success(f"{self.address} | The food ({type_num}) is already claimed!")
                    return True, "claimed"
                else:
                    logger.error(f"{self.address} | Failed to claim the food ({type_num}): {err}")

        return False, ""

    def feed_the_egg(self, type_num) -> bool:
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
                    logger.info(f'{self.address} | Can\'t feed the egg: no food')
                    return False
                elif "record not found" in err_str:
                    logger.error(f'{self.address} | Can\'t feed the egg: record not found. Probably already fed.')
                    return False
                else:
                    logger.error(f'{self.address} | Can\'t feed the egg: {err}')

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
                str_err = str(err)
                if any(sub in str_err for sub in ["last sub task error", "sub task error"]):
                    logger.success(f"{self.address} | Submit task {task_id}")
                    return True

                logger.error(f"{self.address} | Error submitting task {task_id}: {err}")

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
                err_str = str(err)
                if "already all finshed" in err_str:
                    logger.success(f"{self.address} | Completed task {task_id}")
                    return True
                else:
                    logger.error(f"{self.address} | Failed to complete task {task_id}: {err}")

        return False

    def get_tickets_number(self) -> int | bool:
        for _ in range(5):
            try:
                response = self.client.get(f'https://api.xter.io/palio/v1/user/{self.address}/ticket')

                res = response.json()

                if res['err_code'] != 0:
                    raise Exception(res)

                else:
                    logger.success(f"{self.address} | Total number of votes {res['data']['total_ticket']}")
                    return res['data']['total_ticket']

            except Exception as err:
                logger.error(f"{self.address} | Error getting current number of tickets: {err}")

        return False

    def vote_onchain(self, vote_param) -> tuple[bool, bool]:
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
                    return True, True

                else:
                    raise Exception(f"{constants.XTERIO_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "Not enough votes" in err_str:
                    return False, False

                else:
                    logger.error(f'{self.address} | Failed to vote onchain: {err}')

        return False, True

    def vote(self, ticket_num: int, index=0) -> bool:
        for _ in range(2):
            current_ticket_amount = ticket_num

            while current_ticket_amount > 0:
                current_ticket_amount -= 1

                try:
                    json_data = {
                        'index': index,
                        'num': current_ticket_amount,
                    }

                    response = self.client.post(f'https://api.xter.io/palio/v1/user/{self.address}/vote', json=json_data)

                    res = response.json()

                    if res['err_code'] != 0:
                        raise Exception(res)

                    else:
                        ok, enough = self.vote_onchain(res['data'])
                        if ok:
                            logger.success(f"{self.address} | Voting was successful")
                            return True

                        else:
                            if not enough:
                                continue
                            else:
                                raise Exception(res)

                except Exception as err:
                    logger.error(f'{self.address} | Failed to vote: {err}')

        return False

    def claim_chat_nft(self) -> bool:
        for _ in range(5):
            try:
                params = {
                    "address": self.address,
                }

                data = f'{{"answer":"{random.choice(chat_messages.CHAT_MESSAGES)}"}}'

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
