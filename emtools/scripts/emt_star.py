#!/usr/bin/env python
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
import time
import argparse
from glob import glob
from datetime import datetime, timedelta
from pprint import pprint
import numpy as np
from collections import defaultdict

from emtools.utils import Process, Color, Path, Timer, Pretty
from emtools.metadata import StarFile


def printStarInfo(starFile):
    with StarFile(starFile) as sf:
        tables = sf.getTableNames()
        for t in tables:
            cols = sf.getTableInfo(t).getColumnNames()
            tSize = sf.getTableSize(t)
            print(f">>> {Color.bold('Table')}: {Color.green(t)}"
                  f"\n    - Columns: {Color.cyan(len(cols))} [{' '.join(c for c in cols)}]"
                  f"\n    -    Rows: {Color.cyan(tSize)}")


def groupBy(starFile, table, column):
    group = defaultdict(lambda: 0)

    with StarFile(starFile) as sf:
        for row in sf.iterTable(table):
            group[row.get(column)] += 1

    for k, v in group.items():
        print(k, v)


def splitBy(starFile, column, minSize):
    with StarFile(starFile) as sf:
        tOptics = sf.getTable('optics')
        tParticles = sf.getTableInfo('particles')
        rows = []
        count = 0
        map = {}

        def _writeStar(minSize=0):
            nonlocal count
            nonlocal rows

            if len(rows) <= minSize:
                return

            count += 1
            outStarFile = Path.replaceExt(starFile, f'_{count:03}.star')
            with StarFile(outStarFile, 'w') as sfOut:
                sfOut.writeTimeStamp()
                sfOut.writeTable('optics', tOptics)
                sfOut.writeHeader('particles', tParticles)
                for row in rows:
                    sfOut.writeRow(row)
            rows = []

        lastValue = None
        lastIndex = 0

        for row in sf.iterTable('particles'):
            value = getattr(row, column)
            if lastValue is not None and lastValue != value:
                _writeStar(int(minSize))
            rows.append(row)
            lastValue = value

        if rows:
            _writeStar(0)  # Write all remaining


def main():
    p = argparse.ArgumentParser(prog='emt-star')
    p.add_argument('input',
                   help="Input STAR file. ")
    p.add_argument('--group_by', '-g', nargs=2,
                   metavar=('TABLE', 'COLUMN'),
                   help="Count rows grouped by a given label")
    p.add_argument('--split_particles', '-s', nargs='+', metavar=('COLUMN', 'minsize'),
                   help="Split input particles by some column")

    args = p.parse_args()
    inputStar = args.input

    if args.group_by:
        table, column = args.group_by
        groupBy(inputStar, table, column)
    elif split := args.split_particles:
        column = split[0]
        minSize = split[1] if len(split) > 1 else 0
        splitBy(inputStar, column, minSize)
    else:
        printStarInfo(args.input)


if __name__ == '__main__':
    main()
