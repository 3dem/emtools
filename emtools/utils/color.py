
HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKCYAN = '\033[96m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'


class Color:
    @staticmethod
    def green(msg):
        return f'{OKGREEN}{msg}{ENDC}'

    @staticmethod
    def red(msg):
        return f'{FAIL}{msg}{ENDC}'

    @staticmethod
    def warn(msg):
        return f'{WARNING}{msg}{ENDC}'