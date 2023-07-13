#!/usr/bin/env python

# This script reads the optics group from a movies star file and change it
# accordingly in the particles starfile and writes a new particles star file
# with the updated values

import sys
import os

from emtools.utils import Timer, Color
from emtools.metadata import StarFile, Table

# Input star file with particles that we want to update the optics group
particlesFn = sys.argv[1]

# Input movies/micrographs file with optics group
moviesFn = sys.argv[2]

tm = Timer()


# The following two functions should return the same value for
# matching between the particles micrograph and the movies's micrograph
# The current implementation might need to changed for other star files
def micFromMovie(row):
    return os.path.basename(row.rlnMicrographMovieName)


def micFromParticle(row):
    return os.path.basename(row.rlnMicrographName).replace('.mrc', '.tiff')


# Let's create a dictionary to match movies from the particles
# star file to the movies star file and retrieve the optics group
with StarFile(moviesFn) as sf:

    opticGroups = {micFromMovie(row): row.rlnOpticsGroup
                   for row in sf.iterTable('movies')}
    print(f"Optic Groups: {len(opticGroups)}")

# Iterate over particles and find their corresponding optic group
with StarFile(particlesFn) as sf:
    outFn = particlesFn.replace('.star', '_changed_optics.star')
    opticTable = sf.getTable('optics')
    ogRow = opticTable[0]

    t = sf.getTableInfo('particles')
    with StarFile(outFn, 'w') as out:
        newOpticTable = Table(opticTable.getColumns())
        addedGroups = set()
        for og in opticGroups.values():
            if og not in addedGroups:
                ogName = 'opticsGroup%03d' % og
                newOpticTable.addRow(ogRow._replace(rlnOpticsGroup=og,
                                                    rlnOpticsGroupName=ogName))
                addedGroups.add(og)
        out.writeTable('optics', newOpticTable)
        out.writeHeader('particles', t)
        for row in sf.iterTable('particles'):
            mic = micFromParticle(row)
            og = opticGroups.get(mic, None)
            if og:
                newRow = row._replace(rlnOpticsGroup=og)
                out.writeRow(newRow)
            else:
                print(f"Missing optics group for particle: "
                      f"{Color.red(row.rlnImageName)}")

tm.toc()






