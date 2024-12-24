import time
from loguru import logger
import requests
from typing import Optional, Dict
from enum import Enum


class CaptchaError(Exception):
    """Base exception for captcha errors"""

    pass


class ErrorCodes(Enum):
    ERROR_WRONG_USER_KEY = "ERROR_WRONG_USER_KEY"
    ERROR_KEY_DOES_NOT_EXIST = "ERROR_KEY_DOES_NOT_EXIST"
    ERROR_ZERO_BALANCE = "ERROR_ZERO_BALANCE"
    ERROR_PAGEURL = "ERROR_PAGEURL"
    IP_BANNED = "IP_BANNED"
    ERROR_PROXY_FORMAT = "ERROR_PROXY_FORMAT"
    ERROR_BAD_PARAMETERS = "ERROR_BAD_PARAMETERS"
    ERROR_BAD_PROXY = "ERROR_BAD_PROXY"
    ERROR_SITEKEY = "ERROR_SITEKEY"
    CAPCHA_NOT_READY = "CAPCHA_NOT_READY"
    ERROR_CAPTCHA_UNSOLVABLE = "ERROR_CAPTCHA_UNSOLVABLE"
    ERROR_WRONG_CAPTCHA_ID = "ERROR_WRONG_CAPTCHA_ID"
    ERROR_EMPTY_ACTION = "ERROR_EMPTY_ACTION"


class CaptchaSolver:
    def __init__(
        self,
        base_url: str = "https://bcsapi.xyz/api",
        proxy: str = "",
        api_key: str = "",
    ):
        self.base_url = base_url
        self.proxy = self._format_proxy(proxy) if proxy else None
        self.api_key = api_key

    def _format_proxy(self, proxy: str) -> Dict[str, str]:
        if not proxy:
            return None
        if "@" in proxy:
            return {"proxy": proxy, "proxy_type": "HTTP"}
        return {"proxy": f"http://{proxy}", "proxy_type": "HTTP"}

    def create_task(
        self,
        sitekey: str,
        pageurl: str,
        invisible: bool = None,
        domain: str = None,
        user_agent: str = None,
    ) -> Optional[str]:
        """Создает задачу на решение капчи"""
        data = {
            "access_token": self.api_key,
            "site_key": sitekey,
            "page_url": pageurl,
        }

        if invisible is not None:
            data["invisible"] = invisible
        if domain:
            data["domain"] = domain
        if user_agent:
            data["user_agent"] = user_agent
        if self.proxy:
            data.update(self.proxy)

        try:
            response = requests.post(
                f"{self.base_url}/captcha/hcaptcha", json=data, timeout=30, verify=False
            ).json()

            if "id" in response:
                return response["id"]

            logger.error(f"Error creating task: {response}")
            return None

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None

    def get_task_result(self, task_id: str) -> Optional[str]:
        """Получает результат решения капчи"""
        params = {"access_token": self.api_key}

        max_attempts = 30
        for _ in range(max_attempts):
            try:
                response = requests.get(
                    f"{self.base_url}/captcha/{task_id}",
                    params=params,
                    timeout=30,
                    verify=False,
                )
                result = response.json()

                if result.get("status") == "completed":
                    return result["solution"]
                elif "error" in response.text:
                    logger.error(f"Error getting result: {response.text}")
                    return None

                time.sleep(5)

            except Exception as e:
                logger.error(f"Error getting result: {e}")
                return None

        return None

    def solve_hcaptcha(self, sitekey: str, pageurl: str) -> Optional[str]:
        """Решает hCaptcha и возвращает токен"""
        task_id = self.create_task(sitekey, pageurl)
        if not task_id:
            return None

        return self.get_task_result(task_id)


class TwentyFourCaptchaSolver:
    def __init__(
        self,
        api_key: str,
        proxy: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = "https://24captcha.online"
        self.proxy = self._format_proxy(proxy) if proxy else None

    def _format_proxy(self, proxy: str) -> Dict[str, str]:
        if not proxy:
            return None
        if "@" in proxy:
            return {"proxy": proxy, "proxytype": "HTTP"}
        return {"proxy": f"http://{proxy}", "proxytype": "HTTP"}

    def create_task(
        self,
        sitekey: str,
        pageurl: str,
        invisible: bool = False,
        enterprise: bool = False,
        rqdata: Optional[str] = None,
    ) -> Optional[str]:
        """Создает задачу на решение капчи"""
        data = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": sitekey,
            "pageurl": pageurl,
            "json": 1,
        }

        if invisible:
            data["invisible"] = invisible
        if enterprise:
            data["enterprise"] = enterprise
        if rqdata:
            data["rqdata"] = rqdata
        if self.proxy:
            data.update(self.proxy)

        try:
            response = requests.post(
                f"{self.base_url}/in.php", json=data, timeout=30, verify=False
            ).json()
            logger.debug(f"Create captcha task request.")

            if "status" in response and response["status"] == 1:
                return response["request"]

            error = response.get("request", "Unknown error")
            if error in ErrorCodes.__members__:
                logger.error(f"API Error: {error}")
            else:
                logger.error(f"Unknown API Error: {error}")
            return None

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None

    def get_task_result(self, task_id: str) -> Optional[str]:
        """Получает результат решения капчи"""
        data = {"key": self.api_key, "action": "get", "id": task_id, "json": 1}

        max_attempts = 30
        for _ in range(max_attempts):
            try:
                response = requests.post(
                    f"{self.base_url}/res.php", json=data, timeout=30, verify=False
                ).json()

                if "status" in response and response["status"] == 1:
                    return response["request"]

                error = response.get("request", "Unknown error")
                if error == "CAPCHA_NOT_READY":
                    time.sleep(5)
                    continue

                if error in ErrorCodes.__members__:
                    logger.error(f"API Error: {error}")
                else:
                    logger.error(f"Unknown API Error: {error}")
                return None

            except Exception as e:
                logger.error(f"Error getting result: {e}")
                return None

        logger.error("Max polling attempts reached without getting a result")
        return None

    def solve_hcaptcha(
        self,
        sitekey: str,
        pageurl: str,
        invisible: bool = False,
        enterprise: bool = False,
        rqdata: Optional[str] = None,
    ) -> Optional[str]:
        """Решает hCaptcha и возвращает токен"""
        task_id = self.create_task(
            sitekey=sitekey,
            pageurl=pageurl,
            invisible=invisible,
            enterprise=enterprise,
            rqdata=rqdata,
        )
        if not task_id:
            return None

        return self.get_task_result(task_id)
