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

import os
import json
from pprint import pprint
from collections import OrderedDict
from datetime import datetime

from emtools.utils import Pretty, Process, JsonTCPServer, JsonTCPClient
from .sessions_data import SessionsData
import sessions_config as sconfig


class SessionsServer(JsonTCPServer):
    def __init__(self, address):
        JsonTCPServer.__init__(self, address)
        self._refresh = 30
        self.data = SessionsData()
        self._files = {}

    def status(self):
        s = JsonTCPServer.status(self)
        s['sessions'] = len(self.data.sessions)
        config = {}
        for k in dir(sconfig):
            if k.startswith('SESSIONS_'):
                config[k] = getattr(sconfig, k)
        config['folders'] = {
            k: f"{v[0]} -> {v[1]}" for k, v in self.data.get_folders().items()
        }
        s['config'] = config
        s['active_sessions'] = [s['name'] for s in self.data.active_sessions()]
        return s

    def list(self, session=''):
        sessions = []
        for k, s in self.data.sessions.items():
            r = s['raw']
            if 'start' in r or True:
                sessions.append({
                    #'start': r['start'],
                    'name': s['name']
                    #'path': r['path']
                })
        return {'sessions': sessions}

    def session_info(self, session_key):
        if session_key in self.data.sessions:
            return self.data.sessions[session_key]
        else:
            return {'errors': [f'Session {session_key} does not exists.']}

    def _check_updates(self):
        """ Implement this function to check for server updates. """
        print('Updates from Sessions.....')
        self.data.update_active_sessions()

    def create_session(self, microscope, group, user, label):
        return self.data.create_session(microscope, group, user, label)

    def delete_session(self, session_name):
        return self.data.delete_session(session_name)


class SessionsClient(JsonTCPClient):
    pass


class Main:
    @staticmethod
    def add_arguments(parser):
        group = parser.add_mutually_exclusive_group()

        group.add_argument('--start_server', action='store_true',
                           help="Start the sessions server.")
        group.add_argument('--status', '-s', action='store_true',
                           help="Query sessions' server status.")
        group.add_argument('--list', '-l', action='store_true',
                           help="List all OTF sessions stored in the cache. ")
        group.add_argument('--info', '-i',
                           help="Get info about this session.")
        group.add_argument('--create', '-c', nargs=4,
                           metavar=('MIC', 'GROUP', 'USER', 'LABEL'),
                           help="Create a new session.")
        group.add_argument('--delete', '-d',
                           metavar='SESSION_NAME', help="Delete session.")

    @staticmethod
    def run(args):
        address = sconfig.SESSIONS_SERVER_ADDRESS

        if args.start_server:
            with SessionsServer(address) as server:
                server.serve_forever()
        else:
            client = SessionsClient(address, verbose=False)
            if not client.test():
                raise Exception(f"Server not listening on {address}")

            if args.status:
                status = client.call('status')['result']
                pprint(status)
            elif args.list:
                sessions = client.call('list')['result']['sessions']
                for s in sessions:
                    print(s)
                print(f"Total: {len(sessions)}")
            elif args.info:
                session = client.call('session_info', args.info)['result']
                pprint(session)
            elif args.create:
                session = client.call('create_session', *args.create)['result']
                pprint(session)
            elif args.delete:
                session = client.call('delete_session', args.delete)['result']
                pprint(session)
            else:
                print("Nothing to do for now")
