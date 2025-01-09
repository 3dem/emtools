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

from emtools.utils import Process, Color


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


class Batch(dict):
    """ Subclass from dict with some utilities related to Batch logic. """
    @property
    def id(self):
        return self['id']

    @property
    def path(self):
        return self['path']

    @property
    def index(self):
        return self['index']

    @property
    def items(self):
        return self['items']

    @property
    def info(self):
        if 'info' not in self:
            self['info'] = {}
        return self['info']

    def join(self, *p):
        return os.path.join(self['path'], *p)

    def relpath(self, p):
        return os.path.relpath(p, self.path)

    def mkdir(self, *p):
        d = self.join(*p)
        os.mkdir(d)
        return d

    def exists(self, *p):
        return os.path.exists(self.join(*p))

    def dump_info(self):
        with open(self.join('info.json'), 'w') as batch_info:
            json.dump(self.info, batch_info, indent=4)

    def call(self, program, kwargs, logfile):
        args = [program] + Args(kwargs).toList()
        with open(logfile, 'w') as f:
            cmd = f">>> {Color.green(args[0])} {Color.bold(' '.join(args[1:]))}"
            print(cmd)
            f.write(f"\n{cmd}\n")
            subprocess.call(args, cwd=self.path, stderr=f, stdout=f)


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
        countStr = '%02d' % (self._batchCount + 1)
        uuidSuffix = str(uuid4()).split('-')[0]
        return f"{nowPrefix}_{countStr}_{uuidSuffix}"

    def _createBatch(self, items, inputFolder=None):
        batch_id = self._createBatchId()
        batch_path = os.path.join(self._workingPath, batch_id)
        print(f"Creating batch: {batch_path}")
        Process.system(f"rm -rf '{batch_path}'")
        Process.system(f"mkdir '{batch_path}'")
        if inputFolder is not None:
            Process.system(f"mkdir '{batch_path}/{inputFolder}'")

        for item in items:
            fn = self._itemFileNameFunc(item)
            baseName = os.path.basename(fn)
            if inputFolder is not None:
                baseName = os.path.join(inputFolder, baseName)
            os.symlink(os.path.abspath(fn),
                       os.path.join(batch_path, baseName))

        self._batchCount += 1
        return Batch({
            'items': items,
            'id': batch_id,
            'path': batch_path,
            'index': self._batchCount
        })

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

