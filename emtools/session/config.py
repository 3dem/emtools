import os
import json

SESSIONS_RAW_FOLDER = os.environ.get('SESSIONS_RAW_FOLDER', '')
SESSIONS_RAW_PATTERN = os.path.join(SESSIONS_RAW_FOLDER,
                                    os.environ.get('SESSIONS_RAW_PATTERN', ''))
SESSIONS_OTF_FOLDER = os.environ.get('SESSIONS_OTF_FOLDER', '')
SESSIONS_CACHE_FOLDER = os.environ.get('SESSIONS_CACHE_FOLDER', '')


def configpath(*paths):
    return os.path.join(SESSIONS_CACHE_FOLDER, 'config', *paths)


def load_users_map():
    with open(configpath('users_map.json')) as f:
        users = json.load(f)

    return users


def load_acquisition():
    """ Load a json file with acquisition information for each scope.
    For example:

    {
        "Krios01": {
            "voltage": 300,
            "magnification": 130000,
            "pixel_size": 0.522,
            "dose": 1.09,
            "cs": 2.7
        },
        "Arctica01": {
            "voltage": 200,
            "magnification": 79000,
            "pixel_size": 0.6485,
            "dose": 1.063,
            "cs": 2.7
        }
    }

    """
    with open(configpath('acquisition.json')) as f:
        acq = json.load(f)

    return acq
