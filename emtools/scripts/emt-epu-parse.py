#!/usr/bin/env python

# This script reads the optics group from a movies star file and change it
# accordingly in the particles starfile and writes a new particles star file
# with the updated values

import os
import argparse
from pprint import pprint

from emtools.metadata import EPU


def main():
    p = argparse.ArgumentParser(prog='emt-epu-parse')
    p.add_argument('rootFolder',
                   help="Parse data from this root folder for all "
                        "movies' xml files. Output file will be a star file "
                        "with parsed information. ")
    p.add_argument('--output', '-o', default='',
                   help="Output file depending in the action. ")

    p.add_argument('--limit', '-l', default=0, type=int,
                   help="Limit number of entries (for debugging)")

    p.add_argument('--backup', '-b', default='',
                   help="Backup metadata files")

    p.add_argument('--info', action='store_true')
    p.add_argument('--last_movie', default='')

    args = p.parse_args()

    kwargs = {}
    if not args.info:
        doBackup = bool(args.backup)
        backupFolder = args.backup or os.path.dirname(args.output)
        kwargs = {
            'outputStar': args.output,
            'backupFolder': backupFolder,
            'doBackup': doBackup,
            'limit': args.limit
        }
        if args.last_movie:
            kwargs['lastMovie'] = args.last_movie

    info = EPU.parse_session(args.rootFolder, **kwargs)
    pprint(info)


if __name__ == '__main__':
    main()
