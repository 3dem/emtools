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


from collections import OrderedDict, namedtuple


class Column:
    def __init__(self, name, type=None):
        self._name = name
        self._type = type or _str

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


class ColumnList:
    def __init__(self, columns=None):
        self._columns = OrderedDict()
        for col in columns or []:
            if isinstance(col, Column):
                self._columns[col.getName()] = col
            elif isinstance(col, str):
                self._columns[col] = Column(col)
            else:
                raise Exception('Invalid type %s for column name.' % col)

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

    def createRowClass(self):

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

        return Row

    @staticmethod
    def createColumns(colNames, values, guessType=True, types=None):
        """ Return a list of Columns create from the names.
        Args:
            colNames: the string list with column names
            values: values (can be None) for guessing the column type
            guessType: if False type will not be guessed even if values is passed
            types: optional dict with types for some columns
        """
        columns = []
        types = types or {}
        for i, colName in enumerate(colNames):
            if colName in types:
                colType = types[colName]
            elif guessType and values:
                colType = _guessType(values[i])
            else:
                colType = _str
            columns.append(Column(colName, colType))

        return columns


class Table(ColumnList):
    """
    Class to hold and manipulate tabular data.
    """
    def __init__(self, columns=None):
        ColumnList.__init__(self, columns)
        self.Row = self.createRowClass()
        self._rows = []

    def clear(self):
        self.Row = None
        self._columns.clear()
        self._rows = []

    def clearRows(self):
        """ Remove all the rows from the table, but keep its columns. """
        self._rows = []

    def addRow(self, row):
        """ Add a new Row. """
        self._rows.append(row)

    def addRowValues(self, *args, **kwargs):
        """ Append a new Row from the given values. """
        row = self.Row(*args, **kwargs)
        self._rows.append(row)
        return row

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

            newCols[colName] = Column(colName, colType)

        # Update columns and create new Row class
        self._columns.update(newCols)
        self.Row = self.createRowClass()

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

        # Remove undesired columns and create again the Row class
        self._columns = OrderedDict([(k, v) for k, v in oldColumns.items()
                                     if k not in rmCols])
        self.Row = self.createRowClass()

        # Recreate rows without these column values
        cols = self.getColumnNames()
        self.clearRows()

        for row in oldRows:
            self._rows.append(self.Row(**{k: getattr(row, k) for k in cols}))

    def getColumnValues(self, colName):
        """
        Return the values of a given column

        Args:
            colName: The name of an existing column to retrieve values.

        Return:
            A list with all values of that column.
        """
        if colName not in self._columns:
            raise Exception("Not existing column: %s" % colName)
        return [getattr(row, colName) for row in self._rows]

    def sort(self, key, reverse=False):
        """ Sort the table in place using the provided key.
        If key is a string, it should be the name of one column. """
        def keyFunc(r):
            return getattr(r, key) if isinstance(key, str) else key
        self._rows.sort(key=keyFunc, reverse=reverse)

    def print(self, formatStr=None):
        for row in self._rows:
            print(formatStr.format(**row._asdict()))

    def __len__(self):
        return self.size()

    def __iter__(self):
        return iter(self._rows)

    def __getitem__(self, item):
        return self._rows[item]

    def __setitem__(self, key, value):
        self._rows[key] = value


# --------- Helper functions  ------------------------
def _str(s):
    """ Get the string value but stripping quotes if present. """
    return s[1:-1] if s.startswith('"') and s.endswith('"') else s


def _guessType(strValue):
    try:
        int(strValue)
        return int
    except ValueError:
        try:
            float(strValue)
            return float
        except ValueError:
            return _str


def _formatValue(v):
    return '%0.6f' % v if isinstance(v, float) else str(v)


def _getFormatStr(v):
    return '.6f' if isinstance(v, float) else ''
