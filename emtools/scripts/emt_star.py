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


def main():
    p = argparse.ArgumentParser(prog='emt-star')
    p.add_argument('input',
                   help="Input STAR file. ")
    p.add_argument('--group_by', '-g', nargs=2,
                   metavar=('TABLE', 'COLUMN'),
                   help="Count rows grouped by a given label")

    args = p.parse_args()

    if args.group_by:
        table, column = args.group_by
        groupBy(args.input, table, column)
    else:
        printStarInfo(args.input)


if __name__ == '__main__':
    main()

