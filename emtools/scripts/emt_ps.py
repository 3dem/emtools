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
import sys
import argparse
from pprint import pprint

from emtools.utils import Process, Color, System


def main():
    p = argparse.ArgumentParser(prog='emt-ps',
                                description="Utility script to monitor programs execution.")

    p.add_argument('--specs', '-s', action='store_true',
                   help='Print out this machine hardware specifications.')
    p.add_argument('--hostname', action='store_true',
                   help='Print out this machine hostname.')
    p.add_argument('--name', '-n',
                   help="Program name to check running processes")
    p.add_argument('--folder', '-f',
                   help='Folder to check where the processes are running')
    p.add_argument('--kill', '-k', action='store_true',
                   help='Kill matching processes')
    p.add_argument('--children', '-c', action='store_true',
                   help='Include also children processes together with '
                        'matching processes.')
    p.add_argument('--verbose', '-v', action='count', default=0,
                   help='More verbose outputs.')

    args = p.parse_args()

    specs = System.specs()
    cpus = specs['CPUs']

    if args.specs:
        pprint(specs)
        sys.exit(0)
    elif args.hostname:
        print(System.hostname())
        sys.exit(0)

    folderPath = os.path.abspath(args.folder) if args.folder else args.folder
    print('path', folderPath)
    Process.checkChilds(args.name, folderPath, kill=args.kill, verbose=args.verbose)


if __name__ == '__main__':
    main()
