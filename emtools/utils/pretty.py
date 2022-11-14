import math
import os
from datetime import datetime


class Pretty:
    # Default timestamp
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    DATE_FORMAT = '%Y-%m-%d'

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
    def delta(td):
        """ Remove the milliseconds of the timedelta. """
        return str(td).split('.')[0]

    @staticmethod
    def date(dt, **kwargs):
        return dt.strftime(kwargs.get('format', Pretty.DATE_FORMAT))

    @staticmethod
    def datetime(dt, **kwargs):
        return dt.strftime(kwargs.get('format', Pretty.DATETIME_FORMAT))

    @staticmethod
    def timestamp(timestamp, **kwargs):
        return Pretty.datetime(datetime.fromtimestamp(timestamp), **kwargs)

    @staticmethod
    def parse_datetime(dt_str, **kwargs):
        f = kwargs.get('format', Pretty.DATETIME_FORMAT)
        return datetime.strptime(dt_str, f)

    @staticmethod
    def modified(fn, **kwargs):
        if not os.path.exists(fn):
            return None
        f = kwargs.get('format', Pretty.DATETIME_FORMAT)
        dt = datetime.fromtimestamp(os.stat(fn).st_mtime)
        return dt if f is None else Pretty.datetime(dt, **kwargs)

