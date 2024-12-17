import time
from loguru import logger
import requests
from typing import Optional, Dict


class CaptchaSolver:
    def __init__(
        self,
        base_url: str = "https://www.google.com",
        proxy: str = "",
        api_key: str = "",
    ):
        self.base_url = base_url
        self.proxy = self._format_proxy(proxy) if proxy else None
        self.api_key = api_key

    def _format_proxy(self, proxy: str) -> Dict[str, str]:
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    def solve_hcaptcha(self, sitekey: str, pageurl: str) -> Optional[str]:
        url = f"{self.base_url}/solve"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        data = {"sitekey": sitekey, "pageurl": pageurl}

        try:
            for _ in range(3):
                response = requests.post(
                    url, headers=headers, json=data, proxies=self.proxy, timeout=600
                )

                if "Invalid or expired API key" in response.text:
                    logger.error("Invalid or expired API key for captcha solver")
                    break

                if "Too many requests" in response.text:
                    logger.error(
                        "Too many requests for captcha solver, waiting 5 seconds..."
                    )
                    time.sleep(5)
                    continue

                if response.status_code == 200:
                    result = response.json()
                    return result.get("token")

            return None
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            return None
