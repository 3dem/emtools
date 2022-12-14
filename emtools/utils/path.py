
import os
from glob import glob
from datetime import datetime as dt
from datetime import timedelta
import numpy as np

from .pretty import Pretty


class Path:
    @staticmethod
    def splitall(path):
        return os.path.normpath(path).split(os.path.sep)


class Main:
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('pattern', help="Pattern of files to inspect")
        parser.add_argument('--bin', '-b', type=int,
                            help="Create bins of the given time in minutes")
        parser.add_argument('--plot', '-p', action='store_true',
                            help="Plot the number of files per bin")

    @staticmethod
    def run(args):
        files = glob(args.pattern)
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

        if args.bin:
            bindelta = timedelta(minutes=args.bin)
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
        print(f"Average size: {Pretty.size(round(total_size/len(files)))}")

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

        def plot():
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
            rects1 = ax.bar(x + w/2, values, w, label='Men')
            # Add some text for labels, title and custom x-axis tick labels, etc.
            ax.set_ylabel('Files')
            ax.set_title(f'Files generated every {args.bin} minutes')
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

        if args.plot:
            plot()
