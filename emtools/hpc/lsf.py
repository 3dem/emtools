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








def print_users(users):
    """ Print the list of users. """
    headers = ["USER", "JOBID", "STAT", "QUEUE", "EXEC_HOST"]
    format = u'{:<20}{:<15}{:<5}{:<15}{:<30}'

    print(format.format(*headers))

    for user, jobs in users:
        for entry in jobs:
            values = [entry[k] for k in headers]
            print(format.format(*values))





class LSF:
    """ Utility class to group some functions. """
    def __init__(self, **kwargs):
        self.debug = kwargs.get('debug', False)

    def print_args(self, args):
        if self.debug:
            print("\n>>>", Color.bold(' '.join(args)))

    def get_queues(self, queuePattern):
        queues = []
        if queuePattern:
            args = ["bqueues", "-o", "queue_name", "-json"]
            p = Process(*args, doRaise=False)

            if self.debug:
                p.print()
            queuesjson = json.loads(p.stdout)

            for entry in queuesjson['RECORDS']:
                queueName = entry['QUEUE_NAME']
                if queuePattern in queueName:
                    queues.append(queueName)

        return queues

    def get_users(self, queue=None, user=None):
        users = {}
        """ Get a dict with the jobs of some users. """
        args = ['bjobs']
        if user:
            args.extend(['-u', user])
        elif queue:
            args.extend(['-q', queue, '-u', 'all'])
        args.extend(['-o', 'user: jobid: stat: job_name: queue: exec_host ', '-json'])

        self.print_args(args)

        usersjson = json.loads(Process(*args).stdout)
        for entry in usersjson['RECORDS']:
            user = entry['USER']
            if user not in users:
                users[user] = []
            users[user].append(entry)

        return users

    def nodes_from_users(self, usersdict):
        nodes = {}
        for user, jobs in usersdict.items():
            for parts in jobs:
                nodestr = parts['EXEC_HOST']
                for n in nodestr.split(':'):
                    if '*' in n:
                        cores, name = n.split('*')
                    else:
                        cores, name = 1, n

                    if name not in nodes:
                        nodes[name] = {}
                    if user not in nodes[name]:
                        nodes[name][user] = []
                    nodes[name][user].append({
                        'jobid': parts['JOBID'],
                        'cores': cores
                    })
        return nodes

    def show_queues(self, queuePattern, outputJson=False):
        queuesJson = self.get_queues_json(queuePattern)

        if not queuePattern or not queuesJson:
            Process('bqueues').print(stdout=True)
            return

        if outputJson:
            print(json.dumps(queuesJson, indent=4))
            return

        # Normal show as a list with color codes
        headers = ["HOST_NAME", "STATUS", "MAX", "RUN", "USERS"]
        format_str = u'{:<20}{:<15}{:<10}{:<10}{:<}'
        print(format_str.format(*headers))

        for hostname, info in queuesJson.items():
            usersStr = ' '.join(info['users'].keys())
            status = info['status']
            line = format_str.format(hostname, status,
                                     info['max'], info['run'],
                                     usersStr)
            if 'closed' in status or 'unavail' in status:
                color = Color.red
            elif int(info['run']) > 0:
                color = Color.warn
            else:
                color = None

            print(color(line) if color else line)

    def get_queues_json(self, queuePattern):
        """ List available nodes to a given queue """
        json = {}
        queues = self.get_queues(queuePattern)

        for q in queues:
            args = ["bqueues", "-l", q]
            proc = Process(*args, doRaise=False)

            if proc.returncode == 0:
                usersdict = self.get_users(q)
                nodes = self.nodes_from_users(usersdict)

                for line in proc.lines():
                    if 'HOSTS' in line:
                        parts = line.split()
                        for p in parts[1:]:
                            reserve = p.split('+')[0].replace('/', '')
                            args = ["bhosts", '-o',
                                    'host_name:20 status: max:5 run:5', reserve]

                            self.print_args(args)

                            for line2 in Process(*args).lines():
                                if line2 and 'HOST_NAME' not in line2:
                                    node, status, maxCores, runCores = line2.split()
                                    users = nodes.get(node, {})
                                    if node in json:
                                        json[node]['users'].update(users)
                                    else:
                                        json[node] = {
                                            'status': status,
                                            'max': maxCores,
                                            'run': runCores,
                                            'users': users
                                        }
        return json

    def show_jobs(self, queue=None, user=None):
        def _print_sorted(**kwargs):
            if queue := kwargs.get('queue', None):
                args = ["bqueues", "-l", queue]
                proc = Process(*args, doRaise=False)
                if proc.returncode != 0:
                    return
            users = self.get_users(**kwargs)
            print(Color.bold("\n>>> JOBS: "))
            sorted_users = sorted(users.items(), key=lambda u: len(u[1]), reverse=True)
            print_users(sorted_users)

        if user:
            _print_sorted(queue=None, user=user)
        else:
            queues = self.get_queues(queue)
            for q in queues:
                _print_sorted(queue=q)


