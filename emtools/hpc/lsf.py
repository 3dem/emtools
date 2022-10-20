#!/usr/bin/env python3
# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@scilifelab.se'
# *
# **************************************************************************

""" 
This script will check for actions to be taken on sessions,
e.g: create folders or the README file
"""

from emtools.utils import Color, Process


def usage():
    nodes = {}
    for line in Process('bjobs', '-u', 'all', '-o', 'user exec_host').lines():
        if line:
            user, nodestr = line.split()
            for n in nodestr.split(':'):
                name = n.split('*')[-1]
                if name not in nodes:
                    nodes[name] = []
                if user not in nodes[name]:
                    nodes[name].append(user)
    return nodes


def show_queues(queueName):
    """ List available nodes to a given queue """
    if not queueName:
        Process('bqueues').print()
        return

    nodes = usage()

    queues = []
    for line in Process("bqueues").lines():
        if 'QUEUE_NAME' not in line and line.strip():
            parts = line.split()
            queues.append(parts[0])

    for q in queues:
        if queueName in q:
            print()
            for line in Process("bqueues", "-l", q).lines():
                if 'HOSTS' in line:
                    parts = line.split()
                    for p in parts[1:]:
                        reserve = p.split('+')[0].replace('/', '')
                        print()
                        args = ["bhosts", '-o',
                                'host_name:20 status: max:5 run:5', reserve]
                        for line2 in Process(*args).lines():
                            if 'HOST_NAME' in line2:
                                print(line2 + '\tUSERS')
                            elif line2:
                                parts = line2.split()
                                users = nodes.get(parts[0], [])
                                if users:
                                    line2 += f'\t{" ".join(users)}'
                                if 'closed' in parts[1]:
                                    line2 = Color.red(line2)
                                elif int(parts[3]) > 0:
                                    line2 = Color.warn(line2)

                                print(line2)
