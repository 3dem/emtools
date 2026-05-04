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
import json
import subprocess
import traceback
import shlex
import time
from glob import glob
from uuid import uuid4
from datetime import datetime, timedelta
from contextlib import contextmanager

from emtools.utils import Color, FolderManager, Timer, Pretty, Path
from emtools.metadata import Mdoc, StarFile


class Args(dict):
    """ Subclass from dict with some utilities related to arguments. """

    def toList(self):
        args = []
        for k, v in self.items():
            args.append(str(k))
            if isinstance(v, list):
                args.extend(str(e) for e in v)
            elif v != '':
                args.append((str(v)))
        return args

    def toLine(self):
        return ' '.join("%s %s" % (k, v) for k, v in self.items())

    @staticmethod
    def fromString(string):
        return Args.fromList(shlex.split(string))

    @staticmethod
    def fromList(iterable):
        args = Args()
        for p in iterable:
            if p.startswith('--'):
                last_key = p
                args[p] = ''
            else:
                v = args[last_key]

                if v:
                    if isinstance(v, list):
                        v.append(p)
                    else:
                        v = [v, p]
                else:
                    v = p
                args[last_key] = v

        return args

    def subset(self, prefix, new_prefix='', filters=None, inverted_booleans=[], possitive=[]):
        """ Return a new Args object with a subset of the keys.
        """
        filters = filters or []
        full_prefix = f'{prefix}.'

        def _filter(k, v):
            return k.startswith(full_prefix)

        result = Args()

        for k, v in self.items():
            k_suffix = k.replace(full_prefix, '')

            if _filter(k, v):
                nk = k.replace(full_prefix, new_prefix)

                if isinstance(v, bool):
                    if 'remove_false' in filters:
                        add_boolean = not v if k_suffix in inverted_booleans else v
                        if add_boolean:
                            result[nk] = ''
                    else:
                        result[nk] = v
                else:
                    if v or 'remove_empty' not in filters:
                        if k_suffix in possitive:
                            value = float(v)
                            if value > 0:
                                result[nk] = ''
                        else:
                            result[nk] = v

        return result


class Vars:
    """ Handle variable definitions, either from input dict
    or from os.environ.
    """
    def __init__(self, vars={}):
        self._vars = vars

    def get(self, key, is_path=False):
        """ Get the var for that Key, raising exception if the var does not exist.
        If is_path = True, validates that the path exists.
        """
        value = self._vars.get(key, os.environ.get(key, None))

        if value is None:
            raise Exception(f"ERROR: Missing expected variable {key}.")

        if is_path and not os.path.exists(value):
            raise Exception(f"ERROR: Variable {key}={value} does not exist.")

        return value


class Batch(dict, FolderManager):
    """ Subclass from dict with some utilities related to Batch logic. """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        FolderManager.__init__(self, self['path'])
        self._logId = f" {self.id}:"
        self._timer = Timer()  # Create a timer to monitor batch execution
        self._timerPrefix = ''

    def clone(self):
        return Batch(self)

    @property
    def id(self):
        return self['id']

    @property
    def index(self):
        return self['index']

    @property
    def info(self):
        if 'info' not in self:
            self['info'] = {}
        return self['info']

    @property
    def error(self):
        return self.info.get('error', None)

    @error.setter
    def error(self, value):
        self.info['error'] = str(value)

    def dump_info(self):
        self.dump(self.info, 'info.json')

    def dump_all(self, fn=None):
        fileName = fn or 'batch.json'
        self.dump(self, fileName)

    def load_all(self, fn=None):
        filePath = fn or self.join('batch.json')
        with open(filePath) as f:
            self.update(json.load(f))

    def call(self, program, kwargs, logfile=None, verbose=False, cwd=True):
        """
        If cwd is True, call the program from the batch directory.
        """
        if isinstance(kwargs, dict):
            args = Args(kwargs).toList()
        elif isinstance(kwargs, list):
            args = list(kwargs)
        elif isinstance(kwargs, str):
            args = shlex.split(kwargs)
        else:
            raise Exception("Expecting dict or list as arguments")

        args.insert(0, program)
        logfile = logfile or self.join('batch.log')

        with open(logfile, 'a') as f:
            cmd = self.log(f"{Color.green(args[0])} {Color.bold(' '.join(args[1:]))}")
            f.write(f"\n{cmd}\n")
            f.flush()
            kwargs = {'stderr': f, 'stdout': f}
            if cwd:
                kwargs['cwd'] = self.path
            subprocess.call(args, **kwargs)

    def tic(self, prefix=''):
        self._timer.tic()
        self._timerPrefix = prefix

    def toc(self):
        self.info.update({
            f'{self._timerPrefix}_start': self._timer.getTic(),
            f'{self._timerPrefix}_end': Pretty.now(),
            f'{self._timerPrefix}_elapsed': str(self._timer.getElapsedTime())
        })

    @contextmanager
    def execute(self, prefix=''):
        try:
            self.tic(prefix=prefix)
            yield self
        except Exception as e:
            self.error = traceback.format_exc()
        finally:
            self.toc()


class BatchManager:
    """ Class used to generate and handle the creation of batches
    from an input stream of items.

    This is used for streaming/parallel processing. Batches will have a folder
    and a filename is extracted from each item and linked into the batch
    folder.
    """
    def __init__(self, batchSize, inputItemsIterator, workingPath,
                 itemFileNameFunc=lambda item: item.getFileName(),
                 createBatch=True):
        """
        Args:
            batchSize: Number of items that will be grouped into one batch
            inputItemsIterator: input items iterator
            workingPath: path where the batches folder will be created
            itemFileNameFunc: function to extract a filename from each item
                (by default: lambda item: item.getFileName())
        """
        self._itemsIterator = inputItemsIterator
        self._batchSize = batchSize
        self._batchCount = 0
        self._workingPath = workingPath
        self._itemFileNameFunc = itemFileNameFunc
        self._create = createBatch

    def _createBatchId(self):
        # We will use batchCount, before the batch is created
        nowPrefix = datetime.now().strftime('%y%m%d-%H%M%S')
        countStr = '%02d' % self._batchCount
        uuidSuffix = str(uuid4()).split('-')[0]
        return f"{nowPrefix}_{countStr}_{uuidSuffix}"

    def _createBatch(self, items, inputFolder=None, **batchAttrs):
        self._batchCount += 1
        batch_id = self._createBatchId()
        batch_path = os.path.join(self._workingPath, batch_id)
        batch = Batch(id=batch_id,
                      index=self._batchCount,
                      path=batch_path,
                      items=items,
                      **batchAttrs)
        if self._create:
            batch.create()
            self._createBatchLinks(batch, items, inputFolder=inputFolder)
        return batch

    def _createBatchLinks(self, batch, items, inputFolder=None):
        if inputFolder is not None:
            batch.mkdir(inputFolder)

        for item in items:
            fn = self._itemFileNameFunc(item)
            baseName = os.path.basename(fn)
            if inputFolder is not None:
                baseName = os.path.join(inputFolder, baseName)
            os.symlink(os.path.abspath(fn), batch.join(baseName))

    def generate(self):
        """ Generate batches based on the input items. """
        items = []

        for item in self._itemsIterator:
            items.append(item)

            if len(items) == self._batchSize:
                yield self._createBatch(items)
                items = []

        if items:
            yield self._createBatch(items)


class MdocBatchManager(BatchManager):
    """ Batch manager for Tilt-series. """

    def __init__(self, mdocsPattern, workingPath,
                 moviesPath=None, **kwargs):
        """
        Args:
            mdocsPattern: input pattern of Mdocs files
            workingPath: path where the batches folder will be created
            moviesPath: path where the frames pointed by Mdocs are

        Kwargs:
            wait: waiting time in seconds to check for new files
            timeout: time in seconds to quit after no new files found
            blacklist: container of tsName that have been processed or want
                to be avoided
        """
        if not glob(mdocsPattern):
            raise Exception(f"No mdoc files were found with pattern: {mdocsPattern}")

        BatchManager.__init__(self, 0, self._iterMdocs(mdocsPattern), workingPath,
                              itemFileNameFunc=lambda item: item[1]['SubFramePath'],
                              createBatch=kwargs.get('createBatch', True))
        self._moviesPath = moviesPath
        self._wait = kwargs.get('wait', 60)
        self._timeout = timedelta(seconds=kwargs.get('timeout', 3600))
        self._blacklist = set(kwargs.get('blacklist', []))

    def _iterMdocs(self, mdocsPattern):
        """ Iterate over a provided Mdocs pattern. """
        one_min = timedelta(minutes=1)

        def _newMdoc(now, fn):
            """ Return True if the file meets the following two conditions:
            - It has not been processed (in blacklist)
            - Modification time is more than 1 minute.
            """
            tsName = self._tsName(fn)
            if tsName not in self._blacklist:
                s = os.stat(fn)
                dt = datetime.fromtimestamp(s.st_mtime)
                # Ignore also sessions that have not been updated for
                # more than X days or that have not been modified since last check
                if now - dt > one_min:
                    self._blacklist.add(tsName)
                    return True
            return False

        last_found = datetime.now()
        now = datetime.now()

        def _print(msg):
            print(f"INPUT MDOCS: {Pretty.now()}: {msg}", flush=True)

        while now - last_found < self._timeout:
            _print("Checking for new mdocs")
            if new_mdocs := [fn for fn in glob(mdocsPattern) if _newMdoc(now, fn)]:
                _print(f"New mdocs found: {str(new_mdocs)}")
                for mdocFn in new_mdocs:
                    mdoc = Mdoc.parse(mdocFn)
                    mdoc['MdocFile'] = {'Path': mdocFn}
                    yield mdoc
                last_found = now
            else:
                _print("No new Mdocs found, sleeping.")

            time.sleep(self._wait)
            now = datetime.now()

    def _subframePath(self, mdocFn, section):
        movieFolder = self._moviesPath or os.path.dirname(mdocFn)
        return os.path.join(movieFolder, Mdoc.getSubFrameBase(section))

    def _tsName(self, mdocFn):
        # Remove all extensions, there are cases like .mrc.mdoc
        name = mdocFn
        while Path.getExt(name):
            name = Path.removeBaseExt(name)
        return name

    def generate(self):
        """ Generate batches based on the input items. """
        for mdoc in self._itemsIterator:
            mdocFn = mdoc['MdocFile']['Path']
            yield self._createBatch(mdoc.zvalues, mdoc=mdoc, tsName=self._tsName(mdocFn))

    def _createBatchLinks(self, batch, items, inputFolder=None):
        mdocFn = batch['mdoc']['MdocFile']['Path']

        def _absfn(item):
            return os.path.abspath(self._subframePath(mdocFn, item[1]))

        framesFolder = os.path.dirname(_absfn(items[0]))
        os.symlink(framesFolder, batch.join('frames'))

        for item in items:
            baseName = os.path.basename(_absfn(item))
            os.symlink(os.path.join('frames', baseName), batch.join(baseName))


class TsStarBatchManager(BatchManager):
    """
        Batch manager from a Relion tilt_series.star file.
        (e.g. after the TS import job)
    """

    def __init__(self, tsIterator, workingPath):
        """
        Args:
            tsIterator: input tilt-series iterator
            workingPath: path where the batches folder will be created
        """
        BatchManager.__init__(self, 0, tsIterator, workingPath,
                              itemFileNameFunc=lambda item: item.rlnMicrographMovieName)
        self._create = False  # Do not create batch folder until processing

    def generate(self):
        """ Generate batches based on the input items. """
        for tsRow in self._itemsIterator:
            tsName = tsRow.rlnTomoName
            with StarFile(tsRow.rlnTomoTiltSeriesStarFile) as sf:
                items = [row._asdict() for row in sf.iterTable(tsName)]
            yield self._createBatch(items, tsName=tsName)
