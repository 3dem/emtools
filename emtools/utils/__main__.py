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
