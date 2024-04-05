from curl_cffi import requests

from model.constants import USER_AGENT


def create_client(proxy: str) -> requests.Session:
    session = requests.Session(impersonate="chrome120", timeout=60)

    if proxy:
        session.proxies.update({
            "http": "http://" + proxy,
            "https": "http://" + proxy,
        })

    session.headers.update(HEADERS)

    return session


HEADERS = {
    'authority': 'api.xter.io',
    'accept': '*/*',
    'authorization': '',
    'content-type': 'application/json',
    'origin': 'https://xter.io',
    'referer': 'https://xter.io/',
    'sec-ch-ua': '"Chromium";v="120", "Not(A:Brand";v="24", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': USER_AGENT,
}
