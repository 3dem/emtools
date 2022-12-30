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
import threading
from pprint import pprint
from collections import OrderedDict
from datetime import datetime, timedelta

from emtools.utils import Pretty, Process, Path
import sessions_config as sconfig


class SessionsData:
    def __init__(self, **kwargs):
        self.data_folder = sconfig.SESSIONS_DATA_FOLDER
        self.sessions_json_file = os.path.join(self.data_folder,
                                               'sessions.json')
        self.verbose = kwargs.get('verbose', 0)
        self.sessions = OrderedDict()
        self.lock = threading.Lock()
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
            with self.lock:
                with open(self.sessions_json_file) as f:
                    for s in json.load(f):
                        self.sessions[self.session_key(s)] = s

    def save(self):
        with open(self.sessions_json_file, 'w') as f:
            json.dump([s for s in self.sessions.values()], f)

    def update(self, new_sessions):
        with self.lock:
            for s in new_sessions:
                #self.update_session(s)
                self.sessions[self.session_key(s)] = s
            self.save()

    def create_session(self, microscope, group, user, label):
        errors = []
        dirs = []
        result = {}
        try:
            ds = Pretty.date(datetime.now(), format='%Y%m%d')
            pattern = sconfig.SESSIONS_NAME_PATTERN.replace('YYYYMMDD', ds)
            session_name = pattern.format(**locals())

            if session_name in self.sessions:
                raise Exception(f'Session {session_name} already exists')

            for k, v in self.get_folders().items():
                folder = v[1]
                session_path = os.path.join(folder, session_name)
                if os.path.exists(session_path):
                    errors.append(f"Session folder {session_path} already exists.")
                dirs.append(session_path)

            if not errors:
                for d in dirs:
                    os.mkdir(d)
            now = Pretty.now()
            session = {
                'name': session_name,
                'creation': now,
                'updated': now,
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
            self.update([session])
        except Exception as e:
            errors.append(f"Exception: {str(e)}")

        return {'errors': errors} if errors else {'session': session}

    def delete_session(self, session_name):
        errors = []
        try:
            if session_name not in self.sessions:
                raise Exception(f'Session {session_name} does not exists')
            session = self.sessions[session_name]
            for k in ['raw', 'offload', 'otf']:
                Process.system(f"rm -rf {session[k]['path']}")
            with self.lock:
                del self.sessions[session_name]
                self.save()
        except Exception as e:
            errors.append(f"Exception: {str(e)}")

        return {'errors': errors} if errors else {'deleted': session_name}

    def active_sessions(self):
        return iter(s for s in self.sessions.values()
                    if s.get('status', 'finished') == 'active')

    def offload_session_files(self, session):
        """ Move files from the Raw folder to the Offload folder.
        Files will be moved when there has been a time without modification
        (file's timeout).
        """
        src = session['raw']['path']
        dst = session['offload']['path']
        ed = Path.ExtDict()

        now = datetime.now()
        td = timedelta(minutes=1)

        def _updateSessionFiles():
            new_session = dict(session)
            new_session['updated'] = Pretty.now()
            raw = new_session['raw']
            if 'files' in raw:
                ed.update(raw['files'])
            raw['files'] = dict(ed)
            ed.clear()
            self.update([new_session])

        def _moveFile(srcFile, dstFile):
            s = os.stat(srcFile)
            dt = datetime.fromtimestamp(s.st_mtime)
            if now - dt >= td:
                Process.system(f'rsync -ac --remove-source-files {srcFile} {dstFile}')
                ed.register(srcFile, stat=s)
                if len(ed) >= 10:  # update session info more frequently
                    _updateSessionFiles()

        Path.copyDir(src, dst, copyFileFunc=_moveFile)
        if ed:
            _updateSessionFiles()

    def update_active_sessions(self):
        for s in self.active_sessions():
            print(f"   Active session: {s['name']}, checking files")
            self.offload_session_files(s)

    def get_folders(self):
        folders = OrderedDict()
        for f in ['EPU', 'Offload', 'OTF', 'Groups']:
            folder = os.path.join(sconfig.SESSIONS_DATA_FOLDER, 'links', f)
            fpath = os.path.abspath(os.path.realpath(folder))
            folders[f] = (folder, fpath)
        return folders
