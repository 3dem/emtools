#!/usr/bin/env python

from glob import glob

from emtools.utils import Pretty, Color
from emtools.metadata import StarReader
from .config import *


class SessionsOtf:
    def __init__(self, root=None, verbose=False):
        self.root = root or SESSIONS_OTF_FOLDER
        self.verbose = verbose

    def find_sessions(self):
        sessions = []
        non_sessions = []
        for entry in os.listdir(self.root):
            fn = os.path.join(self.root, entry)
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

    def get_session(self, folder):
        def _path(*paths):
            return os.path.join(folder, *paths)

        # Detect if it is a OTF session by checking 'relion_it_options.py' exists
        it = _path('relion_it_options.py')

        if not os.path.exists(it):
            return None

        stat = os.stat(it)
        gain = _path('gain.mrc')
        gain_real = os.path.abspath(os.path.realpath(gain))

        raw_folder = ''
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
            raw_folder = os.path.dirname(os.path.realpath(frames_folder))
        elif os.path.islink(gain):
            raw_folder = os.path.dirname(gain_real)

        if raw_folder:
            if raw_folder.startswith(SESSIONS_RAW_FOLDER):
                raw_folder = os.path.relpath(raw_folder, SESSIONS_RAW_FOLDER)
            else:
                raw_folder = f"{Color.red('WRONG')} {raw_folder}"

        if not movies_number:
            # Try to find the number of movies from other source
            movies_star = _path('Import', 'job001', 'movies.star')
            if os.path.exists(movies_star):
                reader = StarReader(movies_star)
                table = reader.readTable('movies')
                reader.close()
                movies_number = table.size()

        return {
            'path': os.path.relpath(folder, SESSIONS_OTF_FOLDER),
            'gain': gain_real,
            'exists': os.path.exists(raw_movie),
            'movies': movies_number,
            'data': raw_folder,
            'start': Pretty.timestamp(stat.st_mtime)
        }

    def create(self, input_raw_folder, project_name):
        print(f">>> Creating OTF session from: {input_raw_folder}")
        input_raw_folder = os.path.join(SESSIONS_RAW_FOLDER,
                                        input_raw_folder)
        if not os.path.exists(input_raw_folder):
            raise Exception("Input folder does not exists")

        os.system(f"rm -rf {project_name}")

        # TODO: Validate project name
        def _path(*paths):
            return os.path.join(project_name, *paths)

        os.mkdir(project_name)
        os.symlink(input_raw_folder, _path('data'))

        gain = glob(_path('data', '*gain*.mrc'))[0]
        os.symlink(os.path.relpath(gain, project_name), _path('gain.mrc'))

        relion_it_options = """{
'prep__ctffind__do_phaseshift' : 'False',
'proc__ctffind_mics' : 'Schemes/prep/ctffind/micrographs_ctf.star',
'proc__extract__extract_size' : '416',
'proc__extract__do_fom_threshold' : 'False',
'proc__autopick__nr_mpi' : '4',
'proc__autopick__log_diam_max' : '180.0',
'proc__autopick__topaz_other_args' : '',
'proc__autopick__log_diam_min' : '150.0',
'do_proc' : 'True',
'proc__select_mics__select_maxval' : '6',
'proc__extract__do_rescale' : 'True',
'proc__topaz_model' : '',
'prep__motioncorr__fn_gain_ref' : 'gain.mrc',
'prep__motioncorr__fn_gain_ref' : 'gain.mrc', 
'prep__do_at_most' : '36', 
'prep__importmovies__angpix' : '0.6485', 
'prep__importmovies__kV' : '300.0', 
'prep__importmovies__Cs' : '2.7', 
'prep__importmovies__fn_in_raw' : 'data/Images-Disc1/GridSquare_*/Data/Foil*fractions.tiff'
}
"""
        with open(_path('relion_it_options.py'), 'w') as f:
            f.write(relion_it_options)


class Main:
    @staticmethod
    def add_arguments(parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--list', '-l', action='store_true',
                           help="List all OTF sessions found in "
                                "the OTF folder. ")
        group.add_argument('--create', metavar=('INPUT', 'PROJECT_NAME'), nargs=2,
                           help="Create a new OTF session from the input raw folder. ")
        group.add_argument('--processing', '-u', action='store_true',
                           help="Update the cache with new sessions found"
                                "in the root folder. ")

    @staticmethod
    def run(args):
        so = SessionsOtf(verbose=args.verbose)

        if args.list:
            so.verbose = 0
            sessions = so.find_sessions()
            width = max(len(s['path']) for s in sessions)
            format_str = '{start:10} {movies:>7}  {path:<%d} {data:<}' % width
            sessions.sort(key=lambda s: s['start'])
            for s in sessions:
                s['start'] = s['start'].split()[0]
                if s['exists']:
                    s['start'] = Color.bold(s['start'])
                print(format_str.format(**s))

        if args.create:
            so.create(*args.create)

        else:
            so.verbose = 1
            so.find_sessions()
