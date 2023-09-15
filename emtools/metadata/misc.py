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

import os
from datetime import datetime, timedelta

from emtools.utils import Path


class Bins:
    def __init__(self, delimiters):
        if not delimiters:
            raise Exception("At least one delimiter should be provided")

        self.bins = [0] * (len(delimiters) + 1)
        self.delimiters = delimiters
        self.total = 0

    def addValue(self, v):
        added = False
        for i, d in enumerate(self.delimiters):
            if v < d:
                self.bins[i] += 1
                added = True
                break
        if not added:
            self.bins[-1] += 1
        self.total += 1

    def print(self):
        print("Total: ", self.total)
        for label, b, p in self:
            print(f"{label:<10} {b:>7} {p:>6.2f}%")

    def toList(self):
        return list(iter(self))

    def __iter__(self):
        if not self.total:
            return

        for i, b in enumerate(self.bins):
            p = round((b * 100.0) / self.total, 2)
            if i == 0:
                label = "< %s" % self.delimiters[0]
            elif i == len(self.delimiters):
                label = "> %s" % self.delimiters[i-1]
            else:
                label = "> %s and < %s" % (self.delimiters[i-1],
                                           self.delimiters[i])

            yield label, b, p


class TsBins(Bins):
    def __init__(self, items, binSize=60):
        """
        Initialize the TimestampBins instance.
        Args:
            items: Items list sorted by timestamps. Each item should have
                a item['ts'] key with the timestamp value.
            binSize: size of the bins in minutes
        """
        # Compute bin delimiters based on binSize and first and last items
        first = items[0]
        last = items[-1]
        last_ts = datetime.fromtimestamp(last['ts'])
        bindelta = timedelta(minutes=binSize)
        delimiters = [datetime.fromtimestamp(first['ts']) + bindelta]

        while delimiters[-1] < last_ts:
            delimiters.append(delimiters[-1] + bindelta)

        Bins.__init__(self, delimiters)
        for item in items:
            self.addValue(datetime.fromtimestamp(item['ts']))


class DataFiles:
    """ Keep track of a Session data files.
    Mainly statistics about files in a dataset, but
    can also be used to maintain a record of transferred files.
    """
    class Counter:
        """ Count first, last and total number of files.
        A filter function can be passed to track only filenames
        that the filter return True.
        """
        def __init__(self, name='', filter_func=None):
            self._first = None
            self._first_ts = None
            self._last = None
            self._last_ts = None
            self.total = 0
            self._filter_func = filter_func

        def register(self, fn, stat):
            if self._filter_func is None or self._filter_func(fn):
                if self._first is None or stat.st_mtime < self._first_ts:
                    self._first = fn
                    self._first_ts = stat.st_mtime
                if self._last is None or stat.st_mtime > self._last_ts:
                    self._last = fn
                    self._last_ts = stat.st_mtime

                self.total += 1

        def print(self, name):
            if self._first:
                first_dt = datetime.fromtimestamp(self._first_ts)
                print(f"First {name}: "
                      f"\n\tpath: {self._first}"
                      f"\n\ttime: {first_dt}")
            if self._last:
                last_dt = datetime.fromtimestamp(self._last_ts)
                print(f"Last {name}: "
                      f"\n\tpath: {self._last}"
                      f"\n\ttime: {last_dt}")

            if self._first and self._last_ts:
                print(f"Duration: {(last_dt - first_dt).seconds / 3600:0.2f} hours")

    def __init__(self, filters=[]):
        self._root = None
        self._ed = Path.ExtDict()
        self._total_dirs = 0
        self._index_files = set()
        self.counters = [DataFiles.Counter()]
        for cf in filters:
            self.counters.append(DataFiles.Counter(filter_func=cf))

    def scan(self, folder):
        """ Scan a folder and register all files recursively. """
        self._root = folder

        for root, dirs, files in os.walk(folder):
            for fn in files:
                self.register(os.path.join(root, fn))
            self._total_dirs += len(dirs)

    def register(self, filename, stat=None):
        """ Register a file, if stat is None it will be calculated. """
        if os.path.exists(filename):
            fn = filename.replace(self._root, '')
            if fn not in self._index_files:
                self._index_files.add(fn)
                stat = stat or os.stat(filename)

                for c in self.counters:
                    c.register(fn, stat)
                # Track first and last file based on modification time

                self._ed.register(filename, stat=stat)

    @property
    def total_files(self):
        return self.counters[0].total

    def info(self):
        """ Return a dict with some info """

        if self.total_files == 0:
            return {}

        def _rowInfo(row):
            dt = datetime.fromtimestamp(row.timeStamp)
            return row.timeStamp, dt, row.movieBaseName

        firstTs, firstCreation, firstMovie = _rowInfo(self.moviesTable[0])
        lastTs, lastCreation, lastMovie = _rowInfo(self.moviesTable[-1])
        hours = (lastCreation - firstCreation).seconds / 3600

        return {
            'movies': len(self.moviesTable),
            'first_movie': firstMovie,
            'first_movie_creation': firstTs,
            'last_movie': lastMovie,
            'last_movie_creation': lastTs,
            'duration': f'{hours:0.2f} hours',
        }

    def __contains__(self, item):
        return item in self._index_files

    def print(self, sort=None):
        self._ed.print(sort=sort)
        print("=======================================")
        print(f"Total dirs: {self._total_dirs}")
        print(f"Total files: {self.total_files}")
        self.counters[0].print('file')

