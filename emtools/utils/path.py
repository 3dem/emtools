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
import shutil
import time
import tempfile
import json
from glob import glob
from datetime import datetime as dt
from collections import OrderedDict
from contextlib import contextmanager

from .pretty import Pretty
from .process import Process
from .color import Color


GLOB_CHARS = ['*', '?', '[', ']']

IMAGE_EXT = ['tiff', 'tif', 'png', 'jpg', 'jpeg']
TEXT_EXT = ['txt', 'log', 'err', 'out', 'json', 'csv']


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
        """ Add a slash (/) to the end of the path if not present. """
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
        return Path.rsync(dir1, dir2, '--dry-run', verbose=verbose) == 0

    @staticmethod
    def rsync(dir1, dir2, *args,
              verbose=False,
              size=False):
        """ Run rsync to synchronize dir1 and dir2 are synchronized (i.e. same content)
        Use rsync as a subprocess to synchronize dir1 and dir2 and return
        the number of files transferred.
        Args:
            dir1: source directory
            dir2: destination directory
            *args: extra arguments to rsync
            verbose: If True, print the command to stdout
            size: If True, a tuple is returned with transferred files and transferred data size
        """
        dir1 = Path.addslash(dir1)
        dir2 = Path.addslash(dir2)

        cmd = ['rsync', '-a', '--stats'] + list(args) + [dir1, dir2]
        p = Process(*cmd, doRaise=True)

        if verbose:
            p.print(stdout=True)

        def _value(line):
            # Get the value after the colon (:)
            # and remove , that is used to separate thousands
            return int(line.split(':')[1].replace(',', ''))

        transf = 0
        transfSize = 0

        for line in p.lines():
            if 'Number of regular files transferred:' in line:
                transf = _value(line)
            elif 'Total transferred file size:' in line:
                transfSize = _value(line.replace('bytes', ''))

        return (transf, transfSize) if size else transf


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

        if last:
            return last[0], dt.fromtimestamp(last[1])
        else:
            return None, None

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
    @contextmanager
    def tmpDir(**kwargs):
        tmp = tempfile.mkdtemp(prefix=kwargs.get('prefix', ''))

        chdir = kwargs.get('chdir', False)
        cwd = os.getcwd()
        if chdir:
            os.chdir(tmp)

        if kwargs.get('verbose', True):
            print(f"Using temporary dir: {tmp}")

        yield tmp

        if chdir:
            os.chdir(cwd)

        globalClean = int(os.environ.get('EMWRAP_CLEAN', 1))
        if kwargs.get('clean', globalClean):
            shutil.rmtree(tmp)
        else:
            print(f"Temporary directory was not deleted, "
                  f"remove it with the following command: \n"
                  f"{Color.bold('rm -rf %s' % tmp)}")

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

    @staticmethod
    def isPattern(path):
        return any(c in path for c in GLOB_CHARS)

    @staticmethod
    def isImage(path):
        return Path.getExt(path).lower()[1:] in IMAGE_EXT

    @staticmethod
    def isText(path):
        return Path.getExt(path).lower()[1:] in TEXT_EXT


class FolderManager:
    """ Helper class with some path utilities from a given path. """
    def __init__(self, path):
        self.__path = path
        self._logId = ""
        self.__extraLog = None

    def join(self, *p):
        return os.path.join(self.__path, *p)

    def relpath(self, p):
        return os.path.relpath(p, self.path)

    def mkdir(self, *p, **kwargs):
        d = self.join(*p)
        Process.system(f"mkdir -p '{d}'", **kwargs)
        return d

    def exists(self, *p):
        return os.path.exists(self.join(*p))

    @property
    def path(self):
        return self.__path

    @path.setter
    def path(self, value):
        self.__path = value

    def create(self, **kwargs):
        """ Create batch folder. """
        self.log(f"Creating folder: {self.path}")
        Process.system(f"rm -rf '{self.path}'", **kwargs)
        Process.system(f"mkdir -p '{self.path}'", **kwargs)

    def log(self, msg, flush=False):
        logMsg = f"{Pretty.now()}:{self._logId} {msg}"
        print(logMsg, flush=flush)
        if self.__extraLog:
            self.__extraLog(logMsg, flush=flush)
        return logMsg

    def setExtraLog(self, logFunc):
        self.__extraLog = logFunc

    def listdir(self):
        """ Return files relative to the path. """
        return os.listdir(self.path)

    def glob(self, pattern):
        return glob(self.join(pattern))

    def dump(self, obj, fn):
        filePath = self.join(fn)
        with open(filePath, 'w') as f:
            json.dump(obj, f, indent=4)

    def rename(self, oldFn, newFn):
        os.rename(self.join(oldFn), self.join(newFn))

    def link(self, fn, absolute=False, name=None):
        """ Link a file inside the folder and return the basename.
        If name is None, the basename of the fn will be used.
        """
        base = name or os.path.basename(fn)
        src = os.path.abspath(fn) if absolute else self.relpath(fn)
        os.symlink(src, self.join(base))
        return base

    def copy(self, *paths):
        """ Copy one or many files into the path. """
        for p in paths:
            shutil.copy(p, self.__path)

