
import os
import time
from glob import glob
from datetime import datetime as dt
from datetime import timedelta
from collections import OrderedDict
import numpy as np

from .pretty import Pretty
from .process import Process
from .color import Color


class Path:
    class ExtDict(OrderedDict):
        """ Keep track of number of files and size by extension. """
        def register(self, filename, stat=None):
            """ Register a file, if stat is None it will be calculated. """
            stat = stat or os.stat(filename)
            ext = os.path.splitext(filename)[1]
            if ext not in self:
                self[ext] = {'count': 0, 'size': 0}
            s = self[ext]
            s['count'] += 1
            s['size'] += stat.st_size

        def print(self, sort=None):
            f = '{:<10}{:<10}{:<15}'
            if sort:
                items = sorted(self.items(), key=lambda kv: kv[1][sort])
            else:
                items = self.items()

            for k, v in items:
                if isinstance(v, dict):
                    k = k or 'no-ext'
                    print(f.format(k, v['count'], Pretty.size(v['size'])))
                else:
                    print(f"{k}: {v}")
            print(f.format('TOTAL', self.total_count, Pretty.size(self.total_size)))

        def update(self, d, **kwargs):
            for k, v in d.items():
                if k in self:
                    sv = self[k]
                    sv['count'] += v['count']
                    sv['size'] += v['size']
                else:
                    self[k] = dict(v)

        @property
        def total_size(self):
            return sum(v['size'] for v in self.values())

        @property
        def total_count(self):
            return sum(v['count'] for v in self.values())

    @staticmethod
    def splitall(path):
        return os.path.normpath(path).split(os.path.sep)

    @staticmethod
    def checkDirs(dir1, dir2, verbose=False):
        """ Use rsync as a subprocess to check if the two directories
        are synchronized. Both directories must exist.
        """
        if not dir1.endswith('/'):
            dir1 += '/'
        if not dir2.endswith('/'):
            dir2 += '/'

        p = Process('rsync', '--dry-run', '-a', '--stats', dir1, dir2)
        if verbose:
            p.print(stdout=True)

        transf = 1
        for line in p.lines():
            if 'files transferred:' in line:
                transf = int(line.split(':')[1])
                break
        return transf == 0

    @staticmethod
    def lastModified(folder):
        """ Return the last modified file and modified time. """
        files = os.listdir(folder)
        last = None

        for fn in files:
            f = os.path.join(folder, fn)
            s = os.stat(f)
            t = (f, s.st_mtime)
            last = t if not last or s.st_mtime > last[1] else last

        return last[0], dt.fromtimestamp(last[1])

    @staticmethod
    def copyFile(file1, file2, sleep=0):
        """ Copy two files controlling with some possible delay. """
        bufsize = 8 * 1024 * 1024
        print(f'Copying {file1} {file2}')
        with open(file1, "rb") as f1:
            with open(file2, 'wb') as f2:
                while rbytes := f1.read(bufsize):
                    f2.write(rbytes)
                    if sleep:
                        time.sleep(sleep)
        #Process.system(f'cp {file1} {file2}')

    @staticmethod
    def copyDir(dir1, dir2, copyFileFunc=None, **kwargs):
        """ This is a test method to copy a whole directory and control
        the speed of the copy and how files appear in the destination.
        A custom copyFileFunc can be passed to copy files. If None,
        Path.copyFile will be used.
        **kwargs will be passed to copyFile
        """
        _copy = copyFileFunc or Path.copyFile

        def _mkdir(d):
            if not os.path.exists(d):
                Process.system(f"mkdir {d}")

        if not os.path.exists(dir1):
            raise Exception(f"Source directory must exits")

        _mkdir(dir2)

        for root, dirs, files in os.walk(dir1):
            root2 = root.replace(dir1, dir2)
            for d in dirs:
                _mkdir(os.path.join(root2, d))
            for f in files:
                _copy(os.path.join(root, f), os.path.join(root2, f), **kwargs)


class Main:
    @staticmethod
    def add_arguments(parser):
        g = parser.add_mutually_exclusive_group()
        g.add_argument('--stats', metavar='PATTERN_OR_FOLDER',
                       help="Statistics of some files given a pattern or from "
                            "a folder.")
        g.add_argument('--copy_dir', nargs=2, metavar=('SRC_DIR', 'NEW_DIR'),
                       help='Copy directory with some delay')
        g.add_argument('--check_dirs', nargs=2, metavar=('DIR1', 'DIR2'),
                       help='Check if the two directories are synchronized. ')

        parser.add_argument('--bin', '-b', type=int, default=6000,
                            help="Create bins of the given time in minutes "
                                 "(with --stats)")
        parser.add_argument('--plot', '-p', action='store_true',
                            help="Plot the number of files per bin  "
                                 "(with --stats)")
        parser.add_argument('--delay', '-d', type=float, default=0,
                            help="Delay in seconds when copying files "
                                 "(with --copy_dir)")
        parser.add_argument('--sort', choices=['count', 'size'],
                            help="Sort results from --stats with a folder"
                                 "based on count or size (with --stats FOLDER)")

    @staticmethod
    def run(args):
        if pattern := args.stats:
            if os.path.exists(pattern) and os.path.isdir(pattern):
                statsDir(pattern, args.sort)
            else:
                stats(pattern, args.bin, args.plot)
        elif dirs := args.copy_dir:
            Path.copyDir(dirs[0], dirs[1], sleep=args.delay)
        elif dirs := args.check_dirs:
            sync = Path.checkDirs(dirs[0], dirs[1], verbose=True)
            s = Color.green('in SYNC') if sync else Color.red('NOT in SYNC')
            print(f"Dirs are {s}")


def statsDir(folder, sort):
    folders = 0
    ed = Path.ExtDict()
    for root, dirs, files in os.walk(folder):
        folders += len(dirs)
        for f in files:
            ed.register(os.path.join(root, f))

    print(f"Folders: {folders}")
    ed.print(sort)


def stats(pattern, bin, plot):
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
        start = dt.fromtimestamp(first[1]['ts'])
        bins = [{'start': start, 'end': start + bindelta, 'count': 0}]
        for k, v in fs:
            last_bin = bins[-1]
            end = last_bin['end']
            ts = dt.fromtimestamp(v['ts'])
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
    delta = dt.fromtimestamp(last[1]['ts']) - dt.fromtimestamp(first[1]['ts'])
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
        rects1 = ax.bar(x + w / 2, values, w, label='Men')
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
                    print(msg)
                    last_i = i
            else:
                last_i = None
                annot.set_visible(False)

        fig.canvas.mpl_connect("motion_notify_event", hover)

        plt.show()
