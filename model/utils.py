import functools
import random
import time

from loguru import logger


def random_pause(start, end):
    time.sleep(random.randint(start, end))


def retry(attempts: int, return_by_default: any, log_indicator: str | int = "-"):
    def retry_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, attempts + 1):
                result = func(*args, **kwargs)
                if result is False:
                    logger.error(f"{log_indicator} | Attempt {attempt} failed, retrying...")
                else:
                    return result
            logger.error(f"{log_indicator} | All attempts failed, returning default value.")
            return return_by_default
        return wrapper
    return retry_decorator
