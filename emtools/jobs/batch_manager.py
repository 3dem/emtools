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
from uuid import uuid4
from datetime import datetime
import json
import subprocess
import traceback
from contextlib import contextmanager

from emtools.utils import Color, FolderManager, Timer, Pretty, Path
from emtools.metadata import Mdoc


class Args(dict):
    """ Subclass from dict with some utilities related to arguments. """

    def toList(self):
        args = []
        for k, v in self.items():
            args.append(str(k))
            if v != '':
                args.append((str(v)))
        return args

    def toLine(self):
        return ' '.join("%s %s" % (k, v) for k, v in self.items())


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

    def dump(self, obj, fn):
        filePath = self.join(fn)
        with open(filePath, 'w') as f:
            json.dump(obj, f, indent=4)

    def dump_info(self):
        self.dump(self.info, 'info.json')

    def dump_all(self):
        self.dump(self, 'batch.json')

    def load_all(self):
        with open(self.join('batch.json')) as f:
            self.update(json.load(f))

    def call(self, program, kwargs, logfile=None, verbose=False, cwd=True):
        """
        If cwd is True, call the program from the batch directory.
        """
        if isinstance(kwargs, dict):
            args = Args(kwargs).toList()
        elif isinstance(kwargs, list):
            args = list(kwargs)
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
            f'{self._timerPrefix}start': self._timer.getTic(),
            f'{self._timerPrefix}end': Pretty.now(),
            f'{self._timerPrefix}elapsed': str(self._timer.getElapsedTime())
        })

    @contextmanager
    def execute(self):
        try:
            self.tic()
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
                 itemFileNameFunc=lambda item: item.getFileName()):
        """
        Args:
            batchSize: Number of items that will be grouped into one batch
            inputItemsIterator: input items iterator
            workingPath: path where the batches folder will be created
            itemFileNameFunc: function to extract a filename from each item
                (by default: lambda item: item.getFileName())
        """
        self._items = inputItemsIterator
        self._batchSize = batchSize
        self._batchCount = 0
        self._workingPath = workingPath
        self._itemFileNameFunc = itemFileNameFunc

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

        for item in self._items:
            items.append(item)

            if len(items) == self._batchSize:
                yield self._createBatch(items)
                items = []

        if items:
            yield self._createBatch(items)


class MdocBatchManager(BatchManager):
    """ Batch manager for Tilt-series. """

    def __init__(self, tsIterator, workingPath, suffix=None, movies=None):
        """
        Args:
            tsIterator: input tilt-series iterator
            workingPath: path where the batches folder will be created
            suffix: suffix to be removed from mdoc filename to generate
                the tilt-series name
        """
        BatchManager.__init__(self, 0, tsIterator, workingPath,
                              itemFileNameFunc=lambda item: item[1]['SubFramePath'])
        self._suffix = suffix
        self._movies = movies

    def _subframePath(self, mdocFn, section):
        movieFolder = self._movies or os.path.dirname(mdocFn)
        return os.path.join(movieFolder, Mdoc.getSubFrameBase(section))

    def _tsName(self, mdocFn):
        name = Path.removeBaseExt(mdocFn)
        if self._suffix:
            name = name.replace(self._suffix, '')
        return name

    def generate(self):
        """ Generate batches based on the input items. """
        for mdoc in self._items:
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