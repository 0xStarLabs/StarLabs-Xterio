import time
from loguru import logger
import requests
from typing import Optional, Dict


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
                f"{self.base_url}/captcha/hcaptcha", json=data, timeout=30
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
                    f"{self.base_url}/captcha/{task_id}", params=params, timeout=30
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
