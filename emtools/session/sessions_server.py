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
import sessions_config as sconfig


class SessionsData:
    def __init__(self, **kwargs):
        self.data_folder = sconfig.SESSIONS_DATA_FOLDER
        self.sessions_json_file = os.path.join(self.data_folder,
                                               'sessions.json')
        self.verbose = kwargs.get('verbose', 0)
        self.sessions = OrderedDict()
        self.load()

    def print(self, *args):
        if self.verbose:
            print(*args)

    def session_key(self, s):
        return s['name']

    def load(self):
        """ Load sessions. """
        self.sessions = OrderedDict()
        if os.path.exists(self.sessions_json_file):
            with open(self.sessions_json_file) as f:
                for s in json.load(f):
                    self.sessions[self.session_key(s)] = s

    def save(self):
        with open(self.sessions_json_file, 'w') as f:
            json.dump([s for s in self.sessions.values()], f)

    def update(self, new_sessions):
        for s in new_sessions:
            self.update_session(s)
            self.sessions[self.session_key(s)] = s
        self.save()


class SessionsServer(JsonTCPServer):
    def __init__(self, address):
        JsonTCPServer.__init__(self, address)
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
            k: f"{v[0]} -> {v[1]}" for k, v in self._get_folders().items()
        }
        s['config'] = config
        s['active_sessions'] = [s['name'] for s in self._active_sessions()]
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

    def _active_sessions(self):
        return iter(s for s in self.data.sessions.values()
                    if s.get('status', 'finished') == 'active')

    def _check_updates(self):
        """ Implement this function to check for server updates. """
        print('Updates from Sessions.....')
        for s in self._active_sessions():
            print(f"   Active session: {s['name']}, checking files")
            for root, dirs, files in os.walk(s['raw']['path']):
                for f in files:
                    fn = os.path.join(root, f)
                    if fn not in self._files[s['name']]
                    s = os.stat(fn)
                    fn = os.path.join(root, f)
                    ext = os.path.splitext(f)[1]
                    if ext not in stats:
                        stats[ext] = {'count': 0, 'size': 0}
                    s = stats[ext]
                    s['count'] += 1
                    s['size'] += os.stat(fn).st_size
    def _get_folders(self):
        folders = OrderedDict()
        for f in ['EPU', 'Offload', 'OTF', 'Groups']:
            folder = os.path.join(sconfig.SESSIONS_DATA_FOLDER, 'links', f)
            fpath = os.path.abspath(os.path.realpath(folder))
            folders[f] = (folder, fpath)
        return folders

    def create_session(self, microscope, group, user, label):
        errors = []
        dirs = []
        result = {}
        sessions = self.data.sessions
        try:
            ds = Pretty.date(datetime.now(), format='%Y%m%d')
            pattern = sconfig.SESSIONS_NAME_PATTERN.replace('YYYYMMDD', ds)
            session_name = pattern.format(**locals())

            if session_name in self.data.sessions:
                raise Exception(f'Session {session_name} already exists')

            for k, v in self._get_folders().items():
                folder = v[1]
                session_path = os.path.join(folder, session_name)
                if os.path.exists(session_path):
                    errors.append(f"Session folder {session_path} already exists.")
                dirs.append(session_path)

            if not errors:
                for d in dirs:
                    os.mkdir(d)
            session = {
                'name': session_name,
                'creation': Pretty.now(),
                'status': 'active',
                'raw': {
                    'path': dirs[0],
                    'status': 'active',  # finished
                },
                'offload': {
                    'path': dirs[1],
                    'status': 'receiving'  # finished, delivered, deleted
                },
                'otf': {
                    'path': dirs[2],
                },
                'delivery': {'path': dirs[3]},
            }
            self.data.sessions[session_name] = session
            self.data.save()
        except Exception as e:
            errors.append(f"Exception: {str(e)}")

        return {'errors': errors} if errors else {'session': session}

    def delete_session(self, session_name):
        errors = []
        sessions = self.data.sessions
        try:
            if session_name not in self.data.sessions:
                raise Exception(f'Session {session_name} does not exists')

            for k, v in self._get_folders().items():
                folder = v[1]
                session_path = os.path.join(folder, session_name)
                Process.system(f'rm -rf {session_path}')

            del self.data.sessions[session_name]
            self.data.save()
        except Exception as e:
            errors.append(f"Exception: {str(e)}")

        return {'errors': errors} if errors else {'deleted': session_name}


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
