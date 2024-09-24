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
import time
from datetime import datetime as dt
from collections import OrderedDict

from .pretty import Pretty
from .process import Process


class Path:
    """
    Group some path utility functions.
    """

    class ExtDict(OrderedDict):
        """ Keep track of number of files and size by extension. """
        def register(self, filename, stat=None):
            """ Register a file, if stat is None it will be calculated. """
            if stat or os.path.exists(filename):
                stat = stat or os.stat(filename)
                ext = os.path.splitext(filename)[1]
                if ext not in self:
                    self[ext] = {'count': 0, 'size': 0}
                s = self[ext]
                s['count'] += 1
                s['size'] += stat.st_size

        def print(self, sort=None):
            f = '{:<10}{:<10}{:<15}'
            if sort:
                items = sorted(self.items(), key=lambda kv: kv[1][sort])
            else:
                items = self.items()

            for k, v in items:
                if isinstance(v, dict):
                    k = k or 'no-ext'
                    print(f.format(k, v['count'], Pretty.size(v['size'])))
                else:
                    print(f"{k}: {v}")
            print(f.format('TOTAL', self.total_count, Pretty.size(self.total_size)))

        def update(self, d, **kwargs):
            for k, v in d.items():
                if k in self:
                    sv = self[k]
                    sv['count'] += v['count']
                    sv['size'] += v['size']
                else:
                    self[k] = dict(v)

        @property
        def total_size(self):
            return sum(v['size'] for v in self.values())

        @property
        def total_count(self):
            return sum(v['count'] for v in self.values())

    @staticmethod
    def splitall(path):
        return os.path.normpath(path).split(os.path.sep)

    @staticmethod
    def addslash(path):
        """ Add an slash (/) to the end of the path if not present. """
        return path if path.endswith('/') else path + '/'

    @staticmethod
    def rmslash(path):
        """ Remove the slash (/) from the end of the path if present. """
        return path[:-1] if path.endswith('/') else path

    @staticmethod
    def inSync(dir1, dir2, verbose=False):
        """ Return True if both dir1 and dir2 are synchronized (i.e. same content)
        Use rsync as a subprocess to check if the two directories
        are synchronized. Both directories must exist.
        """
        dir1 = Path.addslash(dir1)
        dir2 = Path.addslash(dir2)

        p = Process('rsync', '--dry-run', '-a', '--stats', dir1, dir2)
        if verbose:
            p.print(stdout=True)

        transf = 1
        for line in p.lines():
            if 'files transferred:' in line:
                transf = int(line.split(':')[1])
                break
        return transf == 0

    @staticmethod
    def lastModified(folder):
        """ Return the last modified file and modified time. """
        files = os.listdir(folder)
        last = None

        for fn in files:
            f = os.path.join(folder, fn)
            s = os.stat(f)
            t = (f, s.st_mtime)
            last = t if not last or s.st_mtime > last[1] else last

        return last[0], dt.fromtimestamp(last[1])

    @staticmethod
    def copyFile(file1, file2, sleep=0):
        """ Copy two files controlling with some possible delay. """
        bufsize = 8 * 1024 * 1024
        print(f'Copying {file1} {file2}')
        with open(file1, "rb") as f1:
            with open(file2, 'wb') as f2:
                while rbytes := f1.read(bufsize):
                    f2.write(rbytes)
                    if sleep:
                        time.sleep(sleep)
        #Process.system(f'cp {file1} {file2}')

    @staticmethod
    def copyDir(dir1, dir2, copyFileFunc=None, pl=None, **kwargs):
        """ This is a test method to copy a whole directory and control
        the speed of the copy and how files appear in the destination.
        A custom copyFileFunc can be passed to copy files. If None,
        Path.copyFile will be used.
        **kwargs will be passed to copyFile
        """
        pl = pl or Process

        _copy = copyFileFunc or Path.copyFile

        def _mkdir(d):
            if not os.path.exists(d):
                pl.system(f"mkdir {d}")

        if not os.path.exists(dir1):
            raise Exception(f"Source directory must exits")

        _mkdir(dir2)

        for root, dirs, files in os.walk(dir1):
            root2 = root.replace(dir1, dir2)
            for d in dirs:
                _mkdir(os.path.join(root2, d))
            for f in files:
                _copy(os.path.join(root, f), os.path.join(root2, f), **kwargs)


    @staticmethod
    def replaceExt(filename, newExt):
        """ Replace the current path extension(from last .)
        with a new one. The new one should contain the ."""
        return Path.removeExt(filename) + newExt

    @staticmethod
    def replaceBaseExt(filename, newExt):
        """ Replace the current basename extension(from last .)
        with a new one. The new one should not contain the .
        """
        return Path.replaceExt(os.path.basename(filename), newExt)

    @staticmethod
    def removeBaseExt(filename):
        """Take the basename of the filename and remove extension"""
        return Path.removeExt(os.path.basename(filename))

    @staticmethod
    def removeExt(filename):
        """ Remove extension from basename """
        return os.path.splitext(filename)[0]

    @staticmethod
    def getExt(filename):
        """ Get filename extension """
        return os.path.splitext(filename)[1]

    @staticmethod
    def exists(path):
        """ Just avoid empty or None path to raise exception
        from os.path.exists.
        """
        return path and os.path.exists(path)

