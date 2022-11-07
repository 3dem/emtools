import os


class Path:
    @staticmethod
    def splitall(path):
        return os.path.normpath(path).split(os.path.sep)

