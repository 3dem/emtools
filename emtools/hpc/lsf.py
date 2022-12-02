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

import json

from emtools.utils import Color, Process


def print_args(args):
    print("\n>>>", Color.bold(' '.join(args)))


def get_users(queue=None, user=None):
    users = {}
    """ Get a dict with the jobs of some users. """
    args = ['bjobs']
    if user:
        args.extend(['-u', user])
    elif queue:
        args.extend(['-q', queue, '-u', 'all'])
    args.extend(['-o', 'user: jobid: stat: job_name: queue: exec_host ', '-json'])
    print_args(args)
    usersjson = json.loads(Process(*args).stdout)
    for entry in usersjson['RECORDS']:
        user = entry['USER']
        if user not in users:
            users[user] = []
        users[user].append(entry)
    return users


def print_users(users):
    """ Print the list of users. """
    headers = ["USER", "JOBID", "STAT", "QUEUE", "EXEC_HOST"]
    format = u'{:<15}{:<15}{:<5}{:<15}{:<30}'

    print(format.format(*headers))

    for user, jobs in users:
        for entry in jobs:
            values = [entry[k] for k in headers]
            print(format.format(*values))


def nodes_from_users(usersdict):
    nodes = {}
    for user, jobs in usersdict.items():
        for parts in jobs:
            nodestr = parts['EXEC_HOST']
            for n in nodestr.split(':'):
                name = n.split('*')[-1]
                if name not in nodes:
                    nodes[name] = []
                if user not in nodes[name]:
                    nodes[name].append(user)

    return nodes


def get_queues(queuePattern):
    queues = []
    if queuePattern:
        for line in Process("bqueues").lines():
            if 'QUEUE_NAME' not in line and line.strip():
                parts = line.split()
                if queuePattern in parts[0]:
                    queues.append(parts[0])
    return queues


def show_queues(queuePattern):
    """ List available nodes to a given queue """
    if not queuePattern:
        Process('bqueues').print(stdout=True)
        return

    queues = get_queues(queuePattern)

    for q in queues:
        usersdict = get_users(q)
        nodes = nodes_from_users(usersdict)
        args = ["bqueues", "-l", q]
        print_args(args)
        for line in Process(*args).lines():
            if 'HOSTS' in line:
                parts = line.split()
                for p in parts[1:]:
                    reserve = p.split('+')[0].replace('/', '')
                    args = ["bhosts", '-o',
                            'host_name:20 status: max:5 run:5', reserve]
                    print_args(args)
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


def show_jobs(queue=None, user=None):
    def _print_sorted(users):
        print(Color.bold("\n>>> JOBS: "))
        sorted_users = sorted(users.items(), key=lambda u: len(u[1]), reverse=True)
        print_users(sorted_users)

    if user:
        _print_sorted(get_users(queue=None, user=user))
    else:
        queues = get_queues(queue)
        for q in queues:
            _print_sorted(get_users(queue=q))


