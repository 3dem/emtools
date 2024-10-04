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

from emtools.jobs import Pipeline, BatchManager
from emtools.metadata import StarFile, StarMonitor
from emtools.utils import Pretty


class StarPipelineTester(Pipeline):
    """ Helper class to test Pipeline behaviour base on an input
    STAR file generated in streaming.
    """
    def __init__(self, inputStar, outputDir, **kwargs):
        Pipeline.__init__(self)

        self.threads = kwargs.get('threads', 4)
        self.batchSize = kwargs.get('batchSize', 128)
        self.outputDir = outputDir
        self.inputStar = inputStar
        self.outputStar = os.path.join(outputDir, 'output.star')
        self._sf = None
        self._file = None
        self.totalItems = 0

        print(f">>> {Pretty.now()}: ----------------- "
              f"Starting STAR Pipeline Tester ----------- ")

        monitor = StarMonitor(inputStar, 'particles',
                              lambda row: row.rlnImageId,
                              timeout=30)

        batchMgr = BatchManager(self.batchSize, monitor.newItems(), outputDir,
                                itemFileNameFunc=self._filename)

        g = self.addGenerator(batchMgr.generate)
        outputQueue = None
        print(f"Creating {self.threads} processing threads.")
        for _ in range(self.threads):
            p = self.addProcessor(g.outputQueue, self._process,
                                  outputQueue=outputQueue)
            outputQueue = p.outputQueue

        self.addProcessor(outputQueue, self._output)

    def _filename(self, row):
        """ Helper to get unique name from a particle row. """
        pts, stack = row.rlnImageName.split('@')
        return stack.replace('.mrcs', f'_p{pts}.mrcs')

    def _process(self, batch):
        """ Dummy function to process an input batch. """
        time.sleep(5)
        return batch

    def _output(self, batch):
        """ Compile a batch that has been 'processed'. """
        if self._sf is None:
            self._file = open(self.outputStar, 'w')
            self._sf = StarFile(self._file)
            with StarFile(self.inputStar) as sf:
                self._sf.writeTable('optics', sf.getTable('optics'))
                self._sf.writeHeader('particles', sf.getTableInfo('particles'))

        for row in batch['items']:
            self._sf.writeRow(row)
            self._file.flush()

        self.totalItems += len(batch['items'])

    def run(self):
        Pipeline.run(self)
        if self._sf is not None:
            self._sf.close()


