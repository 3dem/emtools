# **************************************************************************
# *
# * Authors:     J.M. de la Rosa Trevin (delarosatrevin@gmail.com)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# **************************************************************************

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
    """ Basic helper class to have colored string.
    Useful for commands and log messages. """

    @staticmethod
    def green(msg):
        return f'{OKGREEN}{msg}{ENDC}'

    @staticmethod
    def red(msg):
        return f'{FAIL}{msg}{ENDC}'

    @staticmethod
    def warn(msg):
        return f'{WARNING}{msg}{ENDC}'

    @staticmethod
    def bold(msg):
        return f'{BOLD}{msg}{ENDC}'

    @staticmethod
    def cyan(msg):
        return f'{OKCYAN}{msg}{ENDC}'

    @staticmethod
    def blue(msg):
        return f'{OKBLUE}{msg}{ENDC}'
