# **************************************************************************
# *
# * Authors:  J. M. de la Rosa Trevin (delarosatrevin@gmail.com)
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
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@gmail.com'
# *
# **************************************************************************

import unittest
import tempfile
from io import StringIO  # for Python 3

from emtools.utils import Timer
from emtools.metadata import StarFile
from emtools.tests import testpath


class TestStarFile(unittest.TestCase):
    """
    Our basic test class
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

