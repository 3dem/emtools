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

import math
import os
from datetime import datetime


class Pretty:
    """ Helper class for "pretty" string formatting from several input types
    (e.g. size, dates, timestamps, elapsed, etc.).
    """
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
    def now(**kwargs):
        return Pretty.datetime(datetime.now(), **kwargs)

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

    @staticmethod
    def elapsed(timestamp, now=None):
        """
        Get a datetime object or a int() Epoch timestamp and return a
        pretty string like 'an hour ago', 'Yesterday', '3 months ago',
        'just now', etc
        """
        now = now or datetime.now()
        if isinstance(timestamp, datetime):
            ts = timestamp
        elif type(timestamp) in [int, float, str]:
            ts = datetime.fromtimestamp(int(timestamp))
        else:
            raise Exception(f"Can not convert type {type(timestamp)} to timestamp")

        diff = now - ts
        second_diff = diff.seconds
        day_diff = diff.days

        if day_diff < 0:
            return ''

        if day_diff == 0:
            if second_diff < 10:
                return "just now"
            if second_diff < 60:
                return str(second_diff) + " seconds ago"
            if second_diff < 120:
                return "a minute ago"
            if second_diff < 3600:
                return str(int(second_diff / 60)) + " minutes ago"
            if second_diff < 7200:
                return "an hour ago"
            if second_diff < 86400:
                return str(int(second_diff / 3600)) + " hours ago"
        if day_diff == 1:
            return "Yesterday"
        if day_diff < 7:
            return str(day_diff) + " days ago"

        def _plural(div, noun):
            v = int(day_diff / div)
            s = 's' if v > 1 else ''
            return f"{v} {noun}{s} ago"

        if day_diff < 31:
            return _plural(7, 'week')
        if day_diff < 365:
            return _plural(30, 'month')

        return _plural(365, 'year')


