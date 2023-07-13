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

import pyworkflow as pw

from emtools.utils import Color
from .monitors import ProtocolMonitor


class Workflow:
    """ Workflow manager over Scipion project """
    def __init__(self, project):
        self.project = project

    def createProtocol(self, protocolClass, **kwargs):
        """ Create new protocol instances through the project
        and return a newly created protocol of the given class
        Args:
            protocolClass: String or Class to instanciate the protocol
        """
        if isinstance(protocolClass, str):
            parts = protocolClass.split('.')
            domain = pw.Config.getDomain()
            protClass = domain.importFromPlugin('.'.join(parts[:-1]), parts[-1])
            extraKwargs = kwargs.pop('kwargs', {})
            kwargs.update(extraKwargs)

        return self.project.newProtocol(protClass, **kwargs)

    def saveProtocol(self, prot):
        self.project.saveProtocl(prot)

    def launchProtocol(self, prot, wait=False):
        """ Overwrite launchProtocol method.
        Params:
            wait: can be True or False to simply wait or not for the protocol
                to finish. It can be also a dict for waiting for outputs to
                either be created or closed. e.g:
                wait={'outputMicrographs': 'created', 'outputCTF': 'created'}
                wait={'outputParticles': 'closed'}
        """
        label = Color.bold(f"'{prot.getClassName()}' ({prot.getRunName()})")
        print(Color.bold(f">>> Running protocol {label}\n   wait: {wait}"))
        self.project.launchProtocol(prot)

        if wait:
            kwargs = wait if isinstance(wait, dict) else {}
            #prot = self.wait(prot, **kwargs)
            self.wait(prot, **kwargs)

        #return prot

    def saveProtocol(self, prot):
        return self.project.saveProtocol(prot)

    def wait(self, prot, **kwargs):
        pm = ProtocolMonitor(prot)
        pm.wait(**kwargs)
        return self.updateProtocol(prot)

    def updateProtocol(self, prot):
        """ Reload a protocol from db. Return True if it was reloaded. """
        r = self.project._updateProtocol(prot)
        self.project.mapper.commit()
        return r == pw.PROTOCOL_UPDATED
