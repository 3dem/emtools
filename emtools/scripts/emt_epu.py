#!/usr/bin/env python

# This script reads the optics group from a movies star file and change it
# accordingly in the particles starfile and writes a new particles star file
# with the updated values

import os
import argparse
from pprint import pprint

from emtools.metadata import EPU


def main():
    p = argparse.ArgumentParser(prog='emt-epu')
    p.add_argument('--scan', metavar='EPU_FOLDER',
                   help="Parse data from this root folder for all "
                        "movies' xml files. Output file will be a star file "
                        "with parsed information. ")
    p.add_argument('--output', '-o',
                   help="Output file depending in the action. ")

    p.add_argument('--backup', '-b', metavar='BACKUP_FOLDER',
                   help="Backup JPG and some XML files.")

    p.add_argument('--info', action='store_true')

    args = p.parse_args()

    kwargs = {}
    if args.scan:
        s = EPU.Session(args.scan, outputStar=args.output, backupFolder=args.backup)
        s.scan()
        s.df.print()


if __name__ == '__main__':
    main()
