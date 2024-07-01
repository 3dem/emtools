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

from datetime import datetime

from .pretty import Pretty


class Timer(object):
    """ Simple Timer base in datetime.now and timedelta. """

    def __init__(self, message="Elapsed:"):
        self.message = message
        self.tic()

    def tic(self, msg=None):
        if msg:
            print(msg)
        self._dt = datetime.now()

    def getElapsedTime(self):
        return datetime.now() - self._dt

    def toc(self, message=None, pretty=False):
        print(self.getToc(message=message, pretty=pretty))

    def getToc(self, message=None, pretty=False):
        if message:
            self.message = message

        elapsed = self.getElapsedTime()
        elapsedStr = Pretty.delta(elapsed) if pretty else str(elapsed)

        return f"{self.message} {elapsedStr}"

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.toc(self.message)
