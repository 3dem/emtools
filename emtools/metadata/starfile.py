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


class _Column:
    def __init__(self, name, type=None):
        self._name = name
        self._type = type or str

    def __str__(self):
        return 'Column: %s (type: %s)' % (self._name, self._type)

    def __cmp__(self, other):
        return (self.getName() == other.getName()
                and self.getType() == other.getType())

    def __eq__(self, other):
        return self.__cmp__(other)

    def getName(self):
        return self._name

    def getType(self):
        return self._type

    def setType(self, colType):
        self._type = colType


class _ColumnsList:
    def __init__(self):
        self._columns = OrderedDict()

    def printColumns(self):
        print("Columns: ")
        for c in self.getColumns():
            print("   %s" % str(c))

    def hasColumn(self, colName):
        """ Return True if a given column exists. """
        return colName in self._columns

    def hasAnyColumn(self, colsNames):
        return any(self.hasColumn(c) for c in colsNames)

    def hasAllColumns(self, colNames):
        return all(self.hasColumn(c) for c in colNames)

    def getColumn(self, colName):
        """ Return the column with that name or
        None if the column does not exist.
        """
        return self._columns.get(colName, None)

    def getColumns(self):
        return self._columns.values()

    def getColumnNames(self):
        return [c.getName() for c in self.getColumns()]

    # ---------------------- Internal Methods ----------------------------------
    def _createColumns(self, columnList, values=None, guessType=False, types=None):
        """ Create the columns.
        Args:
            columnList: it can be either a list of Column objects or just
                strings representing the column names
            values: values of a given line to guess type from
            guessType: If True the type of a given column (if not passed in
                types) will be guessed from the line of values
            types: It can be a dictionary {columnName: columnType} pairs that
                allows to specify types for certain columns.
        """
        self._columns.clear()

        if isinstance(columnList[0], _Column):
            for col in columnList:
                self._columns[col.getName()] = col
        else:
            values = values or []
            types = types or {}
            for i, colName in enumerate(columnList):
                if colName in types:
                    colType = types[colName]
                elif guessType and values:
                    colType = _guessType(values[i])
                else:
                    colType = str
                self._columns[colName] = _Column(colName, colType)

        self._createRowClass()

    def _createRowClass(self):

        class Row(namedtuple('_Row', self._columns.keys())):
            __slots__ = ()

            def hasColumn(self, colName):
                """ Return True if the row has this column. """
                return hasattr(self, colName)

            def hasAnyColumn(self, colNames):
                return any(self.hasColumn(c) for c in colNames)

            def hasAllColumns(self, colNames):
                return all(self.hasColumn(c) for c in colNames)

            def set(self, key, value):
                return setattr(self, key, value)

            def get(self, key, default=None):
                return getattr(self, key, default)

        self.Row = Row


class _Reader(_ColumnsList):
    """ Internal class to handling reading table data. """

    def __init__(self, inputFile, tableName='', guessType=True, types=None):
        """ Create a new Reader given a filename or file as input.
        Args:
            inputFile: can be either an string (filename) or file object.
            tableName: name of the data that will be read.
            guessType: if True, the columns type is guessed from the first row.
            types: It can be a dictionary {columnName: columnType} pairs that
                allows to specify types for certain columns.
        """
        _ColumnsList.__init__(self)

        if isinstance(inputFile, str):
            self._file = open(inputFile)
        else:
            self._file = inputFile

        dataStr = 'data_%s' % (tableName or '')
        self._findDataLine(self._file, dataStr)

        # Find first column line and parse all columns
        line, foundLoop = self._findLabelLine(self._file)
        colNames = []
        values = []

        while line.startswith('_'):
            parts = line.split()
            colNames.append(parts[0][1:])
            if not foundLoop:
                values.append(parts[1])
            line = self._file.readline().strip()

        self._singleRow = not foundLoop

        if foundLoop:
            values = line.split() if line else []

        self._createColumns(colNames,
                            values=values, guessType=guessType, types=types)
        self._types = [c.getType() for c in self.getColumns()]


        if self._singleRow:
            self._row = self.__rowFromValues(values)
        else:
            self._row = self.__rowFromValues(values) if values else None

    def __rowFromValues(self, values):

        try:
            return self.Row(*[t(v) for t, v in zip(self._types, values)])
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

    def _findDataLine(self, inputFile, dataStr):
        """ Raise an exception if the desired data string is not found.
        Move the line pointer after the desired line if found.
        """
        line = inputFile.readline()
        while line:
            if line.startswith(dataStr):
                return line
            line = inputFile.readline()

        raise Exception("'%s' block was not found" % dataStr)

    def _findLabelLine(self, inputFile):
        line = ''
        foundLoop = False

        rawLine = inputFile.readline()
        while rawLine:
            if rawLine.startswith('_'):
                line = rawLine
                break
            elif rawLine.startswith('loop_'):
                foundLoop = True
            rawLine = inputFile.readline()

        return line.strip(), foundLoop

    def readAll(self):
        """ Read all rows and return as a list. """
        return list(iter(self))

    def __iter__(self):
        row = self.getRow()

        while row is not None:
            yield row
            row = self.getRow()


class _Writer:
    """ Write star tables to file. """
    def __init__(self, inputFile):
        self._file = inputFile
        self._format = None
        self._columns = None

    def writeTableName(self, tableName):
        self._file.write("\ndata_%s\n\n" % (tableName or ''))

    def writeSingleRow(self, row):
        m = max([len(c) for c in row._fields]) + 5
        format = "_{:<%d} {:>10}\n" % m
        for col, value in row._asdict().items():
            self._file.write(format.format(col, value))
        self._file.write('\n\n')

    def writeHeader(self, columns):
        self._file.write("loop_\n")
        self._columns = columns
        # Write column names
        for col in columns:
            self._file.write("_%s \n" % col.getName())

    def writeRowValues(self, values):
        """ Write to file a line for these row values.
        Order should be ensured that is the same of the expected columns.
        """
        if not self._format:
            self._computeLineFormat([values])
        self._file.write(self._format.format(*values))

    def writeRow(self, row):
        """ Write to file the line for this row.
        Row should be an instance of the expected Row class.
        """
        self.writeRowValues(row._asdict().values())

    def writeNewline(self):
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


class Table(_ColumnsList):
    """
    Class to hold and manipulate tabular data for EM processing programs.
    """
    Reader = _Reader
    Writer = _Writer
    Column = _Column

    def __init__(self, **kwargs):
        _ColumnsList.__init__(self)
        self.clear()

        if 'fileName' in kwargs:
            if 'columns' in kwargs:
                raise Exception("Please provide either 'columns' or 'fileName',"
                                " but not both.")
            fileName = kwargs.get('fileName')
            tableName = kwargs.get('tableName', None)
            self.read(fileName, tableName)
        elif 'columns' in kwargs:
            self._createColumns(kwargs['columns'])

    def clear(self):
        self.Row = None
        self._columns.clear()
        self._rows = []
        self._inputFile = None
        self._inputLine = None

    def clearRows(self):
        """ Remove all the rows from the table, but keep its columns. """
        self._rows = []

    def addRow(self, *args, **kwargs):
        self._rows.append(self.Row(*args, **kwargs))

    def readStar(self, inputFile, tableName=None, guessType=True, types=None):
        """ Parse a given table from the input star file.
        Args:
            inputFile: Provide the input file from where to read the data.
                The file pointer will be moved until the last data line of the
                requested table.
            tableName: star table name
            guessType: if True, the columns type is guessed from the first row.
            types: It can be a dictionary {columnName: columnType} pairs that
                allows to specify types for certain columns.
        """
        self.clear()
        reader = _Reader(inputFile,
                         tableName=tableName, guessType=guessType, types=types)
        self._columns = reader._columns
        self._rows = reader.readAll()
        self.Row = reader.Row

    def read(self, fileName, tableName=None):
        with open(fileName) as f:
            self.readStar(f, tableName)

    def writeStar(self, outputFile, tableName=None, singleRow=False):
        """ Write a Table in Star format to the given file.
        Args:
            outputFile: File handler that should be already opened and
                in the position to write.
            tableName: The name of the table to write.
            singleRow: If True, don't write loop_, just label - value pairs.
        """
        writer = _Writer(outputFile)
        writer.writeTableName(tableName)

        if self.size() == 0:
            return

        if singleRow:
            writer.writeSingleRow(self._rows[0])
        else:
            writer.writeHeader(self._columns.values())
            for row in self:
                writer.writeRow(row)

        writer.writeNewline()

    def write(self, output_star, tableName=None, singleRow=False):
        with open(output_star, 'w') as output_file:
            self.writeStar(output_file,
                           tableName=tableName,
                           singleRow=singleRow)

    def printStar(self, tableName=None):
        self.writeStar(sys.stdout, tableName)

    def size(self):
        return len(self._rows)

    def addColumns(self, *args):
        """ Add one or many columns.

        Each argument should be in the form:
            columnName=value
        where value can be a constant or another column.

        Examples:
            table.addColumns('rlnDefocusU=rlnDefocusV', 'rlnDefocusAngle=0.0')
        """
        # TODO:
        # Maybe implement more complex value expression,
        # e.g some basic arithmetic operations or functions

        map = {k: k for k in self.getColumnNames()}
        constSet = set()
        newCols = OrderedDict()

        for a in args:
            colName, right = a.split('=')
            if self.hasColumn(right):
                colType = self.getColumn(right).getType()
                map[colName] = right
            elif right in newCols:
                colType = newCols[right].getType()
                map[colName] = map[right]
            else:
                colType = _guessType(right)
                value = colType(right)
                map[colName] = value
                constSet.add(value)

            newCols[colName] = _Column(colName, colType)

        # Update columns and create new Row class
        self._columns.update(newCols)
        self._createRowClass()

        # Update rows with new column values
        oldRows = self._rows
        self.clearRows()

        def _get(row, colName):
            # Constants are passed as tuple
            mapped = map[colName]
            return mapped if mapped in constSet else getattr(row, mapped)

        colNames = self.getColumnNames()
        for row in oldRows:
            self._rows.append(self.Row(**{k: _get(row, k) for k in colNames}))

    def removeColumns(self, *args):
        """ Remove columns with these names. """
        # Check if any argument is a list and flatten into a single one
        rmCols = []
        for a in args:
            if isinstance(a, list):
                rmCols.extend(a)
            else:
                rmCols.append(a)

        oldColumns = self._columns
        oldRows = self._rows

        # Remove non desired columns and create again the Row class
        self._columns = OrderedDict([(k, v) for k, v in oldColumns.items()
                                     if k not in rmCols])
        self._createRowClass()

        # Recreate rows without these column values
        cols = self.getColumnNames()
        self.clearRows()

        for row in oldRows:
            self._rows.append(self.Row(**{k: getattr(row, k) for k in cols}))

    def getColumnValues(self, colName):
        """
        Return the values of a given column
        :param colName: The name of an existing column to retrieve values.
        :return: A list with all values of that column.
        """
        if colName not in self._columns:
            raise Exception("Not existing column: %s" % colName)
        return [getattr(row, colName) for row in self._rows]

    def sort(self, key, reverse=False):
        """ Sort the table in place using the provided key.
        If key is a string, it should be the name of one column. """
        keyFunc = lambda r: getattr(r, key) if isinstance(key, str) else key
        self._rows.sort(key=keyFunc, reverse=reverse)

    @staticmethod
    def iterRows(fileName, key=None, reverse=False, **kwargs):
        """
        Convenience method to iterate over the rows of a given table.

        Args:
            fileName: the input star filename, it might contain the '@'
                to specify the tableName
            key: key function to sort elements, it can also be an string that
                will be used to retrieve the value of the column with that name.
            reverse: If true reverse the sort order.
            **kwargs:
                tableName: can be used explicit instead of @ in the filename.
                types: It can be a dictionary {columnName: columnType} pairs that
                    allows to specify types for certain columns in the internal reader
        """
        if '@' in fileName:
            tableName, fileName = fileName.split('@')
        else:
            tableName = kwargs.pop('tableName', None)

        # Create a table iterator
        with open(fileName) as f:
            reader = _Reader(f, tableName, **kwargs)
            if key is None:
                for row in reader:
                    yield row
            else:
                if isinstance(key, str):
                    keyFunc = lambda r: getattr(r, key)
                else:
                    keyFunc = key
                for row in sorted(reader, key=keyFunc, reverse=reverse):
                    yield row

    def __len__(self):
        return self.size()

    def __iterRows(self, line, inputFile):
        """ Internal method to iter through rows. """
        typeList = [c.getType() for c in self.getColumns()]
        while line:
            yield self.Row(*[t(v) for t, v in zip(typeList, line.split())])
            line = inputFile.readline().strip()

    def __iter__(self):
        return iter(self._rows)

    def __getitem__(self, item):
        return self._rows[item]

    def __setitem__(self, key, value):
        self._rows[key] = value


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


