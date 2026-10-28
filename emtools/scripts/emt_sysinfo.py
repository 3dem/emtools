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
Quick summary of this workstation: OS/distro, kernel, CPUs, RAM, disk and
GPUs. Mostly a thin, friendly wrapper around emtools.utils.System.
"""

import json
import argparse
import platform

from emtools.utils import Color, Pretty, System


def get_info(disk_path='/'):
    """ Collect a dict with a quick summary of this workstation.
    Reuses emtools.utils.System for all the underlying lookups. """
    return {
        'hostname': System.hostname(),
        'os': System.distro(),
        'kernel': System.kernel(),
        'arch': platform.machine(),
        'cpus': System.cpus(),
        'memory_gb': System.memory(),
        'disk': System.disk(disk_path),
        'disk_path': disk_path,
        'gpus': System.gpus(),
    }


def print_info(info):
    """ Print a nicely formatted report from the dict returned by get_info(). """
    width = 70
    title = f" SYSTEM INFO: {info['hostname']} "
    print(Color.bold(title.center(width, '=')))
    print(f" {'OS':<10}: {info['os']}")
    print(f" {'Kernel':<10}: {info['kernel']} ({info['arch']})")
    print(f" {'CPUs':<10}: {info['cpus']}")
    print(f" {'Memory':<10}: {info['memory_gb']} GB")

    disk = info['disk']
    if disk:
        pct = 100 * disk['used'] / disk['total'] if disk['total'] else 0
        print(f" {'Disk (' + info['disk_path'] + ')':<10}: "
             f"{Pretty.size(disk['total'])} total, "
             f"{Pretty.size(disk['free'])} free ({pct:.0f}% used)")

    gpus = info['gpus']
    print(f" {'GPUs':<10}: {len(gpus)}")
    for g in gpus:
        line = (f"   [{g.get('index', '?')}] {g.get('name', 'Unknown GPU'):<28} "
               f"{g.get('memory.total', '?'):>10} total  "
               f"{g.get('memory.used', '?'):>10} used  "
               f"driver {g.get('driver_version', '?')}")
        print(Color.cyan(line))

    print(Color.bold('=' * width))


def main():
    p = argparse.ArgumentParser(
        prog='emt-sysinfo',
        description="Print a quick summary of this workstation's hardware "
                    "and OS: Linux distro/version, kernel, CPUs, RAM, disk "
                    "usage and GPUs.")
    p.add_argument('--json', '-j', action='store_true',
                   help='Print the info as JSON instead of the formatted report.')
    p.add_argument('--disk-path', default='/',
                   help='Path used to report disk usage (default: /).')

    args = p.parse_args()
    info = get_info(disk_path=args.disk_path)

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print_info(info)


if __name__ == '__main__':
    main()
