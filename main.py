from loguru import logger
import urllib3
import sys

from process import start


def main():
    configuration()
    start()


def configuration():
    urllib3.disable_warnings()
    logger.remove()
    logger.add(sys.stdout, colorize=True, format="<light-cyan>{time:HH:mm:ss}</light-cyan> | <level> {level: <8}</level> | - <white>{message}</white>")


if __name__ == '__main__':
    main()
