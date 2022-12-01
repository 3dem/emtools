#!/usr/bin/env python

from .path import Main as path_Main
import argparse


parser = argparse.ArgumentParser(prog='emtools.utils')
subparsers = parser.add_subparsers(
    help="Utils' command (path)",
    dest='command')

path_Main.add_arguments(subparsers.add_parser("path"))
parser.add_argument('--verbose', '-v', action='count')
args = parser.parse_args()
cmd = args.command

if cmd == "path":
    path_Main.run(args)
else:
    parser.print_help()
