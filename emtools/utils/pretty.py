import math
from datetime import datetime


class Pretty:
    @staticmethod
    def size(size):
        """ Human friendly file size. """
        unit_list = list(zip(['bytes', 'kB', 'MB', 'GB', 'TB', 'PB'],
                             [0, 0, 1, 2, 2, 2]))
        if size > 1:
            exponent = min(int(math.log(size, 1024)), len(unit_list) - 1)
            quotient = float(size) / 1024 ** exponent
            unit, num_decimals = unit_list[exponent]
            format_string = '{:.%sf} {}' % num_decimals
            return format_string.format(quotient, unit)
        if size == 0:
            return '0 bytes'
        if size == 1:
            return '1 byte'

    @staticmethod
    def timestamp(timestamp, tsformat='%Y-%m-%d %H:%M:%S'):
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime(tsformat)

