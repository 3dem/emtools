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
from contextlib import AbstractContextManager
from collections import OrderedDict
from datetime import datetime, timedelta

from .table import ColumnList, Table


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
    def printTable(table, tableName=''):
        w = StarFile(sys.stdout, closeFile=False)
        w.writeTable(tableName, table, singleRow=len(table) <= 1)

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
        self.__createTable(tableName, **kwargs)
        if self._singleRow:
            self._table.addRow(self.__rowFromValues(self._values))
        else:
            for line in self._iterRowLines():
                self._table.addRow(self.__rowFromValues(self.__split_line(line)))

        return self._table

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

    # ---------------------- Writer functions --------------------------------
    def writeLine(self, line):
        """ Write a line to the opened file. """
        self._file.write(f"{line}\n")

    def _writeTableName(self, tableName):
        self._file.write("\ndata_%s\n\n" % (tableName or ''))

    def writeSingleRow(self, tableName, row):
        """ Write a Row as a single row Table of label/value pairs. """
        self._writeTableName(tableName)
        m = max([len(c) for c in row._fields]) + 5
        format = "_{:<%d} {:>10}\n" % m
        for col, value in row._asdict().items():
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
        for col in self._columns:
            self._file.write("_%s \n" % col.getName())

    def writeRowValues(self, values):
        """ Write to file a line for these row values.
        Order should be ensured that is the same of the expected columns.
        """
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

    def _computeLineFormat(self, valuesList):
        """ Compute format base on row values width. """
        # Take a hint for the columns width from the first row
        widths = [len(_formatValue(v)) for v in valuesList[0]]
        formats = [_getFormatStr(v) for v in valuesList[0]]
        n = len(valuesList)

        if n > 1:
            # Check middle and last row, just in case ;)
            for index in [n // 2, -1]:
                for i, v in enumerate(valuesList[index]):
                    w = len(_formatValue(v))
                    if w > widths[i]:
                        widths[i] = w

        self._format = " ".join("{:>%d%s} " % (w + 1, f)
                                for w, f in zip(widths, formats)) + '\n'

    def writeTable(self, tableName, table, singleRow=False):
        """ Write a Table in Star format to the given file.

        Args:
            tableName: The name of the table to write.
            table: Table that is going to be written
            singleRow: If True, don't write *loop\_*, just label/value pairs.
        """
        if table.size():
            if singleRow:
                self.writeSingleRow(tableName, table[0])
            else:
                self.writeHeader(tableName, table)
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
        self._wait = kwargs.get('wait', 10)
        self._timeout = timedelta(seconds=kwargs.get('timeout', 300))
        self.lastCheck = None  # Last timestamp when input was checked
        self.lastUpdate = None  # Last timestamp when new items were found
        self.inputCount = 0  # Count all input elements

        # Black list some items to not be monitored again
        # We are not interested in the items but just skip them from
        # the processing
        blacklist = kwargs.get('blacklist', None)
        if blacklist:
            for row in blacklist:
                self._seenItems.add(self._rowKeyFunc(row))

    def update(self):
        newRows = []
        now = datetime.now()
        mTime = datetime.fromtimestamp(os.path.getmtime(self.fileName))

        if self.lastCheck is None or mTime > self.lastCheck:
            with StarFile(self.fileName) as sf:
                for row in sf.iterTable(self._tableName):
                    rowKey = self._rowKeyFunc(row)
                    if rowKey not in self._seenItems:
                        self.inputCount += 1
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
            return self.lastCheck - self.lastUpdate > self._timeout

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
