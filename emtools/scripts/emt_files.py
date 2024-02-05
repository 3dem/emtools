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
from emtools.metadata import EPU, MovieFiles


def statsDir(folder, sort):
    df = MovieFiles()
    df.scan(folder)
    df.print(sort=sort)
    df.counters[1].print('movie')


def timeStats(pattern, bin, plot):
    files = glob(pattern)
    total_size = 0
    filesDict = {}

    for f in files:
        s = os.stat(f)
        size = s.st_size
        filesDict[f] = {'size': size,
                        'ts': s.st_mtime}

        total_size += size

    fs = sorted((f for f in filesDict.items()), key=lambda f: f[1]['ts'])
    first = fs[0]
    last = fs[-1]

    if bin:
        bindelta = timedelta(minutes=bin)
        start = datetime.fromtimestamp(first[1]['ts'])
        bins = [{'start': start, 'end': start + bindelta, 'count': 0}]
        for k, v in fs:
            last_bin = bins[-1]
            end = last_bin['end']
            ts = datetime.fromtimestamp(v['ts'])
            if ts <= end:
                last_bin['count'] += 1
            else:
                bins.append({'start': end,
                             'end': end + bindelta,
                             'count': 1})

    print(f"Files: {len(files)}")
    print(f"Total size: {Pretty.size(total_size)}")
    print(f"Average size: {Pretty.size(round(total_size / len(files)))}")

    def _print(label, f):
        print(f"{label}: \n\tPath: {f[0]}\n\t"
              f"Date: {Pretty.timestamp(f[1]['ts'])}\n\t"
              f"Size: {Pretty.size(f[1]['size'])}")

    _print("First", first)
    _print("Last", last)
    n = len(bins)
    delta = datetime.fromtimestamp(last[1]['ts']) - datetime.fromtimestamp(first[1]['ts'])
    counts = [b['count'] for b in bins]
    avg = np.mean(counts[:-1]) if n > 1 else counts[0]
    print(f"Total time: {Pretty.delta(delta)}")
    print(f"      Bins: {counts}")
    print(f"       Avg: {avg}")

    if plot:
        import matplotlib.pyplot as plt
        width = 1
        x = np.arange(width, width * (n + 1), width)
        labels = []

        def _addDt(b, onlyTime=False):
            dts = Pretty.datetime(b['start'])
            if onlyTime:
                labels.append(dts.split()[1])
            else:
                labels.append(dts.replace(' ', '\n'))

        _addDt(bins[0])
        last_date = bins[0]['start']

        for b in bins[1:-1]:
            start = b['start']
            if start.day > last_date.day:
                _addDt(b)
                last_date = start
            elif start.hour >= last_date.hour + 4:
                _addDt(b, onlyTime=True)
                last_date = start
            else:
                labels.append('')
        _addDt(bins[-1])
        values = [b['count'] for b in bins]
        fig, ax = plt.subplots(figsize=(24, 8))
        w = width * 0.9
        ax.bar(x + w / 2, values, w, label='Men')
        # Add some text for labels, title and custom x-axis tick labels, etc.
        ax.set_ylabel('Files')
        ax.set_title(f'Files generated every {bin} minutes')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        last_i = None
        annot = ax.annotate("", xy=(0, 0), xytext=(5, 5), textcoords="offset points")
        annot.set_visible(False)

        def hover(event):
            nonlocal last_i
            x, y = event.xdata, event.ydata
            if x and y and 1 < x < n + 1:
                i = int(x) - 1
                b = bins[i]
                if i != last_i:
                    ss = Pretty.datetime(b['start'])
                    es = Pretty.datetime(b['end'])
                    msg = f"{i}: {ss} - {es.split()[1]}"
                    # print(msg)
                    last_i = i
            else:
                last_i = None
                annot.set_visible(False)

        fig.canvas.mpl_connect("motion_notify_event", hover)

        plt.show()


def main():
    p = argparse.ArgumentParser(prog='emt-files')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--stats', '-s', metavar='FOLDER',
                   help="Statistics of the files in a given folder.")
    g.add_argument('--timing', metavar='PATTERN',
                   help="Compute histogram from the timestamps of files "
                        "matching the pattern.")
    g.add_argument('--copy_dir', nargs=2, metavar=('SRC_DIR', 'NEW_DIR'),
                   help='Copy directory with some delay')
    g.add_argument('--check_dirs', nargs=2, metavar=('DIR1', 'DIR2'),
                   help='Check if the two directories are synchronized. ')

    p.add_argument('--bin', '-b', type=int, default=6000,
                   help="Create bins of the given time in minutes "
                        "(with --timing)")
    p.add_argument('--plot', '-p', action='store_true',
                   help="Plot the number of files per bin  "
                        "(with --stats)")
    p.add_argument('--delay', '-d', type=float, default=0,
                   help="Delay in seconds when copying files "
                        "(with --copy_dir)")
    p.add_argument('--sort', choices=['count', 'size'],
                   help="Sort results from --stats with a folder"
                        "based on count or size (with --stats FOLDER)")

    args = p.parse_args()

    def _checkdirs(*dirs):
        for d in dirs:
            if not os.path.exists(d):
                print("ERROR: Missing dir: " + Color.red(d))

    def _mkdir(d):
        if not os.path.exists(d):
            Process.system(f"mkdir -p '{d}'")

    if folder := args.stats:
        statsDir(folder, args.sort)

    elif dirs := args.copy_dir:
        src, dst = args.copy_dir
        # Path.copyDir(src, dst, sleep=args.delay)
        all_files = []
        for root, dirs, files in os.walk(src):
            #root2 = root.replace(dir1, dir2)
            # for d in dirs:
            #     _mkdir(os.path.join(root2, d))
            for f in files:
                srcFn = os.path.join(root, f)
                all_files.append((srcFn, os.stat(srcFn)))
                #_copy(os.path.join(root, f), os.path.join(root2, f), **kwargs)

        # Sort all files by modification time
        # so we can simulate the generation of files in the same order
        # as initially acquired
        all_files.sort(key=lambda t: t[1].st_mtime)
        for t in all_files:
            srcFn = t[0]
            dstFn = srcFn.replace(src, dst)
            _mkdir(os.path.dirname(dstFn))
            Path.copyFile(srcFn, dstFn, sleep=args.delay)

    elif dirs := args.check_dirs:
        sync = Path.inSync(dirs[0], dirs[1], verbose=True)
        s = Color.green('in SYNC') if sync else Color.red('NOT in SYNC')
        print(f"Dirs are {s}")

    elif pattern := args.timing:
        timeStats(pattern, args.bin, args.plot)

    # TODO: check from here
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
                srcFn = os.path.join(root, f)
                if os.path.isfile(srcFn):
                    ed.register(os.path.join(root, f))
        ed.print()


if __name__ == '__main__':
    main()

