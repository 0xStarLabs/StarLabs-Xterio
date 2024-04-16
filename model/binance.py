from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger
import time


def withdraw_from_binance(api_key, api_secret, asset, amount, address, network=None):
    client = Client(api_key, api_secret)

    try:
        # Optionally, fetch balance before attempting withdrawal
        balance = client.get_asset_balance(asset=asset)
        if float(balance['free']) < amount:
            logger.error(f"Insufficient balance to withdraw {amount} {asset}")
            return False

        rounded_amount = round(amount, 8)

        # Perform the withdrawal
        result = client.withdraw(
            coin=asset,
            address=address,
            amount=rounded_amount,
            network=network
        )

        logger.info(f"Successfully initiated withdrawal from Binance: {result}")
        return True

    except BinanceAPIException as e:
        logger.error(f"Binance API Exception occurred: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return False

