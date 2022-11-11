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

import sys
import os
import psutil

from io import StringIO  # for Python 3
import unittest

import emtools.metadata as emd
from strings_star_relion import *

here = os.path.abspath(os.path.dirname(__file__))


def testfile(*args):
    """ Return a given testfile. """
    return os.path.join(here, *args)


def memory_usage():
    # return the memory usage in MB
    process = psutil.Process(os.getpid())
    mem = process.memory_full_info().uss / float(1 << 20)
    print("Memory (MB):", mem)
    return mem


class TestTable(unittest.TestCase):
    """
    Our basic test class
    """
    def _checkColumns(self, table, columnNames):
        for colName, col in zip(columnNames, table.getColumns()):
            self.assertEqual(colName, col.getName())

    def test_read_particles(self):
        """
        Read from a particles .star file
        """
        print("Reading particles star file...")
        f1 = StringIO(particles_3d_classify)
        t1 = emd.StarFile(f1).readTable('')
        cols = t1.getColumns()

        self.assertEqual(len(t1), 16, "Number of rows check failed!")
        self.assertEqual(len(cols), 25, "Number of columns check failed!")

        # Check that all rlnOpticsGroup is 1 and rlnImageName file is the same
        for i, row in enumerate(t1):
            self.assertEqual(row.rlnOpticsGroup, 1, "rlnOpticsGroup check failed!")
            self.assertEqual(row.rlnImageName.split("@")[1], "Extract/job012/Movies/20170629_00021_frameImage.mrcs",
                                                             "rlnImageId check failed!")

        f1.close()

    # def test_read_blocks(self):
    #     """
    #     Read an star file with several blocks
    #     """
    #     print("Reading micrograph star file...")
    #     t1 = Table()
    #     f1 = StringIO(one_micrograph_mc)
    #
    #     # This is a single-row table (different text format key, value)
    #     print("\tread data_general ..")
    #     t1.readStar(f1, tableName='general')
    #
    #     goldValues = [('rlnImageSizeX', 3710),
    #                   ('rlnImageSizeY', 3838),
    #                   ('rlnImageSizeZ', 24),
    #                   ('rlnMicrographMovieName', 'Movies/20170629_00027_frameImage.tiff'),
    #                   ('rlnMicrographGainName', 'Movies/gain.mrc'),
    #                   ('rlnMicrographBinning', 1.000000),
    #                   ('rlnMicrographOriginalPixelSize', 0.885000),
    #                   ('rlnMicrographDoseRate', 1.277000),
    #                   ('rlnMicrographPreExposure', 0.000000),
    #                   ('rlnVoltage', 200.000000),
    #                   ('rlnMicrographStartFrame', 1),
    #                   ('rlnMotionModelVersion', 1)
    #                   ]
    #
    #     self._checkColumns(t1, [k for k, v in goldValues])
    #     row = t1[0]
    #     for k, v in goldValues:
    #         self.assertEqual(getattr(row, k), v, "data_general table check failed!")
    #
    #     print("\tread data_global_shift ..")
    #     t1.readStar(f1, tableName='global_shift')
    #     cols = t1.getColumns()
    #
    #     self.assertEqual(len(t1), 24, "Number of rows check failed!")
    #     self._checkColumns(t1, ['rlnMicrographFrameNumber',
    #                             'rlnMicrographShiftX',
    #                             'rlnMicrographShiftY'])
    #
    #     print("\tread data_local_motion_model ..")
    #     t1.readStar(f1, tableName='local_motion_model')
    #
    #     self.assertEqual(len(t1), 36, "Number of rows check failed!")
    #     self._checkColumns(t1, ['rlnMotionModelCoeffsIdx',
    #                             'rlnMotionModelCoeff'])
    #     coeffs = [int(v) for v in t1.getColumnValues('rlnMotionModelCoeffsIdx')]
    #     self.assertEqual(coeffs, list(range(36)), "rlnMotionModelCoeffsIdx check failed")
    #
    #     f1.close()
    #
    # def test_write_singleRow(self):
    #     fn = '/tmp/test-single-row.star'
    #     print("Writing a single row to %s..." % fn)
    #     t = Table()
    #     f1 = StringIO(one_micrograph_mc)
    #     t.readStar(f1, tableName='global_shift')
    #     t.writeStar(sys.stdout, tableName='global_shift', singleRow=True)
    #
    #     t = Table(columns=['rlnImageSizeX',
    #                        'rlnImageSizeY',
    #                        'rlnMicrographMovieName'])
    #     t.addRow(3710, 3838, 'Movies/14sep05c_00024sq_00003hl_00002es.frames.out.mrc')
    #
    #     with open(fn, 'w') as f:
    #         t.writeStar(f, singleRow=True)
    #
    # def test_iterRows(self):
    #     print("Checking iterRows...")
    #     dataFile = testfile('star', 'refine3d', 'run_it016_data.star')
    #     table = Table(fileName=dataFile, tableName='particles')
    #
    #     # Let's open again the same file for iteration
    #     with open(dataFile) as f:
    #         tableReader = Table.Reader(f, tableName='particles')
    #
    #         for c1, c2 in zip(table.getColumns(), tableReader.getColumns()):
    #             self.assertEqual(c1, c2, "Column c1 (%s) differs from c2 (%s)"
    #                              % (c1, c2))
    #
    #             for r1, r2 in zip(table, tableReader):
    #                 self.assertEqual(r1, r2)
    #
    #     # Now try directly with iterRows function
    #     for r1, r2 in zip(table,
    #                       Table.iterRows(dataFile, tableName='particles')):
    #         self.assertEqual(r1, r2)
    #
    #     defocusSorted = sorted(float(r.rlnDefocusU) for r in table)
    #
    #     for d1, row in zip(defocusSorted,
    #                        Table.iterRows(dataFile,
    #                                       tableName='particles',
    #                                       key=lambda r: r.rlnDefocusU)):
    #         self.assertAlmostEqual(d1, row.rlnDefocusU)
    #
    #     # Test sorting by imageName column, also using getColumnValues and sort()
    #     imageIds = table.getColumnValues('rlnImageName')
    #     imageIds.sort()
    #
    #     # Check sorted iteration give the total amount of rows
    #     rows = [r for r in Table.iterRows(dataFile,
    #                                       tableName='particles',
    #                                       key='rlnImageName')]
    #     self.assertEqual(len(imageIds), len(rows))
    #
    #     for id1, row in zip(imageIds,
    #                         Table.iterRows(dataFile,
    #                                        tableName='particles',
    #                                        key='rlnImageName')):
    #         self.assertEqual(id1, row.rlnImageName)
    #
    #     def getIter():
    #         """ Test a function to get an iterator. """
    #         return Table.iterRows(dataFile,
    #                               tableName='particles', key='rlnImageName')
    #
    #     iterByIds = getIter()
    #     for id1, row in zip(imageIds, iterByIds):
    #         self.assertEqual(id1, row.rlnImageName)
    #
    # def test_removeColumns(self):
    #     print("Checking removeColumns...")
    #     dataFile = testfile('star', 'refine3d', 'run_it016_data.star')
    #     table = Table(fileName=dataFile, tableName='particles')
    #
    #     expectedCols = [
    #         'rlnCoordinateX',
    #         'rlnCoordinateY',
    #         'rlnAutopickFigureOfMerit',
    #         'rlnClassNumber',
    #         'rlnAnglePsi',
    #         'rlnImageName',
    #         'rlnMicrographName',
    #         'rlnOpticsGroup',
    #         'rlnCtfMaxResolution',
    #         'rlnCtfFigureOfMerit',
    #         'rlnDefocusU',
    #         'rlnDefocusV',
    #         'rlnDefocusAngle',
    #         'rlnCtfBfactor',
    #         'rlnCtfScalefactor',
    #         'rlnPhaseShift',
    #         'rlnGroupNumber',
    #         'rlnAngleRot',
    #         'rlnAngleTilt',
    #         'rlnOriginXAngst',
    #         'rlnOriginYAngst',
    #         'rlnNormCorrection',
    #         'rlnLogLikeliContribution',
    #         'rlnMaxValueProbDistribution',
    #         'rlnNrOfSignificantSamples',
    #         'rlnRandomSubset'
    #     ]
    #
    #     colsToRemove = [
    #         'rlnOriginXAngst',
    #         'rlnOriginYAngst',
    #         'rlnNormCorrection',
    #         'rlnAnglePsi',
    #         'rlnMaxValueProbDistribution'
    #     ]
    #
    #     # Check all columns were read properly
    #     self.assertEqual(expectedCols, table.getColumnNames())
    #     # Check also using hasAllColumns method
    #     self.assertTrue(table.hasAllColumns(expectedCols))
    #
    #     table.removeColumns(colsToRemove)
    #     self.assertEqual([c for c in expectedCols if c not in colsToRemove],
    #                      table.getColumnNames())
    #     # Check also using hasAnyColumn method
    #     self.assertFalse(table.hasAnyColumn(colsToRemove))
    #
    # def test_addColumns(self):
    #     tmpOutput = '/tmp/sampling.star'
    #     print("Checking addColumns to %s..." % tmpOutput)
    #     dataFile = testfile('star', 'refine3d', 'run_it016_sampling.star')
    #     table = Table(fileName=dataFile, tableName='sampling_directions')
    #
    #     expectedCols = ['rlnAngleRot',
    #                     'rlnAngleTilt',
    #                     'rlnAnglePsi',
    #                     'rlnExtraAngle1',
    #                     'rlnExtraAngle2',
    #                     'rlnAnotherConst'
    #                     ]
    #
    #     self.assertEqual(expectedCols[:2], table.getColumnNames())
    #
    #     table.addColumns('rlnAnglePsi=0.0',
    #                      'rlnExtraAngle1=rlnAngleRot',
    #                      'rlnExtraAngle2=rlnExtraAngle1',
    #                      'rlnAnotherConst=1000')
    #
    #     self.assertEqual(expectedCols, table.getColumnNames())
    #
    #     # Check values
    #     def _values(colName):
    #         return table.getColumnValues(colName)
    #
    #     for v1, v2, v3 in zip(_values('rlnAngleRot'),
    #                           _values('rlnExtraAngle1'),
    #                           _values('rlnExtraAngle2')):
    #         self.assertAlmostEqual(v1, v2)
    #         self.assertAlmostEqual(v1, v3)
    #
    #     self.assertTrue(all(v == 1000 for v in _values('rlnAnotherConst')))
    #
    #     table.write(tmpOutput, tableName='sampling_directions')
    #
    # def test_addRows(self):
    #     print("Checking addRows...")
    #     t1 = Table()
    #     f1 = StringIO(particles_3d_classify)
    #
    #     t1.readStar(f1)
    #     nRows = len(t1)
    #     lastRow = t1[-1]
    #
    #     values = [378.000000, 2826.000000, 5.360625, 4, -87.35289,
    #               "000100@Extract/job012/Movies/20170629_00021_frameImage.mrcs",
    #               "MotionCorr/job002/Movies/20170629_00021_frameImage.mrc",
    #               1, 4.809192, 0.131159, 10864.146484, 10575.793945, 77.995003, 0.000000,
    #               1.000000, 0.000000, 1, 81.264321, 138.043147, 4.959233, -2.12077,
    #               0.798727, 10937.130965, 0.998434, 5
    #               ]
    #
    #     for i in range(1, 4):
    #         values[4] = nRows + 1
    #         t1.addRow(*values)
    #
    #     self.assertEqual(nRows + 3, len(t1))
    #     newLastRow = t1[-1]
    #     self.assertEqual(len(lastRow), len(newLastRow))
    #
    # def test_types(self):
    #     """ Tests when providing types dict instead of guessing the type. """
    #
    #     def _checkCols(goldValues, t):
    #         """ Check expected columns and their types. """
    #         for colName, colType in goldValues.items():
    #             col = t.getColumn(colName)
    #             self.assertIsNotNone(col)
    #             self.assertEqual(colType, col.getType())
    #
    #     # Replace the micName to get a number value for that column
    #     micsStr = corrected_micrographs_mc
    #     micsStr = micsStr.replace('MotionCorr/job002/Movies/20170629_000', '')
    #     micsStr = micsStr.replace('_frameImage.mrc', '')
    #
    #     f = StringIO(micsStr)
    #     t = Table()
    #     t.readStar(f, tableName='micrographs')
    #
    #     goldValues = {'rlnCtfPowerSpectrum': str,
    #                   'rlnMicrographName': int,  # should be integer after replace
    #                   'rlnMicrographMetadata': str,
    #                   'rlnOpticsGroup': int,
    #                   'rlnAccumMotionTotal': float,
    #                   'rlnAccumMotionEarly': float,
    #                   'rlnAccumMotionLate': float
    #                   }
    #
    #     _checkCols(goldValues, t)
    #
    #     # Now parse again the table but force some columns to be str
    #     types = {'rlnMicrographName': str,
    #              'rlnOpticsGroup': str
    #              }
    #     f = StringIO(micsStr)
    #     t.readStar(f, tableName='micrographs', types=types)
    #     goldValues.update(types)
    #     _checkCols(goldValues, t)
    #

N = 100


def read_metadata():
    dataFile = testfile('star', 'refine3d', 'run_it016_sampling.star')
    tables = []
    for i in range(N):
        tables.append(Table(fileName=dataFile,
                            tableName='sampling_directions'))
    memory_usage()


def read_emcore():
    import emcore as emc
    dataFile = testfile('star', 'refine3d', 'run_it016_sampling.star')
    tables = []
    for i in range(N):
        t = emc.Table()
        t.read('sampling_directions', dataFile)
        tables.append(t)
    memory_usage()


if __name__ == '__main__':
    unittest.main()
    # read_metadata()
    # read_emcore()
