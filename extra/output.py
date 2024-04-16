from termcolor import cprint
from pyfiglet import figlet_format
from colorama import init
import sys
import os


def show_logo():
    os.system("cls")
    init(strip=not sys.stdout.isatty())
    print("\n")
    logo = figlet_format("STAR LABS", font="banner3")
    cprint(logo, 'light_cyan')
    print("")


def show_dev_info():
    print("\033[36m" + "VERSION: " + "\033[92m" + "1.1" + "\033[92m")
    print("\033[36m"+"DEV: " + "\033[92m" + "https://t.me/StarLabsTech" + "\033[92m")
    print("\033[36m"+"GitHub: " + "\033[92m" + "https://github.com/0xStarLabs/StarLabs-Xterio" + "\033[92m")
    print("\033[36m" + "DONATION EVM ADDRESS: " + "\033[92m" + "0x620ea8b01607efdf3c74994391f86523acf6f9e1" + "\033[0m")
    print()


def show_menu(menu_items: list):
    os.system("")
    print()
    counter = 0
    for item in menu_items:
        counter += 1

        if counter == len(menu_items):
            print('' + '[' + '\033[34m' + f'{counter}' + '\033[0m' + ']' + f' {item}\n')
        else:
            print('' + '[' + '\033[34m' + f'{counter}' + '\033[0m' + ']' + f' {item}')