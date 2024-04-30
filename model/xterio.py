import traceback

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
                    session.proxies.update({
                        'http': f'http://{self.proxy}',
                        'https': f'http://{self.proxy}',
                    })

                self.eth_w3 = Web3(Web3.HTTPProvider(self.config['ETH_RPC'], session=session))
                self.eth_w3.middleware_onion.inject(geth_poa_middleware, layer=0)

                self.client = create_client(self.proxy)

                return True
            except Exception as err:
                logger.error(f"{self.address} | Failed to init client: {err}")

        return False

    def mint_nft(self) -> bool:
        for retry in range(self.config['attempts']):
            try:
                nft_id = self.__get_nft_id()
                if nft_id == 0:
                    raise Exception("wrong NFT ID")

                mint_data = self.__mint_request(nft_id)
                if mint_data == {}:
                    raise Exception("wrong mint data")

                ok = self.__mint_nft(mint_data)
                if not ok:
                    raise Exception("unexpected error")

                return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to mint NFT: {err}")

        return False

    def perform_incubation(self) -> bool:
        for _ in range(5):
            try:
                ok, is_new = self.sign_in()
                if not ok:
                    raise Exception("unable to sign in")

                response = self.client.post(f"https://api.xter.io/palio/v1/user/{self.address}/incubation")

                if response.json()['err_code'] == 0 or "already generated the initial NFT" in response.text:
                    logger.success(f'{self.address} | Incubated!')
                    return True

            except Exception as err:
                logger.error(f"{self.address} | Failed to incubate: {err}")

        return False

    def __check_if_minted(self) -> bool:
        for _ in range(3):
            try:
                pass
            except Exception as err:
                logger.error(f"{self.address} | Failed to check if NFT is minted: {err}")

        return False

    def __mint_nft(self, mint_data: dict) -> bool:
        for _ in range(5):
            try:
                self.__check_gas()

                abi = self.config['abi']
                contract_address = Web3.to_checksum_address(constants.MINT_DEPOSIT_ADDRESS)

                contract = self.eth_w3.eth.contract(address=contract_address, abi=abi)

                transaction = contract.functions.mintWithSig(
                    mint_data['token_type'],
                    mint_data['token_address'],
                    int(mint_data['token_id']),
                    1,  # amount
                    [
                        int(mint_data['limit_for_buyer_id'][2:], 16),
                        1,
                        0,
                        1,
                    ],  # _limits
                    "0x0000000000000000000000000000000000000000",
                    0,
                    mint_data['payee_address'],
                    mint_data['expire_time'],
                    Web3.to_bytes(hexstr=mint_data['sign_msg'])
                ).build_transaction(
                    {
                        'from': self.address,
                        'nonce': self.eth_w3.eth.get_transaction_count(account=self.address),
                        'chainId': 1,
                        'value': 0
                    }
                )

                gas_estimate = contract.functions.mintWithSig(
                    mint_data['token_type'],
                    mint_data['token_address'],
                    int(mint_data['token_id']),
                    1,  # amount
                    [
                        int(mint_data['limit_for_buyer_id'][2:], 16),
                        1,
                        0,
                        1,
                    ],  # _limits
                    "0x0000000000000000000000000000000000000000",
                    0,
                    mint_data['payee_address'],
                    mint_data['expire_time'],
                    Web3.to_bytes(hexstr=mint_data['sign_msg'])
                ).estimate_gas({'from': self.address})

                recommended_base_fee = self.eth_w3.eth.fee_history(block_count=1, newest_block='latest')['baseFeePerGas'][0]

                max_priority_fee_per_gas = self.eth_w3.to_wei(2, 'gwei')
                max_fee_per_gas = recommended_base_fee + max_priority_fee_per_gas

                transaction.update({
                    'type': '0x2',
                    'maxFeePerGas': max_fee_per_gas,
                    'maxPriorityFeePerGas': max_priority_fee_per_gas,
                    'gas': int(gas_estimate * random.uniform(1.25, 1.3)),
                })

                signed_transaction = self.eth_w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = self.eth_w3.eth.send_raw_transaction(signed_transaction.rawTransaction)

                receipt = self.eth_w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    logger.success(f"{self.address} | NFT mint: {constants.ETH_EXPLORER_TX}{tx_hash.hex()}")
                    return True
                else:
                    raise Exception(f"{constants.ETH_EXPLORER_TX}{tx_hash.hex()}")

            except Exception as err:
                err_str = str(err)
                if "buyer limit exceeded" in err_str or "-32603" in err:
                    logger.success(f"{self.address} | NFT already claimed!")
                    return True
                else:
                    logger.error(f"{self.address} | Failed to mint NFT: {err_str}")
                    time.sleep(random.randint(4, 6))

        return False

    def __mint_request(self, nft_id: int) -> dict:
        for _ in range(5):
            try:
                data = {
                    "nft_id": nft_id
                }
                response = self.client.post(f"https://api.xter.io/palio/v1/user/{self.address}/incubation/mint", json=data)
                if response.json()['err_code'] == 0:
                    return response.json()['data']

            except Exception as err:
                logger.error(f"{self.address} | Failed to make mint request: {err}")

        return {}

    def __get_nft_id(self) -> int:
        for _ in range(5):
            try:
                response = self.client.get(f"https://api.xter.io/palio/v1/user/{self.address}/incubation")
                if response.json()['err_code'] == 0:
                    nft_id = response.json()['data']['palio_nft']['active']['ID']
                    logger.success(f"{self.address} | NFT ID -> {nft_id}")
                    return response.json()['data']['palio_nft']['active']['ID']

            except Exception as err:
                logger.error(f"{self.address} | Failed to incubate: {err}")

        return 0

    def check_eth_balance(self) -> Wei | bool:
        for _ in range(5):
            try:
                return self.eth_w3.eth.get_balance(self.address)
            except Exception as err:
                logger.error(f"{self.address} | Failed to get ETH balance: {err}")

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

    def __check_gas(self):
        while True:
            try:
                current_gas_price_wei = self.eth_w3.eth.gas_price
                current_gas_price_gwei = int(current_gas_price_wei / 1e9)

                if current_gas_price_gwei <= self.config['MAX_GAS']:
                    logger.success(f"Gas price is {current_gas_price_gwei} Gwei, within the limit. Proceeding with the transaction.")
                    break
                else:
                    logger.info(f"Gas price is too high: {current_gas_price_gwei} Gwei. Waiting for 30 seconds to recheck.")
                    time.sleep(30)
            except Exception as e:
                logger.error(f"Error checking gas price: {e}")
                time.sleep(30)
