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
import unittest
import tempfile
from pprint import pprint

from emtools.utils import Timer, Color
from emtools.metadata import StarFile, EPU
from emtools.tests import testpath


class TestStarFile(unittest.TestCase):
    """
    Tests for StarFile class.
    """

    def _checkColumns(self, table, columnNames):
        for colName, col in zip(columnNames, table.getColumns()):
            self.assertEqual(colName, col.getName())

    def test_read_movieStar(self):
        """
        Read a star file with several blocks
        """
        movieStar = testpath('metadata', 'movie_frameImage.star')
        expectedTables = {
            'general': {
                'columns': ['rlnImageSizeX', 'rlnImageSizeY', 'rlnImageSizeZ',
                            'rlnMicrographMovieName', 'rlnMicrographBinning',
                            'rlnMicrographOriginalPixelSize',
                            'rlnMicrographDoseRate',
                            'rlnMicrographPreExposure',
                            'rlnVoltage',
                            'rlnMicrographStartFrame',
                            'rlnMotionModelVersion'],
                'size': 1,
            },
            'global_shift': {
                'columns': ['rlnMicrographFrameNumber',
                            'rlnMicrographShiftX',
                            'rlnMicrographShiftY'],
                'size': 24,
            },
            'local_motion_model': {
                'columns': ['rlnMotionModelCoeffsIdx', 'rlnMotionModelCoeff'],
                'size': 36,
            },
            'hot_pixels': {
                'columns': ['rlnCoordinateX',
                            'rlnCoordinateY'],
                'size': 219,
            },
            'local_shift': {
                'columns': ['rlnMicrographFrameNumber',
                            'rlnCoordinateX',
                            'rlnCoordinateY',
                            'rlnMicrographShiftX',
                            'rlnMicrographShiftY'],
                'size': 600,
            }
        }

        with StarFile(movieStar) as sf:
            # Read table in a different order as they appear in file
            # also before the getTableNames() call that create the offsets
            t1 = sf.getTable('local_shift')
            t2 = sf.getTable('general')

            self.assertEqual(set(sf.getTableNames()),
                             set(expectedTables.keys()))

            for tableName, tableInfo in expectedTables.items():
                colNames = tableInfo.get('columns', {})
                if colNames:
                    t = sf.getTable(tableName)
                    size = tableInfo['size']
                    self.assertEqual(t.size(), size)
                    self.assertEqual(sf.getTableSize(tableName), size)
                    rows = [r for r in sf.iterTable(tableName)]
                    for r1, r2 in zip(rows, t):
                        self.assertEqual(r1, r2)
                        
                    self.assertEqual(len(rows), size)
                    self._checkColumns(t, colNames)

    def test_read_particlesStar(self):
        partStar = testpath('metadata', 'particles_1k.star')

        with StarFile(partStar) as sf:
            ptable = sf.getTable('particles')
            self.assertEqual(len(ptable), 1000)
            otable = sf.getTable('optics')
            self.assertEqual(len(otable), 1)

        def _enlarge(inputStar, n):
            """ Enlarge input star file. """
            lines = []
            ftmp = tempfile.TemporaryFile('w+')
            with open(inputStar) as f:
                for line in f:
                    ftmp.write(line)
                    if 'GridSquare' in line:
                        lines.append(line)
                for i in range(n):
                    for line in lines:
                        ftmp.write(line)
            ftmp.seek(0)
            return ftmp

        n = 1000
        nn = 1000 * (n + 1)
        part1m = _enlarge(partStar, n)

        with StarFile(part1m) as sf:
            t = Timer()
            otable = sf.getTable('optics')
            t.toc('Read optics:')

            t.tic()
            ptable = sf.getTable('particles')
            t.toc(f'Read {len(ptable)} particles:')
            self.assertEqual(len(ptable), nn)

            t.tic()
            size = sf.getTableSize('particles')
            t.toc(f'Counted {size} particles:')
            self.assertEqual(size, nn)


class TestEPU(unittest.TestCase):
    """ Tests for EPU class. """

    def test_read_acquisition(self):
        fn = 'FoilHole_5850127_Data_5798426_5798428_20221104_061329.xml'
        xml = testpath('metadata', fn)

        acq = EPU.get_acquisition(xml)
        self.assertTrue(all(k in acq for k in ['camera', 'instrument',
                                               'magnification', 'pixelSize', 'voltage']))
        self.assertEqual(acq['instrument']['id'], '3788')

    def test_read_session_info(self):
        sessionPath = os.environ.get('EPU_TEST_SESSION', '')
        if not sessionPath or not os.path.exists(sessionPath):
            print(f"Please define {Color.warn('EPU_TEST_SESSION')} pointing to "
                  f"an existing data folder and run the test again.")
        else:
            print(f">>> Getting session info from: {Color.bold(sessionPath)}")
            session = EPU.get_session_info(sessionPath)
            pprint(session)
