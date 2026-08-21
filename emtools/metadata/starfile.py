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
# **************************************************************************

__author__ = 'Jose Miguel de la Rosa Trevin, Grigory Sharov'

import os
import sys
import time
import re
import math
from contextlib import AbstractContextManager
from datetime import datetime, timedelta

import emtools
from emtools.utils import Pretty, Color, Path

from .table import ColumnList, Table
from .misc import Acquisition


class StarFile(AbstractContextManager):
    """
    Class to manipulate STAR files.

    It can be used to read data from STAR file tables or also
    to write into new files. It also contains some helper methods
    to queries table's columns or size without parsing all data rows.

    """

    # Compile regex to split data lines taking into account string literals
    _splitRegex = re.compile('\"[^"]*\"|[^"\s]+')

    @staticmethod
    def printTable(table, tableName='',
                   computeFormat=False,
                   timeStamp=False):
        w = StarFile(sys.stdout, closeFile=False)
        w.writeTable(tableName, table, singleRow=len(table) <= 1, 
                     computeFormat=computeFormat, timeStamp=timeStamp)

    def __init__(self, inputFile, mode='r', **kwargs):
        """
        Args:
            inputFile: can be a str with the file path or a file object.
            mode: mode to open the file, if inputFile is already a file,
                the mode will be ignored.
        """
        self._file = self.__loadFile(inputFile, mode)
        self._closeFile = kwargs.get('closeFile', True)

        # While parsing the file, store the offsets for data_ blocks
        # for quick access when need to load data rows
        self._offsets = {}
        self._names = []  # flag to check if we searched all tables

        # Used for writing
        self._format = None
        self._columns = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def __contains__(self, item):
        """ Return if a table name is in the file. """
        return item in self.getTableNames()

    def getTableNames(self):
        """ Return all the names of the *data\_* blocks found in the file. """
        if not self._names:  # Scan for ALL table names
            f = self._file  # shortcut notation
            f.seek(0)  # move file pointer to the beginning
            offset = 0
            line = f.readline()
            while line:
                # While searching for a data line, we will store the offsets
                # for any data_ line that we find
                if line.startswith('data_'):
                    tn = line.strip().replace('data_', '')
                    self._offsets[tn] = offset
                    self._names.append(tn)
                offset = f.tell()
                line = f.readline()

        return list(self._names)

    def __createTable(self, tableName, **kwargs):
        guessType = kwargs.get('guessType', True)
        types = kwargs.get('types', {})
        self._loadTableInfo(tableName)
        cols = ColumnList.createColumns(self._colNames, self._values,
                                        guessType=guessType, types=types)
        self._table = Table(columns=cols)
        self._types = [c.getType() for c in self._table.getColumns()]

    def getTable(self, tableName, **kwargs):
        """
        Read the given table from the file and parse columns' definition
        and data rows.

        Args:
            tableName: the name of the table to read, it can be the empty string
            kwargs:
                guessType=True, by default types will be guessed for data rows.
                    If False, all values will be returned as strings
                types=None, optional types dict with {columnName: columnType}
                    pairs that allows to specify types for certain columns.
        """
        try:
            self.__createTable(tableName, **kwargs)
        except:
            return None

        if self._singleRow:
            self._table.addRow(self.__rowFromValues(self._values))
        else:
            for line in self._iterRowLines():
                self._table.addRow(self.__rowFromValues(self.__split_line(line)))

        return self._table

    @staticmethod
    def getTableFromFile(tableName, starFileName, **kwargs):
        """ Shortcut to read a table from file.
        **kwargs are the same expected by getTable function.
        """
        with StarFile(starFileName) as sf:
            return sf.getTable(tableName, **kwargs)

    @staticmethod
    def getTablesDict(starFileName, **kwargs):
        """ Shortcut to read all tables from file as a dictionary.
        **kwargs are the same expected by getTable function.
        """
        with StarFile(starFileName) as sf:
            return {table: sf.getTable(table, **kwargs) for table in sf.getTableNames()}

    def getTableSize(self, tableName):
        """
        Return the number of elements in the given table without parsing
        all the rows of the table.

        If one is only interested in the number of items in a row,
        this method is much more efficient that parsing all rows in
        the table.
        """
        self._loadTableInfo(tableName)
        if self._singleRow:
            return 1
        else:
            return sum(1 for line in self._iterRowLines())

    def getTableInfo(self, tableName, **kwargs):
        """ Similar to getTable(), but it will not parse the data rows.
        Only the columns will be read into the Table instance.
        """
        self.__createTable(tableName, **kwargs)
        return self._table

    def iterTable(self, tableName, **kwargs):
        """ Only iterate over the table's rows and do not create
        a Table in memory to store all rows.

        Args:
            tableName: name of the table to iterate
            kwargs:
                start, starting index, first one is 0
                limit, limit to this number of elements
        """
        start = kwargs.get('start', 0)
        limit = kwargs.get('limit', None)

        self.__createTable(tableName, **kwargs)
        if self._singleRow:
            yield self.__rowFromValues(self._values)
        else:
            c = 0
            for i, line in enumerate(self._iterRowLines()):
                if i >= start:
                    c += 1
                    yield self.__rowFromValues(self.__split_line(line))
                if limit and c == limit:
                    break

    def getTableRow(self, tableName, rowIndex, **kwargs):
        """ Get a given row by index. Extra args are passed to iterTable. """
        kwargs['start'] = rowIndex
        kwargs['limit'] = 1
        for row in self.iterTable(tableName, **kwargs):
            return row

    def __loadFile(self, inputFile, mode):
        return open(inputFile, mode) if isinstance(inputFile, str) else inputFile

    def __split_line(self, line, default=[]):
        """ Split a data line taking into account string literals """
        if '"' in line:
            return self._splitRegex.findall(line) if line else default

        return line.split() if line else default

    def _loadTableInfo(self, tableName):
        self._findDataLine(tableName)

        # Find first column line and parse all columns
        self._findLabelLine()
        colNames = []
        values = []

        while self._line.startswith('_'):
            parts = self._line.split()
            colNames.append(parts[0][1:])
            if not self._foundLoop:
                values.append(parts[1])
            self._line = self._file.readline().strip()

        self._singleRow = not self._foundLoop

        if self._foundLoop:
            values = self.__split_line(self._line)

        self._colNames = colNames
        self._values = values

    def __rowFromValues(self, values):
        if not values:
            return None
        try:
            return self._table.Row(*[t(v) for t, v in zip(self._types, values)])
        except Exception as e:
            print("types: ", self._types)
            print("values: ", values)
            raise e

    def __rowFromLine(self, line):
        return self.__rowFromValues(self.__split_line(line))

    def _getRow(self):
        """ Get the next Row, it is None when not more rows. """
        result = self._row

        if self._singleRow:
            self._row = None
        elif result is not None:
            line = self._file.readline().strip()
            self._row = self.__rowFromValues(self.__split_line(line))

        return result

    def _findDataLine(self, dataName):
        """ Raise an exception if the desired data string is not found.
        Move the line pointer after the desired line if found.
        """
        f = self._file  # shortcut notation

        # Check if we know the offset for this data line
        dataStr = 'data_' + dataName
        if dataStr in self._offsets:
            f.seek(self._offsets[dataStr])
            f.readline()
            return

        full_scan = False
        initial_offset = offset = f.tell()
        line = f.readline()
        # Iterate all lines once if necessary, going back to
        # the beginning of the file once
        while not full_scan:
            while line:
                # While searching for a data line, we will store the offsets
                # for any data_ line that we find
                if line.startswith('data_'):
                    ds = line.strip()
                    self._offsets[ds] = offset
                    if ds == dataStr:
                        return
                offset = f.tell()
                if offset == initial_offset:
                    full_scan = True
                    break
                line = f.readline()
            # Start from the beginning and scann until complete the full loop
            if initial_offset == 0:
                break
            f.seek(0)
            offset = 0
            line = f.readline()

        raise Exception("'%s' block was not found" % dataStr)

    def _findLabelLine(self):
        line = ''
        foundLoop = False

        rawLine = self._file.readline()
        while rawLine:
            if rawLine.startswith('_'):
                line = rawLine
                break
            elif rawLine.startswith('loop_'):
                foundLoop = True
            rawLine = self._file.readline()

        self._line = line.strip()
        self._foundLoop = foundLoop

    def _iterRowLines(self):
        self._lineCount = 0
        # First line is already in self._line
        while self._line:
            self._lineCount += 1
            yield self._line
            self._line = self._file.readline().strip()

    def close(self):
        if getattr(self, '_file', None):
            if self._closeFile:
                self._file.close()
            self._file = None

    def flush(self):
        if getattr(self, '_file', None):
            self._file.flush()

    # ---------------------- Writer functions --------------------------------
    def writeLine(self, line):
        """ Write a line to the opened file. """
        self._file.write(f"{line}\n")

    def writeTimeStamp(self):
        """ Write a comment line with current datetime and library version. """
        self.writeLine(f"\n# StarFile written on {Pretty.now()} "
                       f"by emtools ({emtools.__version__})\n")

    def writeVersion(self, version):
        """ Write a RELION metadata-table version tag (e.g. 50001). """
        self.writeLine(f"# version {version}")

    def _writeTableName(self, tableName):
        self._file.write("\ndata_%s\n\n" % (tableName or ''))

    def writeSingleRow(self, tableName, row):
        """ Write a Row as a single row Table of label/value pairs. """
        self._writeTableName(tableName)
        d = row if isinstance(row, dict) else row._asdict()
        m = max(len(c) for c in d) + 5
        format = "_{:<%d} {:>10}\n" % m
        d = row if isinstance(row, dict) else row._asdict()
        for col, value in d.items():
            self._file.write(format.format(col, _escapeStrValue(value)))
        self._file.write('\n\n')

    def writeHeader(self, tableName, table):
        """ Write table and column names. Needed before any
        row can be written. """
        self._format = None  # clear format for writing new table
        self._writeTableName(tableName)
        self._file.write("loop_\n")
        self._columns = table.getColumns()
        # Write column names
        for i, col in enumerate(self._columns, start=1):
            self._file.write(f"_{col.getName()}  #{i}\n")

    def writeRowValues(self, values):
        """ Write to file a line for these row values.
        Order should be ensured that is the same of the expected columns.
        """
        if isinstance(values, dict):
            values = values.values()

        if not self._format:
            self._computeLineFormat([values])

        values = [_escapeStrValue(v) for v in values]
        self._file.write(self._format.format(*values))

    def writeRow(self, row):
        """ Write to file the line for this row.
        Row should be an instance of the expected Row class.
        """
        self.writeRowValues(row._asdict().values())

    def _writeNewline(self):
        self._file.write('\n')

    def _computeLineFormat(self, valuesList, computeFormat=False):
        """ Compute format base on row values width. """
        # Take a hint for the columns width from the first row
        widths = [len(_formatValue(v)) for v in valuesList[0]]
        formats = [_getFormatStr(v) for v in valuesList[0]]
        n = len(valuesList)
        a = '>'

        if n > 1:
            # Check middle and last row, just in case ;)
            indexes = list(range(len(valuesList))) if computeFormat else [n // 2, -1]
            if computeFormat == 'left':
                a = '<'
            for index in indexes:
                for i, v in enumerate(valuesList[index]):
                    w = len(_formatValue(v))
                    if w > widths[i]:
                        widths[i] = w

        self._format = " ".join("{:%s%d%s} " % (a, w + 1, f)
                                for w, f in zip(widths, formats)) + '\n'

    def writeTable(self, tableName, table,
                   singleRow=False,
                   computeFormat=False,
                   timeStamp=False,
                   version=None):
        """ Write a Table in Star format to the given file.

        Args:
            tableName: The name of the table to write.
            table: Table that is going to be written
            singleRow: If True, don't write *loop\_*, just label/value pairs.
            computeFormat: compute format based on widest first column,
                just for aesthetics and not recommended for large tables.
                Values can be 'left' or 'rigth' for alignment.
            version: If set, write a RELION ``# version`` tag before the table.
        """
        if timeStamp:
            self.writeTimeStamp()
        if version is not None:
            self.writeVersion(version)

        if table.size():
            if singleRow:
                self.writeSingleRow(tableName, table[0])
            else:
                self.writeHeader(tableName, table)
                if computeFormat:
                    valuesList = [row._asdict().values() for row in table]
                    self._computeLineFormat(valuesList, computeFormat=computeFormat)
                for row in table:
                    self.writeRow(row)

            self._writeNewline()
        else:
            # Only write the table name
            self._writeTableName(tableName)


class StarMonitor:
    """
    Monitor a STAR file for changes and return new items in a given table.

    This class will subclass OrderedDict to hold a clone of each new element.
    It will also keep internally the last access timestamp to prevent loading
    the STAR file if it has not been modified since the last check.
    """
    def __init__(self, fileName, tableName, rowKeyFunc, **kwargs):
        self._seenItems = set()
        self.fileName = fileName
        self._tableName = tableName
        self._rowKeyFunc = rowKeyFunc
        self._wait = kwargs.get('wait', 30)
        self._timeout = timedelta(seconds=kwargs.get('timeout', 300))
        self.lastCheck = None  # Last timestamp when input was checked
        self.lastUpdate = None  # Last timestamp when new items were found

        # Black list some items to not be monitored again
        # We are not interested in the items but just skip them from
        # the processing
        blacklist = kwargs.get('blacklist', None)
        if blacklist:
            for row in blacklist:
                self._seenItems.add(self._rowKeyFunc(row))

    def update(self):
        newRows = []

        if os.path.exists(self.fileName):
            now = datetime.now()
            mTime = datetime.fromtimestamp(os.path.getmtime(self.fileName))

            if self.lastCheck is None or mTime > self.lastCheck:
                with StarFile(self.fileName) as sf:
                    for row in sf.iterTable(self._tableName):
                        rowKey = self._rowKeyFunc(row)
                        if rowKey not in self._seenItems:
                            self._seenItems.add(rowKey)
                            newRows.append(row)

            self.lastCheck = now
            if newRows:
                self.lastUpdate = now

        return newRows

    def timedOut(self):
        """ Return True when there has been timeout seconds
        since last new items were found. """
        if self.lastCheck is None or self.lastUpdate is None:
            return False
        else:
            return (self.lastCheck - self.lastUpdate) > self._timeout

    def newItems(self, sleep=10):
        """ Yield new items since last update until the stream is closed. """
        while not self.timedOut():
            for row in self.update():
                yield row
            time.sleep(self._wait)


# --------- Helper functions  ------------------------
def _formatValue(v):
    return '%0.6f' % v if isinstance(v, float) else str(v)


def _getFormatStr(v):
    return '.6f' if isinstance(v, float) else ''


def _escapeStrValue(v):
    """ Escape string values by adding quotes if the string
    is empty or contains spaces. """
    return '"%s"' % v if isinstance(v, str) and (not v or ' ' in v) else v


class RelionStar:

    # RELION 5 pipeline STAR tables; prevents re-running pre-5.0 label migration.
    PIPELINE_VERSION = 50001

    JOB_INDEX = re.compile('job(\d{3})')
    TRUE_VALUES = ['Yes', 'True', 'true']
    FALSE_VALUES = ['No', 'False', 'false']

    TOMO_FRAME_SERIES_COLUMNS = [
        'rlnMicrographMovieName',
        'rlnTomoTiltMovieFrameCount',
        'rlnTomoNominalStageTiltAngle',
        'rlnTomoNominalTiltAxisAngle',
        'rlnMicrographPreExposure',
        'rlnTomoNominalDefocus'
    ]

    TOMO_ALIGNMENT_COLUMNS = [
        "rlnTomoXTilt",
        "rlnTomoYTilt",
        "rlnTomoZRot",
        "rlnTomoXShiftAngst",
        "rlnTomoYShiftAngst"
    ]

    TOMO_OPTIMISATION_SET_TABLE = 'optimisation_set'
    TOMO_OPTIMISATION_SET_COLUMNS = [
        'rlnTomoParticlesFile',
        'rlnTomoTomogramsFile'
    ]

    TOMO_PARTICLES_TABLE = 'particles'
    TOMO_PARTICLES_COLUMNS = [
        'rlnTomoName',
    ]
    TOMO_PARTICLES_PIXEL_COORD_COLUMNS = [
        'rlnCoordinateX',
        'rlnCoordinateY',
        'rlnCoordinateZ',
    ]
    TOMO_PARTICLES_CENTERED_COORD_COLUMNS = [
        'rlnCenteredCoordinateXAngst',
        'rlnCenteredCoordinateYAngst',
        'rlnCenteredCoordinateZAngst',
    ]

    @staticmethod
    def hasTomoParticleCoordinates(table):
        """Return True if the table has tomography particle coordinates."""
        return (
            table.hasAllColumns(RelionStar.TOMO_PARTICLES_PIXEL_COORD_COLUMNS)
            or table.hasAllColumns(RelionStar.TOMO_PARTICLES_CENTERED_COORD_COLUMNS)
        )

    @staticmethod
    def isTomoOptimisationSet(starFile):
        """Return True if the STAR file has a compliant optimisation_set table."""
        try:
            RelionStar.readTomoOptimisationSet(starFile)
            return True
        except (OSError, IOError, Exception):
            return False

    @staticmethod
    def isTomoParticles(starFile):
        """Return True if the STAR file has a compliant tomography particles table."""
        if not starFile or not os.path.isfile(starFile):
            return False
        try:
            with StarFile(starFile) as sf:
                if RelionStar.TOMO_PARTICLES_TABLE not in sf.getTableNames():
                    return False
                if sf.getTableSize(RelionStar.TOMO_PARTICLES_TABLE) < 1:
                    return False
                table = sf.getTableInfo(RelionStar.TOMO_PARTICLES_TABLE)
                return (
                    table is not None
                    and table.hasAllColumns(RelionStar.TOMO_PARTICLES_COLUMNS)
                    and RelionStar.hasTomoParticleCoordinates(table)
                )
        except (OSError, IOError, Exception):
            return False

    @staticmethod
    def readTomoOptimisationSet(starFile):
        """Read the optimisation_set table or raise ValueError."""
        if not starFile or not os.path.isfile(starFile):
            raise ValueError(f"Invalid STAR file: {starFile}")
        all_tables = StarFile.getTablesDict(starFile)
        first_table = next(iter(all_tables.values()))

        if not first_table.hasAllColumns(RelionStar.TOMO_OPTIMISATION_SET_COLUMNS):
            raise ValueError(
                f"{starFile} is not a compliant tomography optimisation_set STAR file."
            )
        return first_table

    @staticmethod
    def readTomoParticles(starFile):
        """Read the particles table or raise ValueError."""
        if not RelionStar.isTomoParticles(starFile):
            raise ValueError(
                f"{starFile} is not a compliant tomography particles STAR file."
            )
        table = StarFile.getTableFromFile(RelionStar.TOMO_PARTICLES_TABLE, starFile)
        if not table:
            raise ValueError(
                f"Could not read '{RelionStar.TOMO_PARTICLES_TABLE}' "
                f"table from {starFile}."
            )
        return table

    @staticmethod
    def to_bool(strValue):
        """ Convert Relion Yes/No to True/False. """
        if strValue == 'Yes':
            return True
        elif strValue == 'False':
            return False
        else:
            raise Exception(f"Invalid Relion bool value: {strValue}")

    @staticmethod
    def from_bool(boolValue):
        """ Return Yes or No string from True/False. """
        if not isinstance(boolValue):
            raise Exception("Expecting bool value for Yes/No conversion")

        return 'Yes' if boolValue else 'No'

    @staticmethod
    def true_value(v):
        return v in RelionStar.TRUE_VALUES

    @staticmethod
    def false_value(v):
        return v in RelionStar.FALSE_VALUES

    @staticmethod
    def getTomoBinning(row):
        return float(getattr(row, 'rlnTomoTomogramBinning', 1))

    @staticmethod
    def getTomoPixelSize(row):
        """Compute the tomogram pixel size from TS pixel size and binning."""
        return (float(getattr(row, 'rlnTomoTiltSeriesPixelSize', 0))
                * RelionStar.getTomoBinning(row))

    @staticmethod
    def reconstructedTomoSize(row, axis):
        """Return reconstructed tomogram size in pixels along X/Y/Z."""
        return float(getattr(row, axis)) / RelionStar.getTomoBinning(row)

    @staticmethod
    def centeredAngstToPixel(centered_angst, row, axis):
        """Convert Relion centered Angstrom coordinates to tomogram pixels."""
        return (float(centered_angst) / RelionStar.getTomoPixelSize(row)
                + RelionStar.reconstructedTomoSize(row, axis) / 2)

    @staticmethod
    def getTomogram(row):
        """Return tomogram path, trying from different columns."""
        cols = ['rlnTomoReconstructedTomogram', 'rlnTomoReconstructedTomogramDenoised']
        for col in cols:
            if value := row.get(col):
                return value
        raise ValueError(f"No tomogram column ({', '.join(cols)}) found in row: {row}")

    @staticmethod
    def read_jobstar(jobStarFile):
        tValues = StarFile.getTableFromFile('joboptions_values',
                                            jobStarFile,
                                            guessType=False)
        def _val(v):
            if RelionStar.true_value(v):
                return True
            elif RelionStar.false_value(v):
                return False
            else:
                return v

        return {row.rlnJobOptionVariable: _val(row.rlnJobOptionValue) for row in tValues}

    @staticmethod
    def write_jobstar(jobType, values, jobStarFile, isTomo=0, isContinue=0):
        """ Convert params dict to a Relion job.star file. """
        with StarFile(jobStarFile, 'w') as sfOut:
            tJob = Table(['rlnJobTypeLabel', 'rlnJobIsContinue', 'rlnJobIsTomo'])
            tJob.addRowValues(jobType, isContinue, isTomo)  
            sfOut.writeTimeStamp()
            sfOut.writeTable('job', tJob, singleRow=True)
            tValues = Table(['rlnJobOptionVariable', 'rlnJobOptionValue'])
            for k, v in values.items():
                if isinstance(v, bool):
                    val = 'Yes' if v else 'No'
                elif v is None:
                    val = ''
                else:
                    # Job option values are always strings in STAR files.
                    val = str(v)
                tValues.addRowValues(k, val)
            sfOut.writeTable('joboptions_values', tValues, computeFormat='left')

    @staticmethod
    def optics_table(acq, opticsGroup=1, opticsGroupName="opticsGroup1",
                     mtf=None, originalPixelSize=None):
        origPs = originalPixelSize or acq['pixel_size']

        values = {
            'rlnOpticsGroupName': opticsGroupName,
            'rlnOpticsGroup': opticsGroup,
            'rlnMicrographOriginalPixelSize': origPs,
            'rlnVoltage': acq['voltage'],
            'rlnSphericalAberration': acq['cs'],
            'rlnAmplitudeContrast': acq.get('amplitude_contrast', 0.1),
            'rlnMicrographPixelSize': acq['pixel_size']
        }
        if mtf:
            values['rlnMtfFileName'] = mtf
        return Table.fromDict(values)

    @staticmethod
    def movies_table(**kwargs):
        extra_cols = kwargs.get('extra_cols', [])
        return Table([
            'rlnMicrographMovieName',
            'rlnOpticsGroup'
        ] + extra_cols)

    @staticmethod
    def micrograph_table(**kwargs):
        cols = []
        if image_id := kwargs.get('image_id', None):
            cols.append(image_id)
        cols.extend([
            'rlnMicrographName',
            'rlnOpticsGroup',
            'rlnCtfImage',
            'rlnDefocusU',
            'rlnDefocusV',
            'rlnCtfAstigmatism',
            'rlnDefocusAngle',
            'rlnCtfFigureOfMerit',
            'rlnCtfMaxResolution'
        ])
        if extra_cols := kwargs.get('extra_cols', []):
            cols.extend(extra_cols)
        return Table(cols)

    @staticmethod
    def coordinates_table(**kwargs):
        return Table(['rlnMicrographName', 'rlnMicrographCoordinates'])

    @staticmethod
    def tiltseries_table(mc=True, ctf=True, **kwargs):
        cols = list(RelionStar.TOMO_FRAME_SERIES_COLUMNS)
        cols.extend([
            'rlnMicrographName',
            'rlnMicrographNameEven',
            'rlnMicrographNameOdd'            
        ])

        if mc:
            cols.extend([
                'rlnMicrographMetadata',
                'rlnAccumMotionTotal',
                'rlnAccumMotionEarly',
                'rlnAccumMotionLate'
            ])

        if ctf:
            cols.extend([
                'rlnCtfImage',
                'rlnDefocusU',
                'rlnDefocusV',
                'rlnCtfAstigmatism',
                'rlnDefocusAngle',
                'rlnCtfFigureOfMerit',
                'rlnCtfMaxResolution',
                'rlnCtfIceRingDensity'
            ])

        cols.extend(kwargs.get('extra_cols', []))

        return Table(cols)

    @staticmethod
    def global_tiltseries_table(**kwargs):
        cols = [
            'rlnTomoName',
            'rlnTomoTiltSeriesStarFile',
            'rlnVoltage',
            'rlnSphericalAberration',
            'rlnAmplitudeContrast',
            'rlnMicrographOriginalPixelSize',
            'rlnTomoHand',
            'rlnOpticsGroupName',
            'rlnTomoTiltSeriesPixelSize'
        ]
        cols.extend(kwargs.get('extra_cols', []))

        return Table(cols)

    @staticmethod
    def _acquisition_from_row(row):
        """ Build Acquisition from an optics or tomography global row. """
        if getattr(row, 'rlnTomoTiltSeriesPixelSize', None):
            pixel_size = RelionStar.getTomoPixelSize(row)
        else:
            pixel_size = (getattr(row, 'rlnMicrographPixelSize', None)
                          or row.rlnMicrographOriginalPixelSize)

        acq = Acquisition(
            pixel_size=pixel_size,
            voltage=row.rlnVoltage,
            cs=row.rlnSphericalAberration,
            amplitude_contrast=getattr(row, 'rlnAmplitudeContrast', 0.1)
        )
        if gain := getattr(row, 'rlnMicrographGainName', None):
            acq['gain'] = gain
        if dose := getattr(row, 'rlnMicrographDoseRate', None):
            acq['total_dose'] = float(dose)

        return acq

    @staticmethod
    def _resolve_linked_star(baseStarFile, linkedPath):
        if not linkedPath:
            return None
        if os.path.isabs(linkedPath):
            return linkedPath

        candidates = [
            os.path.normpath(os.path.join(os.path.dirname(baseStarFile),
                                          linkedPath)),
            os.path.normpath(os.path.join(os.getcwd(), linkedPath)),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return candidates[0]

    @staticmethod
    def getAcquisition(inputTableOrFile):
        """ Load acquisition parameters from an optics/global table row,
        or a given input STAR file (movies, tilt series, tomograms, etc.).
        """
        if hasattr(inputTableOrFile, 'rlnVoltage'):
            return RelionStar._acquisition_from_row(inputTableOrFile)

        if isinstance(inputTableOrFile, Table):
            return RelionStar._acquisition_from_row(inputTableOrFile[0])

        starFile = inputTableOrFile
        if RelionStar.isTomoOptimisationSet(starFile):
            row = RelionStar.readTomoOptimisationSet(starFile)[0]
            if tomogramsStar := getattr(row, 'rlnTomoTomogramsFile', None):
                return RelionStar.getAcquisition(
                    RelionStar._resolve_linked_star(starFile, tomogramsStar))
            if particlesStar := getattr(row, 'rlnTomoParticlesFile', None):
                return RelionStar.getAcquisition(
                    RelionStar._resolve_linked_star(starFile, particlesStar))

        with StarFile(starFile) as sf:
            if t := sf.getTable('optics'):
                return RelionStar._acquisition_from_row(t[0])
            if t := sf.getTable('global'):
                return RelionStar._acquisition_from_row(t[0])

        raise Exception(f"Could not read acquisition parameters from {starFile}")

    @staticmethod
    def alignment_from_xf(xf_row, pixel_size):
        """Convert one IMOD XF row into Relion alignment labels.
        IMOD XF row:
            A11 A12 A21 A22 DX DY
        The translation should be taken from the inverse transform, then
        converted from pixels to Angstroms.
        """
        a11, a12, a21, a22, dx, dy = xf_row

        det = a11 * a22 - a12 * a21
        if abs(det) < 1e-12:
            return {
                'rlnTomoZRot': '',
                'rlnTomoXShiftAngst': '',
                'rlnTomoYShiftAngst': '',
            }

        z_rot = math.degrees(math.atan2(a12, a11))

        # Inverse affine translation:
        # inv(M) * -t
        inv_dx = -((a22 * dx - a12 * dy) / det)
        inv_dy = -((-a21 * dx + a11 * dy) / det)

        return {
            'rlnTomoZRot': z_rot,
            'rlnTomoXShiftAngst': inv_dx * pixel_size,
            'rlnTomoYShiftAngst': inv_dy * pixel_size,
        }

    @staticmethod
    def alignments_from_imod(tlt_angles, xf_alignments, pixel_size):
        """ Read tilt angles (.tlt file) and IMOD transforms (.xf file) to compute Relion alignments.
        Returns:
            list[dict]: list of Relion alignments
        """
        rln_alignments = []

        for tilt, xf_row in zip(tlt_angles, xf_alignments):
            xf_values = RelionStar.alignment_from_xf(xf_row, pixel_size)
            ctf_scale = math.cos(math.radians(tilt))

            rln_alignments.append({
                'tilt': tilt,
                'rlnTomoXTilt': 0.0 if tilt != '' else '',
                'rlnTomoYTilt': tilt,
                'rlnTomoZRot': xf_values.get('rlnTomoZRot', ''),
                'rlnTomoXShiftAngst': xf_values.get('rlnTomoXShiftAngst', ''),
                'rlnTomoYShiftAngst': xf_values.get('rlnTomoYShiftAngst', ''),
                'rlnCtfScalefactor': ctf_scale,
            })

        return rln_alignments

    @staticmethod
    def pipeline_tables():
        return {
            'processes': Table(['rlnPipeLineProcessName',
                                'rlnPipeLineProcessAlias',
                                'rlnPipeLineProcessTypeLabel',
                                'rlnPipeLineProcessStatusLabel']),
            'nodes': Table(['rlnPipeLineNodeName',
                            'rlnPipeLineNodeTypeLabel',
                            'rlnPipeLineNodeTypeLabelDepth']),
            'output_edges': Table(['rlnPipeLineEdgeProcess',
                                   'rlnPipeLineEdgeToNode']),
            'input_edges': Table(['rlnPipeLineEdgeFromNode',
                                  'rlnPipeLineEdgeProcess'])
        }

    @staticmethod
    def write_pipeline(pipeline_star, jobCounter=1, tables=None):
        version = RelionStar.PIPELINE_VERSION
        with StarFile(pipeline_star, 'w') as sf:
            sf.writeTimeStamp()
            tGeneral = Table(['rlnPipeLineJobCounter'])
            tGeneral.addRowValues(jobCounter)
            sf.writeTable('pipeline_general', tGeneral,
                          singleRow=True, version=version)

            if tables:
                for name, t in tables.items():
                    if len(t):
                        sf.writeTable(f"pipeline_{name}", t,
                                      computeFormat=True, version=version)

    @staticmethod
    def job_index(jobId):
        """ Return the integer job index from the name of the form Folder/jobXXX. """
        m = RelionStar.JOB_INDEX.search(jobId)
        if m is None:
            return None
        else:
            return int(m.groups()[0])

    @staticmethod
    def pipeline_to_workflow(pipelineStar):
        """ Read the Relion pipeline star file and build the proper Workflow. """
        from emtools.jobs import Workflow   # import here to avoid circular imports

        wf = Workflow()
        with StarFile(pipelineStar) as sf:
            tables = sf.getTableNames()

            def _table(name):
                fullname = f"pipeline_{name}"
                return sf.getTable(fullname) if fullname in tables else None

            if tGeneral := _table('general'):
                wf.jobNextIndex = int(tGeneral[0].rlnPipeLineJobCounter)
            else:
                wf.jobNextIndex = 1

            if tProc := _table('processes'):
                for row in tProc:
                    jobId = Path.rmslash(row.rlnPipeLineProcessName)
                    wf.registerJob(jobId,
                                   alias=row.rlnPipeLineProcessAlias,
                                   status=row.rlnPipeLineProcessStatusLabel,
                                   jobtype=row.rlnPipeLineProcessTypeLabel,
                                   jobindex=RelionStar.job_index(jobId))

            if tNodes := _table('nodes'):
                nodes = {row.rlnPipeLineNodeName: row.rlnPipeLineNodeTypeLabel
                         for row in tNodes}
            else:
                nodes = {}

            if tOutput := _table('output_edges'):
                for row in tOutput:
                    job = wf.getJob(Path.rmslash(row.rlnPipeLineEdgeProcess))
                    nodeName = row.rlnPipeLineEdgeToNode
                    job.registerOutput(nodeName, datatype=nodes[nodeName])

            if tInput := _table('input_edges'):
                for row in tInput:
                    job = wf.getJob(Path.rmslash(row.rlnPipeLineEdgeProcess))
                    if wf.hasData(row.rlnPipeLineEdgeFromNode):
                        job.addInputs([wf.getData(row.rlnPipeLineEdgeFromNode)])
                    else:
                        print(f"WARNING: Missing input edge: {row.rlnPipeLineEdgeFromNode}")

        return wf

    @staticmethod
    def workflow_to_pipeline(wf, pipelineStar):
        """ Write the input workflow as the expected Relion pipeline STAR file. """
        tables = RelionStar.pipeline_tables()
        tProc = tables['processes']
        tNodes = tables['nodes']
        tOutput = tables['output_edges']
        tInput = tables['input_edges']

        # There are some job'status that are not supported by Relion, so we need to map them to the expected values
        status_map = {
            'Launched': 'Scheduled',
            'Saved': 'Scheduled'
        }

        for job in wf.jobs():
            status = status_map.get(job['status'], job['status'])
            tProc.addRowValues(
                rlnPipeLineProcessName=Path.addslash(job.id),
                rlnPipeLineProcessAlias=job['alias'],
                rlnPipeLineProcessStatusLabel=status,
                rlnPipeLineProcessTypeLabel=job['jobtype']
            )
            for i in job.inputs:
                tInput.addRowValues(
                    rlnPipeLineEdgeProcess=Path.addslash(job.id),
                    rlnPipeLineEdgeFromNode=i.id
                )

            for o in job.outputs:
                tNodes.addRowValues(
                    rlnPipeLineNodeName=o.id,
                    rlnPipeLineNodeTypeLabel=o['datatype'],
                    rlnPipeLineNodeTypeLabelDepth=1
                )
                tOutput.addRowValues(
                    rlnPipeLineEdgeProcess=Path.addslash(job.id),
                    rlnPipeLineEdgeToNode=o.id
                )

        RelionStar.write_pipeline(pipelineStar, wf.jobNextIndex, tables)
