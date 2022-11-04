#!/usr/bin/env python

from .raw import Main as raw_Main
from .otf import Main as otf_Main
import argparse


parser = argparse.ArgumentParser(prog='emtools.session')
subparsers = parser.add_subparsers(
    help='Type of session (raw or otf)',
    dest='command')

raw_Main.add_arguments(subparsers.add_parser("raw"))
otf_Main.add_arguments(subparsers.add_parser("otf"))

parser.add_argument('--verbose', '-v', action='count')

args = parser.parse_args()
cmd = args.command

if cmd == "raw":
    raw_Main.run(args)
elif cmd == 'otf':
    otf_Main.run(args)
else:
    parser.print_help()
