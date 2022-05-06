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
import argparse
from collections import OrderedDict, namedtuple

from .table import ColumnList, Table


class StarReader:
    """ Read tables and rows from star files. """

    def __init__(self, inputFile):
        """ Create a new Reader given a filename or file as input.
        Args:
            inputFile: can be either an string (filename) or file object.
            tableName: name of the data that will be read.
            guessType: if True, the columns type is guessed from the first row.
            types: It can be a dictionary {columnName: columnType} pairs that
                allows to specify types for certain columns.
        """
        if isinstance(inputFile, str):
            self._file = open(inputFile)
        else:
            self._file = inputFile

    def readTable(self, tableName, guessType=True, types=None):
        """ Parse a given table from the input star file.
        Args:
            tableName: star table name
            guessType: if True, the columns type is guessed from the first row.
            types: It can be a dictionary {columnName: columnType} pairs that
                allows to specify types for certain columns.
        """
        colNames, values = self._loadTableInfo(tableName)
        cols = ColumnList.createColumns(colNames, values,
                                        guessType=guessType, types=types)
        self._table = Table(columns=cols)
        self._types = [c.getType() for c in self._table.getColumns()]

        if self._singleRow:
            self._table.addRow(self.__rowFromValues(values))
        else:
            for line in self._iterRowLines():
                self._table.addRow(self.__rowFromValues(line.split()))

        return self._table

    def _loadTableInfo(self, tableName):
        dataStr = 'data_%s' % tableName
        self._findDataLine(dataStr)

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
            values = self._line.split() if self._line else []

        return colNames, values

    def __rowFromValues(self, values):
        try:
            return self._table.Row(*[t(v) for t, v in zip(self._types, values)])
        except Exception as e:
            print("types: ", self._types)
            print("values: ", values)
            raise e

    def getRow(self):
        """ Get the next Row, it is None when not more rows. """
        result = self._row

        if self._singleRow:
            self._row = None
        elif result is not None:
            line = self._file.readline().strip()
            self._row = self.__rowFromValues(line.split()) if line else None

        return result

    def _findDataLine(self, dataStr):
        """ Raise an exception if the desired data string is not found.
        Move the line pointer after the desired line if found.
        """
        line = self._file.readline()
        while line:
            if line.startswith(dataStr):
                return line
            line = self._file.readline()

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

    def readAll(self):
        """ Read all rows and return as a list. """
        return list(iter(self))

    def __iter__(self):
        row = self.getRow()

        while row is not None:
            yield row
            row = self.getRow()


class StarWriter:
    """ Write star tables to file. """
    def __init__(self, inputFile):
        self._file = inputFile
        self._format = None
        self._columns = None

    def _writeTableName(self, tableName):
        self._file.write("\ndata_%s\n\n" % (tableName or ''))

    def _writeSingleRow(self, row):
        m = max([len(c) for c in row._fields]) + 5
        format = "_{:<%d} {:>10}\n" % m
        for col, value in row._asdict().items():
            self._file.write(format.format(col, value))
        self._file.write('\n\n')

    def _writeHeader(self, columns):
        self._file.write("loop_\n")
        self._columns = columns
        # Write column names
        for col in columns:
            self._file.write("_%s \n" % col.getName())

    def _writeRowValues(self, values):
        """ Write to file a line for these row values.
        Order should be ensured that is the same of the expected columns.
        """
        if not self._format:
            self._computeLineFormat([values])
        self._file.write(self._format.format(*values))

    def _writeRow(self, row):
        """ Write to file the line for this row.
        Row should be an instance of the expected Row class.
        """
        self._writeRowValues(row._asdict().values())

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

    def writeTable(self, table, tableName, singleRow=False):
        """ Write a Table in Star format to the given file.
        Args:
            table: Table that is going to be written
            tableName: The name of the table to write.
            singleRow: If True, don't write loop_, just label - value pairs.
        """
        self.writeTableName(tableName)

        if table.size() == 0:
            return

        if singleRow:
            self.writeSingleRow(self._rows[0])
        else:
            self.writeHeader(self._columns.values())
            for row in table:
                self.writeRow(row)

        self.writeNewline()


# --------- Helper functions  ------------------------

def _guessType(strValue):
    try:
        int(strValue)
        return int
    except ValueError:
        try:
            float(strValue)
            return float
        except ValueError:
            return str


def _guessTypesFromLine(line):
    return [_guessType(v) for v in line.split()]


def _formatValue(v):
    return '%0.6f' % v if isinstance(v, float) else str(v)


def _getFormatStr(v):
    return '.6f' if isinstance(v, float) else ''


