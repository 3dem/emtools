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

from emtools.utils import Path, Pretty, Process


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
            self.first = None
            self.first_ts = None
            self.last = None
            self.last_ts = None
            self.total = 0
            self.total_size = 0
            self._filter_func = filter_func

        def register(self, fn, stat):
            if self._filter_func is None or self._filter_func(fn):
                if self.first is None or stat.st_mtime < self.first_ts:
                    self.first = fn
                    self.first_ts = stat.st_mtime
                if self.last is None or stat.st_mtime > self.last_ts:
                    self.last = fn
                    self.last_ts = stat.st_mtime

                self.total += 1
                self.total_size += stat.st_size

        def print(self, name):
            if self.first:
                first_dt = datetime.fromtimestamp(self.first_ts)
                print(f"First {name}: "
                      f"\n\tpath: {self.first}"
                      f"\n\ttime: {first_dt}")
            if self.last:
                last_dt = datetime.fromtimestamp(self.last_ts)
                print(f"Last {name}: "
                      f"\n\tpath: {self.last}"
                      f"\n\ttime: {last_dt}")

            if self.first and self.last_ts:
                print(f"Duration: {(last_dt - first_dt).seconds / 3600:0.2f} hours")

            print(f"Total {name}s: {self.total}, size: {Pretty.size(self.total_size)}")

        def info(self):
            fts = datetime.fromtimestamp(self.first_ts) if self.first else None
            lts = datetime.fromtimestamp(self.last_ts) if self.last else None
            duration = f"{(lts - fts).seconds / 3600:0.2f} hours" if fts and lts else 'None'

            return {
                'first_ts': str(fts),
                'last_ts': str(lts),
                'duration': duration
            }

    def __init__(self, filters=[], root=None):
        self.root = Path.addslash(root) if root else None
        self._ed = Path.ExtDict()
        self._total_dirs = 0
        self._index_files = set()
        self.counters = [DataFiles.Counter()]
        for cf in filters:
            self.counters.append(DataFiles.Counter(filter_func=cf))

    def scan(self, folder):
        """ Scan a folder and register all files recursively. """
        self.root = Path.addslash(folder)

        for root, dirs, files in os.walk(folder):
            for fn in files:
                self.register(os.path.join(root, fn))
            self._total_dirs += len(dirs)

    def register(self, filename, stat=None):
        """ Register a file, if stat is None it will be calculated. """
        if stat or os.path.exists(filename):
            fn = filename.replace(self.root, '')
            if fn not in self._index_files:
                self._index_files.add(fn)
                stat = stat or os.stat(filename)
                # Register for each type of counter
                for c in self.counters:
                    c.register(fn, stat)
                # Register for file extension stats
                self._ed.register(filename, stat=stat)
                return True
        return False

    @property
    def total_files(self):
        return self.counters[0].total

    @property
    def total_size(self):
        return self.counters[0].total_size

    def __contains__(self, filename):
        fn = filename.replace(self.root, '')
        return fn in self._index_files

    def print(self, sort=None):
        self._ed.print(sort=sort)
        print("=======================================")
        print(f"Total dirs: {self._total_dirs}")
        print(f"Total files: {self.total_files}")
        self.counters[0].print('file')


class MovieFiles(DataFiles):
    """ Extension of DataFiles that counts also movie files. """
    def __init__(self, **kwargs):
        DataFiles.__init__(self, filters=[self.is_movie], **kwargs)
        self._moviesSuffix = kwargs.get('moviesSuffix',
                                        ['fractions.tiff', '.eer'])

    def is_movie(self, fn):
        return any(fn.endswith(s) for s in self._moviesSuffix)

    def info(self):
        """ Return a dict with some info """

        if self.total_files == 0:
            return {}

        fc = self.counters[0]  # files counter
        fcInfo = fc.info()
        mc = self.counters[1]  # movies counter
        mcInfo = mc.info()
        total_size = self._ed.total_size

        return {
            'files': self._ed,
            'files_total': fc.total,
            'size': total_size,
            'sizeH': Pretty.size(total_size),
            'first_file': fc.first,
            'first_file_creation': fc.first_ts,
            'last_file': fc.last,
            'last_file_creation': fc.last_ts,
            'movies': mc.total,
            'first_movie': mc.first,
            'first_movie_creation': mc.first_ts,
            'last_movie': mc.last,
            'last_movie_creation': mc.last_ts,
            'duration': fcInfo['duration']
        }

    @property
    def total_movies(self):
        return self.counters[1].total

    def print(self, sort=None):
        DataFiles.print(self, sort=sort)
        self.counters[1].print('movie')
