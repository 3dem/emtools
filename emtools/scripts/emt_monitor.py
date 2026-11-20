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

"""
Record the CPU, memory, I/O and GPU usage of a process tree into a CSV file
(see emtools.utils.ResourceMonitor), or print the summary of such a file.
"""

import os
import argparse

import psutil

from emtools.utils import ResourceMonitor


def _lowPriority():
    """ Lowest CPU and I/O priority, best effort. """
    try:
        os.nice(19)
    except OSError:
        pass
    try:
        psutil.Process().ionice(psutil.IOPRIO_CLASS_IDLE)
    except (AttributeError, psutil.Error, OSError):
        pass


def main():
    p = argparse.ArgumentParser(
        prog='emt-monitor',
        description="Record the CPU, memory, I/O and GPU usage of a process "
                    "tree into a CSV file, or summarize such a file.")
    p.add_argument('--pid', type=int, help="Root process to monitor.")
    p.add_argument('--output', '-o', help="Output CSV file.")
    p.add_argument('--interval', type=float, default=2,
                   help="Seconds between samples (default: 2).")
    p.add_argument('--gpus', default='',
                   help="GPUs used by the job, as the job sees them (CUDA "
                        "device ids separated by commas) or 'all'.")
    p.add_argument('--summary', metavar='CSV',
                   help="Print the summary of a CSV file and exit.")
    args = p.parse_args()

    if args.summary:
        print('\n'.join(ResourceMonitor.summary_lines(
            ResourceMonitor.summarize(args.summary))))
        return

    if not args.pid or not args.output:
        p.error("--pid and --output are required to monitor a process.")

    _lowPriority()
    gpus = args.gpus.strip()
    if gpus.lower() != 'all':
        gpus = [int(g) for g in gpus.split(',') if g.strip()]
    ResourceMonitor(args.pid, args.output, args.interval, gpus).run()


if __name__ == '__main__':
    main()
