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

from emtools.utils import Process


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

    def _createBatch(self, items):
        batch_id = self._createBatchId()
        batch_path = os.path.join(self._workingPath, batch_id)
        print(f"Creating batch: {batch_path}")
        Process.system(f"rm -rf '{batch_path}'")
        Process.system(f"mkdir '{batch_path}'")

        for item in items:
            fn = self._itemFileNameFunc(item)
            baseName = os.path.basename(fn)
            os.symlink(os.path.abspath(fn),
                       os.path.join(batch_path, baseName))
        self._batchCount += 1
        return {
            'items': items,
            'id': batch_id,
            'path': batch_path,
            'index': self._batchCount
        }

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
