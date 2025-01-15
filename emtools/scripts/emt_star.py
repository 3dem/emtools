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


def main():
    p = argparse.ArgumentParser(prog='emt-star')
    p.add_argument('input',
                   help="Input STAR file. ")

    args = p.parse_args()
    printStarInfo(args.input)


if __name__ == '__main__':
    main()

