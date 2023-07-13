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
from glob import glob

from emtools.utils import Process, Color, Pretty


if __name__ == '__main__':
    p = argparse.ArgumentParser(prog='emt-frames.py')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--transfer', '-t', nargs=2, metavar=('SRC', 'DST'),
                   help='Transfer (move) files from SRC to DST')
    p.add_argument('--dry', action='store_true',
                   help="Do no take any action, just print commands. ")
    args = p.parse_args()

    def _mkdir(root, folder):
        folderPath = os.path.join(root, folder)
        if not os.path.exists(folderPath):
            Process.system(f"mkdir {folderPath}")

    def _checkdirs(*dirs):
        for d in dirs:
            if not os.path.exists(d):
                raise Exception("ERROR: Missing dir: " + Color.red(d))

    def _frames(folder):
        count = 0
        size = 0
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.endswith('fractions.tiff'):
                    count += 1
                    size += os.path.getsize(os.path.join(root, f))
        return count, size

    def _move(srcFile, dstFile):
        Process.system(f'rsync -ac --no-perms --remove-source-files {srcFile} {dstFile}')

    if args.transfer:
        src, dst = args.transfer
        _checkdirs(src, dst)

        for root, dirs, files in os.walk(src):
            rootDst = root.replace(src, dst)
            for d in dirs:
                _mkdir(rootDst, d)
            for f in files:
                if f.endswith('fractions.tiff'):
                    srcFile = os.path.join(root, f)
                    dstFile = srcFile.replace(src, dst)
                    Process.system(f'rsync -ac --no-perms --remove-source-files {srcFile} {dstFile}',
                                   only_print=args.dry)

        Process.system(f'rsync -ac --no-perms {src}/ {dst}/',
                       only_print=args.dry)

    else:  # Default option to scan directories and check for movies
        gscem_pattern = '/research/cryo_core_raw/*/*/2023/raw/EPU/*/'
        gscem_folders = glob(gscem_pattern)
        gscem = {}
        for gf in gscem_folders:
            for f in os.listdir(gf):
                gscem[f] = os.path.join(gf, f)

        frames_root = '/mnt/EPU_frames/'
        frame_folders = [os.path.join(frames_root, f) for f in os.listdir(frames_root)]

        frame_folders.sort(key=lambda f: os.path.getmtime(f))

        for f in frame_folders:
            frames, size = _frames(f)
            if frames:
                gf = gscem.get(os.path.basename(f), None)
                gfs = Color.bold(gf) if gf else 'None'
                print(f"\n{f}: {Color.red(frames)} {Pretty.size(size)}\n  -> {gfs}")



