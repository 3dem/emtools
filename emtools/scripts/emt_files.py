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
from datetime import datetime, timedelta
from pprint import pprint

from emtools.utils import Process, Color, Path, Timer
from emtools.metadata import EPU


def main():
    p = argparse.ArgumentParser(prog='emt-files')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--copy', nargs=3, metavar=('SRC', 'DST', 'delay'),
                   help='Copy files from SRC ot DST with certain delay')
    g.add_argument('--transfer', nargs=3, metavar=('FRAMES', 'RAW', 'EPU'),
                   help='Transfer (move) files from SRC to DST')
    g.add_argument('--parse', metavar='DIR',
                   help='Parse and print file stats from DIR')
    g.add_argument('--epu', nargs=2, metavar=('SRC', 'DST'),
                   help="Parse EPU input folder and makes a backup")
    args = p.parse_args()

    def _checkdirs(*dirs):
        for d in dirs:
            if not os.path.exists(d):
                print("ERROR: Missing dir: " + Color.red(d))

    if args.copy:
        src, dst, delayStr = args.copy
        delay = float(delayStr)

        _checkdirs(src, dst)
        files = []
        def _append(srcFile, dstFile, **kwargs):
            s = os.stat(srcFile)
            files.append((s, srcFile, dstFile))
        Path.copyDir(src, dst, _append)
        files.sort(key=lambda f: f[0].st_mtime)
        t = Timer()
        for _, srcFile, dstFile in files:
            t.tic()
            Path.copyFile(srcFile, dstFile, sleep=delay)
            t.toc()

    elif args.transfer:
        frames, raw, epu = args.transfer
        td = timedelta(minutes=1)
        ed = Path.ExtDict()
        epuData = EPU.Data(frames, epu)

        now = None
        movies = []

        def _moveFile(srcFile, dstFile):
            s = os.stat(srcFile)
            dt = datetime.fromtimestamp(s.st_mtime)
            if now - dt >= td:
                ed.register(srcFile, stat=s)
                # Register creation time of movie files
                if srcFile.endswith('_fractions.tiff'):
                    movies.append((os.path.relpath(srcFile, frames), s))
                else:  # Copy metadata files into the OTF/EPU folder
                    dstEpuFile = dstFile.replace(raw, epu)
                    dstEpuDir = os.path.dirname(dstEpuFile)
                    if not os.path.exists(dstEpuDir):
                        Process.system(f'mkdir -p "{dstEpuDir}"')
                    Process.system(f'cp "{srcFile}" "{dstEpuFile}"')
                Process.system(f'rsync -ac --remove-source-files "{srcFile}" "{dstFile}"')

        sync = False
        while not sync:
            now = datetime.now()
            movies = []
            Path.copyDir(frames, raw, _moveFile)
            if movies:
                for m in movies:
                    epuData.addMovie(*m)
                epuData.write()
                pprint(epuData.info())
            time.sleep(30)
            sync = Path.inSync(frames, raw)

        pprint(epuData.info())

    elif args.parse:
        ed = Path.ExtDict()
        for root, dirs, files in os.walk(args.parse):
            for f in files:
                fn = os.path.join(root, f)
                if os.path.isfile(fn):
                    ed.register(os.path.join(root, f))
        ed.print()
    #
    # elif args.epu:
    #     inEPU, outEPU = args.epu
    #     epuStar = os.path.join(outEPU, 'movies.star')
    #     info = EPU.parse_session(inEPU, outputStar=epuStar, backupFolder=outEPU)
    #     pprint(info)


if __name__ == '__main__':
    main()

