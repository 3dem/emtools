import os
import json

SESSIONS_RAW_FOLDER = os.environ['SESSIONS_RAW_FOLDER']
SESSIONS_RAW_PATTERN = os.path.join(SESSIONS_RAW_FOLDER,
                                    os.environ['SESSIONS_RAW_PATTERN'])
SESSIONS_OTF_FOLDER = os.environ['SESSIONS_OTF_FOLDER']
SESSIONS_CACHE_FOLDER = os.environ['SESSIONS_CACHE_FOLDER']


def load_users_map():
    users = {}
    with open(os.path.join(SESSIONS_CACHE_FOLDER, 'users_map.json')) as f:
        users = json.load(f)

    return users
