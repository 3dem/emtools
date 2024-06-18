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

from .motioncor import Main as mc_Main
import argparse


parser = argparse.ArgumentParser(prog='emtools.processing')
subparsers = parser.add_subparsers(
    help="Utils' command (motioncor)",
    dest='command')

mc_Main.add_arguments(subparsers.add_parser("motioncor"))
parser.add_argument('--verbose', '-v', action='count')
args = parser.parse_args()
cmd = args.command

if cmd == "motioncor":
    mc_Main.run(args)
elif cmd:
    raise Exception(f"Unknown option '{cmd}'")
else:
    parser.print_help()
