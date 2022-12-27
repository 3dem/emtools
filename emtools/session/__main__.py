#!/usr/bin/env python

from .raw import Main as raw_Main
from .otf import Main as otf_Main
from .sessions import Main as sessions_Main
import argparse


parser = argparse.ArgumentParser(prog='emtools.session')
subparsers = parser.add_subparsers(
    help='Type of session (raw or otf)',
    dest='command')

sessions_Main.add_arguments(subparsers.add_parser("session"))
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
    sessions_Main.run(args)
    #parser.print_help()
