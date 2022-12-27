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

from glob import glob
import configparser
import ast
from pprint import pprint
from collections import OrderedDict

from emtools.utils import Pretty, Color, JsonTCPServer, JsonTCPClient

from .config import *
from .base import SessionsBase


class SessionsData(SessionsBase):
    def __init__(self, **kwargs):
        self.cache_file = 'sessions.json'
        self.root = kwargs.get('root', SESSIONS_OTF_FOLDER)
        SessionsBase.__init__(self, **kwargs)

    def find_sessions(self, only_new=True):
        sessions = []
        return sessions

    def session_key(self, s):
        return os.path.basename(s['raw']['path'])

    def __find_session_raw(self, session_folder):

        pass

    def get_session(self, folder):
        pass

    def update_session(self, s):  # Not used now
        pass


class SessionsServer(JsonTCPServer):
    def __init__(self, address):
        JsonTCPServer.__init__(self, address)
        self.data = SessionsData()

    def list(self, session=''):
        sessions = []
        for k, s in self.data.sessions.items():
            r = s['raw']
            if 'start' in r or True:
                sessions.append({
                    #'start': r['start'],
                    'key': k,
                    #'path': r['path']
                })
        return {'sessions': sessions}


class SessionsClient(JsonTCPClient):
    pass


class Main:
    @staticmethod
    def add_arguments(parser):
        group = parser.add_mutually_exclusive_group()

        group.add_argument('--start_server', '-d', action='store_true',
                           help="Start the sessions server.")
        group.add_argument('--status', '-s', action='store_true',
                           help="Query sessions' server status.")
        group.add_argument('--list', '-l', action='store_true',
                           help="List all OTF sessions stored in the cache. ")

    @staticmethod
    def run(args):
        address = sessions_config.SESSIONS_SERVER_ADDRESS

        if args.start_server:
            with SessionsServer(address) as server:
                server.serve_forever()
        else:
            client = SessionsClient(address, verbose=False)
            if not client.test():
                raise Exception(f"Server not listening on {address}")

            if args.status:
                client.call('status')
            elif args.list:
                sessions = client.call('list')['result']['sessions']
                for s in sessions:
                    print(s['key'])
                print(f"Total: {len(sessions)}")
            else:
                print("Nothing to do for now")
