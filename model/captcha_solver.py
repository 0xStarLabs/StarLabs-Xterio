from loguru import logger
import requests
from typing import Optional, Dict


class CaptchaSolver:
    def __init__(
        self,
        base_url: str = "http://77.232.42.230:8000",
        proxy: str = "",
        api_key: str = "",
    ):
        self.base_url = base_url
        self.proxy = self._format_proxy(proxy) if proxy else None
        self.api_key = api_key

    def _format_proxy(self, proxy: str) -> Dict[str, str]:
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    def solve_hcaptcha(self, sitekey: str, pageurl: str) -> Optional[str]:
        url = f"{self.base_url}/solve_captcha"
        data = {
            "sitekey": sitekey,
            "pageurl": pageurl,
            "api_key": self.api_key,
            "proxy": "",
        }

        try:
            response = requests.post(url, json=data, proxies=self.proxy, timeout=300)
            if response.status_code == 200:
                result = response.json()
                return result.get("token")
            logger.error(f"Failed to solve captcha: {response.text}")
            return None
        except requests.RequestException as e:
            logger.error(f"Error solving captcha: {e}")
            return None
