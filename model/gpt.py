from openai import OpenAI
from typing import Optional
import httpx

system_prompt = "Your answer should be no longer than 230 characters. You need to enter the role of the scenario and answer according to the given prompt."


def ask_chatgpt(api_key: str, user_message: str, proxy: str = "") -> str:
    """
    Send a message to ChatGPT and get a response.

    Args:
        api_key (str): OpenAI API key
        user_message (str): The message to send to ChatGPT
        proxy (str): Proxy in format user:pass@ip:port or ip:port

    Returns:
        str: ChatGPT's response
    """

    if proxy:
        # Format proxy URL with scheme if not present
        if not proxy.startswith(("http://", "https://")):
            proxy = f"http://{proxy}"

        proxies = {"http://": proxy, "https://": proxy}
        http_client = httpx.Client(proxies=proxies)
        client = OpenAI(api_key=api_key, http_client=http_client)

    else:
        client = OpenAI(api_key=api_key)

    # Prepare the messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    try:
        # Make the API call
        response = client.chat.completions.create(model="gpt-4", messages=messages)

        # Extract and return the response text
        return response.choices[0].message.content
    except Exception as e:
        return f"Error occurred: {str(e)}"
