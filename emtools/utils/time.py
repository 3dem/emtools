
from datetime import datetime

from .pretty import Pretty


class Timer(object):
    """ Simple Timer base in datetime.now and timedelta. """

    def __init__(self, message=""):
        self._message = message
        self.tic()

    def tic(self):
        self._dt = datetime.now()

    def getElapsedTime(self):
        return datetime.now() - self._dt

    def toc(self, message='Elapsed:'):
        print(f"{message} {str(self.getElapsedTime())}")

    def getToc(self):
        return Pretty.delta(self.getElapsedTime())

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.toc(self._message)
