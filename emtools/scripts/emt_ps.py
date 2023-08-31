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
import argparse

from emtools.utils import Process, Color


def main():
    p = argparse.ArgumentParser(prog='emt-ps',
                                help="xxx")
    p.add_argument('program', default='', nargs='?',
                   help="Program name to check running processes")
    p.add_argument('--folder', '-f',
                   help='Folder to check where the processes are running')
    p.add_argument('--kill', '-k', action='store_true',
                   help='Kill matching processes')
    args = p.parse_args()

    kill = args.kill
    folderPath = os.path.abspath(args.folder) if args.folder else args.folder
    print('path', folderPath)
    processes = Process.ps(args.program, workingDir=folderPath)

    color = Color.red if kill else Color.bold

    for folder, procs in processes.items():
        print(f"{Color.warn(folder)}")
        prefix = 'Killing' if kill else ''
        for p in procs:
            print(f"   {p.info['username']} - {prefix} {color(p.info['name']):<30} {p.cmdline()}")
            if kill:
                try:
                    p.kill()
                except:
                    pass


if __name__ == '__main__':
    main()
