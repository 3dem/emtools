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
import time
from datetime import datetime
from collections import OrderedDict

import pyworkflow.protocol as pwprot


class ProtocolMonitor:
    """ Class to monitor protocol progress. """
    def __init__(self, protocol):
        self._prot = protocol
        self._lastUpdate = None

    def update(self):
        """ Load the protocol from the database if necessary.
        Returns:
            True if the protocol was updated, False otherwise.
             If updated, the protocol will contain new values.
        """
        updated = False
        p = self._prot  # shortcut
        projPath, dbPath = p.getProject().path, p.getDbPath()
        fullPath = os.path.join(projPath, dbPath)
        now = datetime.now()
        mTime = datetime.fromtimestamp(os.path.getmtime(fullPath))
        # Avoid reading the protocol db if it has not changed
        if not self._lastUpdate or mTime > self._lastUpdate:
            p = pwprot.getProtocolFromDb(projPath, dbPath, p.getObjId())
            # Close DB connections
            p.getProject().closeMapper()
            p.closeMappers()
            updated = True
            self._prot = p
            self._lastUpdate = now
        return updated

    def wait(self, sleep=1, **kwargs):
        """ Wait until internal protocol meets certain conditions. Internal
        protocol will be updated while checking for conditions.
        If the protocol status is 'Failed' or 'Aborted' the wait function will
        return.
        Params:
            sleep: time in seconds to sleep between updates.
            **kwargs: dictionary with conditions. e.g:
                status='finished' or
                outputMicrographs='created', outputCTF='created' or
                outputParticles='closed'
        Returns:
            None, internal protocol will be updated after the wait and
            conditions are satisfied.
        """
        # Condition on protocol status
        status = kwargs.pop('status', None)

        def _cond(p, k, v):
            output = getattr(p, k, None)
            if output is not None:
                if v == 'created':
                    return True
                elif v == 'closed':
                    return output.isClosed()
                else:
                    return output.getSize() >= v
            return False

        def _done(p):
            return p.status in [pwprot.STATUS_FAILED,
                                pwprot.STATUS_FINISHED,
                                pwprot.STATUS_ABORTED]

        def _ready(p):
            if _done(p) or (status and p.status == status):
                return True

            if kwargs:
                return all(_cond(p, k, v) for k, v in kwargs.items())

            return False

        while not _ready(self._prot):
            while not self.update():
                time.sleep(sleep)

    @property
    def protocol(self):
        return self._prot

    @property
    def lastUpdate(self):
        return self._lastUpdate


class SetDict(OrderedDict):
    """ Ordered Dict subclass to keep track of Scipion sets.
    It provides a useful 'update' method to check for new items.
    """
    def __init__(self, SetClass, filename, *args, **kwargs):
        OrderedDict.__init__(self, *args, **kwargs)
        self._SetClass = SetClass
        self._filename = filename
        self.lastUpdate = None
        self.streamClosed = None

    def update(self):
        newItems = []
        now = datetime.now()
        mTime = datetime.fromtimestamp(os.path.getmtime(self._filename))

        if not self.lastUpdate or mTime > self.lastUpdate:
            setInstance = self._SetClass(filename=self._filename)
            setInstance.loadAllProperties()
            for item in setInstance:
                iid = item.getObjId()
                if iid not in self:
                    itemClone = item.clone()
                    newItems.append(itemClone)
                    self[iid] = itemClone
            self.streamClosed = setInstance.isStreamClosed()
            setInstance.close()

        self.lastUpdate = now
        return newItems