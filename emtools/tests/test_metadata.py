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
import random
import time
import threading
import tempfile
from pprint import pprint
from datetime import datetime

from emtools.utils import Timer, Color, Pretty
from emtools.metadata import StarFile, SqliteFile, EPU, StarMonitor
from emtools.jobs import BatchManager
from emtools.tests import testpath

from .star_pipeline_tester import StarPipelineTester

# Try to load starfile library to launch some comparisons
try:
    import starfile
except:
    starfile = None

try:
    import emtable
except:
    emtable = None


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
        if movieStar is None:
            return

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
            self.assertGreater(len(t1), 0)
            t2 = sf.getTable('general')
            self.assertGreater(len(t2), 0)

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

    def test_getTableRow(self):
        movieStar = testpath('metadata', 'movie_frameImage.star')
        if movieStar is None:
            return

        with StarFile(movieStar) as sf:
            t1 = sf.getTable('global_shift')  # 600 rows
            for i in [0, 1, 2, 23]:
                row = sf.getTableRow('global_shift', i)
                self.assertEqual(row, t1[i])

            t2 = sf.getTable('general')  # 1 row
            row = sf.getTableRow('general', 0)
            self.assertEqual(row, t2[0])

    def test_read_particlesStar(self):
        partStar = testpath('metadata', 'particles_1k.star')
        if partStar is None:
            return

        with StarFile(partStar) as sf:
            ptable = sf.getTable('particles')
            self.assertEqual(len(ptable), 1000)
            otable = sf.getTable('optics')
            self.assertEqual(len(otable), 1)

        ftmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.star')
        print(f">>>> {ftmp.name}")

        def _enlarge(inputStar, n):
            """ Enlarge input star file. """
            lines = []
            with open(inputStar) as f:
                for line in f:
                    ftmp.write(line)
                    if 'GridSquare' in line:
                        lines.append(line)
                for i in range(n):
                    for line in lines:
                        ftmp.write(line)
            ftmp.seek(0)

        n = 1000
        nn = 1000 * (n + 1)
        _enlarge(partStar, n)

        ftmp.close()

        print(Color.cyan(f"Testing starfile with {nn} particles"))

        t = Timer()
        tmpStar = ftmp.name

        with StarFile(tmpStar) as sf:
            t.tic()
            otable = sf.getTable('optics')
            t.toc('Read optics:')

            t.tic()
            size = sf.getTableSize('particles')
            t.toc(f'Counted {size} particles:')
            self.assertEqual(size, nn)

            t.tic()
            ptable = sf.getTable('particles')
            t.toc(f'Read {len(ptable)} particles:')
            self.assertEqual(len(ptable), nn)

        if emtable:
            t.tic()
            table = emtable.Table(fileName=tmpStar, tableName='particles')
            t.toc("Read with 'emtable'")

        if starfile:
            t.tic()
            df = starfile.read(tmpStar)
            t.toc("Read with 'starfile'")

        os.unlink(ftmp.name)

    def test_read_jobstar(self):
        jobStar = testpath('metadata', 'relion5_job002_job.star')
        if jobStar is None:
            return

        expected_values = {
            'bfactor': '150',
            'bin_factor': '1',
            'do_dose_weighting': 'Yes',
            'do_queue': 'No',
            'dose_per_frame': '1.277',
            'eer_grouping': '32',
            'first_frame_sum': '1',
            'fn_defect': '',
            'fn_gain_ref': 'Movies/gain.mrc',
            'gain_flip': 'No flipping (0)'
        }

        def _checkValues(t):
            values = {row.rlnJobOptionVariable: row.rlnJobOptionValue for row in t}
            for k, v in expected_values.items():
                #print(f"{k} = {v}")
                self.assertEqual(v, values[k])

        expected_tables = ['job', 'joboptions_values']
        with StarFile(jobStar) as sf:
            print(f"Tables: {sf.getTableNames()}")
            self.assertEqual(expected_tables, sf.getTableNames())
            t1 = sf.getTable('joboptions_values', guessType=False)
            _checkValues(t1)

        # Test that we can write values
        # with empty string and spaces
        ftmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.star')
        print(f">>>> Writting to {ftmp.name}")

        with StarFile(ftmp) as sf:
            sf.writeTable('joboptions', t1)

        ftmp.close()

        with StarFile(ftmp.name) as sf:
            t2 = sf.getTable('joboptions', guessType=False)
            _checkValues(t2)

        os.unlink(ftmp.name)

    def __test_star_streaming(self, monitorFunc, inputStreaming=True):
        partStar = testpath('metadata', 'particles_1k.star')
        if partStar is None:
            return

        N = 1000

        with StarFile(partStar) as sf:
            ptable = sf.getTable('particles')
            self.assertEqual(len(ptable), N)
            otable = sf.getTable('optics')
            self.assertEqual(len(otable), 1)

        ftmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.star')
        print(f">>>> Using temporary file: {ftmp.name}")

        def _write_star_parts():
            with StarFile(ftmp) as sfOut:
                sfOut.writeTable('optics', otable)
                if inputStreaming:
                    sfOut.writeHeader('particles', ptable)
                    u = int(random.uniform(5, 10))
                    s = u * 10
                    w = 0
                    for i, row in enumerate(ptable):
                        if i == s:
                            print(f"{w} rows written.")
                            ftmp.flush()
                            time.sleep(3)
                            u = int(random.uniform(5, 10))
                            s = i + u * 10
                            w = 0
                        sfOut.writeRow(row)
                        w += 1
                else:
                    sfOut.writeTable('particles', ptable)
                    w = len(ptable)

                print(f"{w} rows written.")

        th = threading.Thread(target=_write_star_parts)
        print(">>> Starting thread...")
        th.start()

        monitor = StarMonitor(ftmp.name, 'particles',
                              lambda row: row.rlnImageId,
                              timeout=30)

        totalCount = monitorFunc(monitor)
        self.assertEqual(totalCount, N)

        print("<<< Waiting for thread")
        th.join()

        ftmp.close()

        # Check output is what we expect
        with StarFile(ftmp.name) as sf:
            ptable = sf.getTable('particles')
            self.assertEqual(len(ptable), N)
            otable = sf.getTable('optics')
            self.assertEqual(len(otable), 1)

        os.unlink(ftmp.name)

    def test_star_monitor(self):
        """ Basic test checking that we are able to monitor a streaming
        generated star file. The final count of rows should be the
        same as the input one.
        """
        def _monitor(monitor):
            totalRows = 0
            while not monitor.timedOut():
                newRows = monitor.update()
                n = len(newRows)
                totalRows += n
                print(f"New rows: {n}")
                print(f"Last update: {Pretty.datetime(monitor.lastUpdate)} "
                      f"Last check: {Pretty.datetime(monitor.lastCheck)} "
                      f"No activity: {Pretty.delta(monitor.lastCheck - monitor.lastUpdate)}")
                time.sleep(5)
            return totalRows

        self.__test_star_streaming(_monitor)

    def test_star_batchmanager(self):
        """ Testing the creating of batches from an input star monitor
        using different batch sizes.
        """

        def _filename(row):
            """ Helper to get unique name from a particle row. """
            pts, stack = row.rlnImageName.split('@')
            return stack.replace('.mrcs', f'_p{pts}.mrcs')

        def _batchmanager(monitor, batchSize):
            totalFiles = 0

            with tempfile.TemporaryDirectory() as tmp:
                print(f"Using dir: {tmp}")

                batchMgr = BatchManager(batchSize, monitor.newItems(), tmp,
                                        itemFileNameFunc=_filename)

                for batch in batchMgr.generate():
                    files = len(os.listdir(batch['path']))
                    print(f"Batch {batch['id']} -> {batch['path']}, files: {files}")
                    totalFiles += files

            return totalFiles

        self.__test_star_streaming(lambda m: _batchmanager(m, 128))
        self.__test_star_streaming(lambda m: _batchmanager(m, 200))

    def test_star_pipeline(self):
        def _pipeline(monitor):
            with tempfile.TemporaryDirectory() as tmp:
                print(f"Using dir: {tmp}")
                p = StarPipelineTester(monitor.fileName, tmp)
                p.run()
                return p.totalItems

        #self.__test_star_streaming(_pipeline, inputStreaming=True)
        self.__test_star_streaming(_pipeline, inputStreaming=False)


class TestEPU(unittest.TestCase):
    """ Tests for EPU class. """

    def test_read_acquisition(self):
        fn = 'FoilHole_5850127_Data_5798426_5798428_20221104_061329.xml'
        xml = testpath('metadata', fn)
        if xml is None:
            return

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



class TestSqliteFile(unittest.TestCase):
    """
    Tests for StarFile class.
    """
    BASIC_TABLES = ['Properties', 'Classes', 'sqlite_sequence', 'Objects']

    def _checkColumns(self, table, columnNames):
        for colName, col in zip(columnNames, table.getColumns()):
            self.assertEqual(colName, col.getName())

    def test_readMovies(self):
        movieSqlite = testpath('metadata', 'scipion', 'movies.sqlite')
        if movieSqlite is None:
            return

        with SqliteFile(movieSqlite) as sf:
            self.assertEqual(sf.getTableNames(), self.BASIC_TABLES)

            self.assertEqual(sf.getTableSize('Objects'), 3775)

            props = [row for row in sf.iterTable('Properties')]
            self.assertEqual(len(props), 22)

            # Retrieve only 10 items starting from the beginning
            props2 = [row for row in sf.iterTable('Properties', limit=10)]
            self.assertEqual(len(props2), 10)

            # Retrieve all items starting from item 10th
            props3 = [row for row in sf.iterTable('Properties', start=9)]
            self.assertEqual(len(props3), len(props) - 9)
            self.assertEqual(props[9], props3[0])

    def test_getTableRow(self):
        movieSqlite = testpath('metadata', 'scipion', 'movies.sqlite')
        if movieSqlite is None:
            return

        with SqliteFile(movieSqlite) as sf:
            t1 = [row for row in sf.iterTable('Objects')]
            for i in [0, 1, 2, 3774]:
                row = sf.getTableRow('Objects', i)
                self.assertEqual(row, t1[i])

            t2 = [row for row in sf.iterTable('Properties')]
            for i in [0, 1, 20, 21]:
                row = sf.getTableRow('Properties', i)
                self.assertEqual(row, t2[i])

    def test_readParticles(self):
        t = Timer()

        partSqlite = testpath('metadata', 'scipion', 'particles.sqlite')
        if partSqlite is None:
            return

        with SqliteFile(partSqlite) as sf:
            self.assertEqual(sf.getTableNames(), self.BASIC_TABLES)

            t.tic()
            self.assertEqual(sf.getTableSize('Objects'), 130987)
            t.toc("Size of particles")

            rows = [r for r in sf.iterTable('Classes')]
            self.assertEqual(len(rows), 45)
