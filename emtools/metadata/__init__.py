# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
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
# *  e-mail address 'delarosatrevin@scilifelab.se'
# *
# **************************************************************************


class MetaData:
    """ Class to handle multiple Tables datasets, in different formats. """

    def __init__(self, fileName):
        self._filename = fileName
        self._tables = None

        if fileName.endswith('.star'):
            pass
        else:
            raise Exception('File type not supported')

    @property
    def tables(self):
        """ Return the table names in this metadata. """
        if self._tables is None:
            self._tables = []
            with open(self._filename) as f:
                for line in f:
                    l = line.strip()
                    if l.startswith('data_'):
                        self._tables.append(l.replace('data_', ''))
        return self._tables


from .table import Column, ColumnList, Table
from .starfile import StarReader, StarWriter
