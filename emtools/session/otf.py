#!/usr/bin/env python

from glob import glob
import configparser
import ast
from pprint import pprint

from emtools.utils import Pretty, Color, Path
from emtools.metadata import StarFile

from .config import *
from .base import SessionsBase
from .raw import SessionsRaw


class SessionsOtf(SessionsBase):
    def __init__(self, **kwargs):
        self.cache_file = 'otf.json'
        self.root = kwargs.get('root', SESSIONS_OTF_FOLDER)
        SessionsBase.__init__(self, **kwargs)

    def find_sessions(self, only_new=True):
        sessions = []
        non_sessions = []
        for entry in os.listdir(self.root):
            fn = os.path.join(self.root, entry)

            if fn in self.sessions and only_new:
                continue

            s = self.get_session(fn)
            if s:
                sessions.append(s)
            else:
                non_sessions.append(fn)

        if self.verbose:
            print(f"\nOTF folder: {Color.bold(SESSIONS_OTF_FOLDER)}/")
            print(f"Total sessions: {Color.bold(len(sessions))}")
            print(Color.red("\n>>> Non-sessions: "))
            for ns in non_sessions:
                print(f"   {ns}")

        return sessions

    def __find_session_raw(self, session_folder):

        pass

    def get_session(self, folder):
        def _path(*paths):
            return os.path.join(folder, *paths)

        # Detect if it is a OTF session by checking 'relion_it_options.py' exists
        it = _path('relion_it_options.py')

        if not os.path.exists(it):
            return None

        stats = acquisition = {}
        with open(it) as f:
            opts = ast.literal_eval(f.read())
            def _get(k):
                v = opts[k]
                if v == 'True':
                    return True
                elif v == 'False':
                    return False
                else:
                    return v
            acquisition = {
                'voltage': _get('prep__importmovies__kV'),
                'cs': _get('prep__importmovies__Cs'),
                'phasePlate': _get('prep__ctffind__do_phaseshift'),
                'detector': None,
                'detectorMode': None,
                'pixelSize': _get('prep__importmovies__angpix'),
                'dosePerFrame': _get('prep__motioncorr__dose_per_frame'),
                'totalDose': None,
                'exposureTime': None,
                'numOfFrames': None,
            }
            stats = {
                'numOfMovies': 0,
                'ptclSizeMin': _get('proc__autopick__log_diam_min'),
                'ptclSizeMax': _get('proc__autopick__log_diam_max')
            }

        gain = _path('gain.mrc')
        gain_real = os.path.abspath(os.path.realpath(gain))
        user = microscope = group = raw_folder = ''
        raw_error = ''
        raw_movie = ''
        movies_number = 0
        frames_folder = _path('Frames')

        if os.path.exists(frames_folder):
            movies = os.listdir(frames_folder)
            if movies:
                first_frame = _path('Frames', movies[0])
                raw_movie = os.path.abspath(os.path.realpath(first_frame))
                raw_folder = raw_movie.split('Images-Disc')[0]
                movies_number = len(movies)
        elif os.path.islink(frames_folder):
            raw_folder = os.path.realpath(frames_folder)
        elif os.path.islink(gain):
            raw_folder = gain_real

        if raw_folder:
            try:
                sr = SessionsRaw(verbose=0)
                info = sr.get_info(raw_folder)
                raw_folder = info['new_raw_folder']
            except Exception as e:
                raw_error = str(e)
        else:
            raw_error = "Can't guess RAW folder"

        if not movies_number:
            # Try to find the number of movies from other source
            movies_star = _path('Import', 'job001', 'movies.star')
            if os.path.exists(movies_star):
                reader = StarFile(movies_star)
                table = reader.readTable('movies')
                reader.close()
                movies_number = table.size()

        mics = _path('MotionCorr', 'job002', 'corrected_micrographs.star')

        stats['numOfMovies'] = movies_number

        return {
            'path': folder,
            'gain': gain_real,
            'exists': os.path.exists(raw_movie),
            'movies': movies_number,
            'user': user,
            'microscope': microscope,
            'group': group,
            'data': raw_folder,
            'raw_error': raw_error,
            'start': Pretty.modified(it),
            'end': Pretty.modified(mics),
            'acquisition': acquisition,
            'stats': stats
        }

    def update_session(self, s):  # Not used now
        pass

    def print_sessions(self, sessions=None):
        sessions = sessions or self.sessions.values()
        if not sessions:
            print("\n>>> No OTF sessions. ")
            return
        sr = SessionsRaw()
        width = max(len(s['path']) for s in sessions) - len(SESSIONS_OTF_FOLDER)
        format_str = '{range:20} {movies:>7}  {path:<%d}  {user:<15} {data:<}' % width
        for session in sorted(sessions, key=lambda s: s['start']):
            s = dict(session)
            s['path'] = os.path.relpath(s['path'], SESSIONS_OTF_FOLDER)
            s['start'] = s['start'].split()[0]
            if s['data'] in sr.sessions:
                s['start'] = Color.bold(s['start'])
            if s['raw_error']:
                s['data'] = f"{Color.red('Error: ' + s['raw_error'])} -> {s['data']}"
            else:
                s['data'] = os.path.relpath(s['data'], SESSIONS_RAW_FOLDER)
            end = s['end'].split()[0] if s['end'] else 'None'
            s['range'] = '%s - %s' % (s['start'], end)
            print(format_str.format(**s))

    def create(self, input_raw_folder, project_name):
        print(f">>> Creating OTF session from: {input_raw_folder}")
        input_raw_folder = os.path.join(SESSIONS_RAW_FOLDER,
                                        input_raw_folder)
        if not os.path.exists(input_raw_folder):
            raise Exception("Input folder does not exists")

        raw_session = {'path': input_raw_folder}
        sr = SessionsRaw(verbose=0)
        sr.update_session(raw_session)
        info = sr.get_info(input_raw_folder)

        date_ts = raw_session['first_movie_creation']
        date_prefix = date_ts.split()[0].replace('-', '')
        otf_pattern = "{}_{microscope}_{group}_{user}_{}"
        otf_folder = otf_pattern.format(date_prefix, project_name, **info)
        os.system(f"rm -rf {otf_folder}")

        def _path(*paths):
            return os.path.join(otf_folder, *paths)

        os.mkdir(otf_folder)
        os.symlink(input_raw_folder, _path('data'))

        gain = glob(_path('data', '*gain*.mrc'))[0]
        os.symlink(os.path.relpath(gain, otf_folder), _path('gain.mrc'))

        # Create a general ini file with config/information of the session
        acquisition = load_acquisition()
        mic = acquisition[info['microscope']]
        config = configparser.ConfigParser()

        config['GENERAL'] = {
            'group': info['group'],
            'user': info['user'],
            'microscope': info['microscope'],
            'raw_data': input_raw_folder
        }

        config['ACQUISITION'] = mic

        config['PREPROCESSING'] = {
            'images': 'data/Images-Disc1/GridSquare_*/Data/Foil*fractions.tiff',
            'software': 'None',  # or Relion or Scipion
        }

        with open(_path('README.ini'), 'w') as configfile:
            config.write(configfile)


class Main:
    @staticmethod
    def add_arguments(parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('session_path', nargs='?',
                           help="Optional session path to inspect")
        group.add_argument('--list', '-l', action='store_true',
                           help="List all OTF sessions stored in the cache. ")
        group.add_argument('--discover', '-d', action='store_true',
                           help="Discover new OTF sessions from the "
                                "the OTF folder. ")
        group.add_argument('--update', '-u', action='store_true',
                           help="Update the cache with new sessions found"
                                "in the root folder. ")
        group.add_argument('--create', metavar=('INPUT', 'PROJECT_NAME'), nargs=2,
                           help="Create a new OTF session from the input raw folder. ")
        group.add_argument('--processing', '-p', action='store_true',
                           help="Update the cache with new sessions found"
                                "in the root folder. ")

        group.add_argument('--print_users', action='store_true',
                           help="Print information about the users found"
                                "in the OTF sessions. ")

    @staticmethod
    def run(args):
        so = SessionsOtf(verbose=args.verbose)

        if args.session_path:
            path = os.path.join(SESSIONS_OTF_FOLDER, args.session_path)
            s = so.sessions.get(path, {})
            print("\n>>> Session: ", Color.bold(args.session_path))
            pprint(s)

        elif args.list:
            so.print_sessions()

        elif args.discover or args.update:
            sessions = so.find_sessions()

            if args.update:
                print(">>> Updating cache...")
                so.update(sessions)

            so.print_sessions(sessions)

        elif args.print_users:
            users = {}
            sessions = so.find_sessions()

            for s in sessions:
                u = s['user']

                if not u:
                    continue

                if u not in users:
                    users[u] = {'sessions': 0, 'group': s['group']}

                user = users[u]
                #user['sessions'] += 1

            user_list = sorted(users.items(), key=lambda item: item[1]['group'])
            users_map = load_users_map()

            for k, v in user_list:
                email = users_map[k]['email'] if k in users_map else ''
                user = k if email else Color.red(k)
                print(f"{user:<15} {email:<35} {v['group']:<15}")

        elif args.create:
            so.create(*args.create)

        elif args.processing:
            pass

        else:
            so.verbose = 1
            so.find_sessions()
