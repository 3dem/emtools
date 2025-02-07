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
import itertools
import json
import subprocess

from emtools.utils import Process, Color, FolderManager, Pretty


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


class Batch(dict, FolderManager):
    """ Subclass from dict with some utilities related to Batch logic. """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        FolderManager.__init__(self, self['path'])

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

    def log(self, msg):
        logMsg = f"{Pretty.now()}: {self.id}: {msg}"
        print(logMsg)
        return logMsg

    def create(self):
        """ Create batch folder. """
        self.log(f"Creating folder: {self.path}")
        FolderManager.create(self, print=False)


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

    def _createBatch(self, items, inputFolder=None):
        self._batchCount += 1
        batch_id = self._createBatchId()
        batch_path = os.path.join(self._workingPath, batch_id)
        batch = Batch(id=batch_id,
                      index=self._batchCount,
                      path=batch_path,
                      items=items)
        batch.create()

        if inputFolder is not None:
            batch.mkdir(inputFolder)

        for item in items:
            fn = self._itemFileNameFunc(item)
            baseName = os.path.basename(fn)
            if inputFolder is not None:
                baseName = os.path.join(inputFolder, baseName)
            os.symlink(os.path.abspath(fn),
                       os.path.join(batch_path, baseName))

        return batch

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

