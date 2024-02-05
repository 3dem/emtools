#!/usr/bin/env python
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

import sys
import json
import os.path
import argparse
import ast
import time
from collections import OrderedDict
import datetime as dt

from emtools.utils import Process, Color, System, Pipeline
from emtools.metadata import EPU, SqliteFile, StarFile, Table

import pyworkflow as pw
from pyworkflow.project import Project
from pyworkflow.protocol import STATUS_FINISHED
from pwem.objects import SetOfParticles
from emtools.pwx import Workflow


OUT_MOVS = 'outputMovies'
OUT_MICS = 'outputMicrographsDoseWeighted'
OUT_CTFS = 'outputCTF'
OUT_COORD = 'outputCoordinates'
OUT_PART = 'outputParticles'

# Some global workflow parameters
params = {}
OTF_FILE = 'scipion-otf.json'
cwd = os.getcwd()


def _setPointer(pointer, prot, extended):
    pointer.set(prot)
    pointer.setExtended(extended)


def loadGpus():
    # Avoid quadro GPUs
    gpuProc = [g for g in System.gpus() if 'Quadro' not in g['name']]
    ngpu = len(gpuProc)
    half = int(ngpu/2)
    gpus = list(range(ngpu))
    # Take half of gpus for Motioncor and the other half for 2D
    params['mcGpus'] = gpus[:half]
    params['cls2dGpus'] = gpus[half:]


def calculateBoxSize(protCryolo):
    """ Calculate the box size based on the estimate particle size from Cryolo
    and recommend boxsize from Eman's wiki page.
    """
    EMAN_BOXSIZES = [24, 32, 36, 40, 44, 48, 52, 56, 60, 64, 72, 84, 96, 100,
                     104, 112, 120, 128, 132, 140, 168, 180, 192, 196, 208,
                     216, 220, 224, 240, 256, 260, 288, 300, 320, 352, 360,
                     384, 416, 440, 448, 480, 512, 540, 560, 576, 588, 600,
                     630, 640, 648, 672, 686, 700, 720, 750, 756, 768, 784,
                     800, 810, 840, 864, 882, 896, 900, 960, 972, 980, 1000,
                     1008, 1024]

    # Calculate the boxsize based on double of cryolo particle estimation
    # and recommended EMAN's boxsizes for performance
    params['partSizePx'] = protCryolo.boxsize.get()
    params['partSizeA'] = params['partSizePx'] * protCryolo.inputMicrographs.get().getSamplingRate()
    boxSize = max(params['partSizePx'] * 2.5, 100)
    for bs in EMAN_BOXSIZES:
        if bs > boxSize:
            boxSize = bs
            break
    params['boxSize'] = boxSize


def clean_project(workingDir):
    """ Clean possible Scipion project files and directories. """
    for fn in ['logs', 'Logs', 'project.sqlite', 'Runs', 'Tmp', 'Uploads']:
        Process.system(f'rm -rf {os.path.join(workingDir, fn)}')


def create_project(workingDir):
    clean_project(workingDir)
    project = Project(pw.Config.getDomain(), workingDir)
    project.create()

    loadGpus()

    def _path(*p):
        return os.path.join(workingDir, *p)

    scipionOptsFn = _path('scipion_options.json')

    if not os.path.exists(scipionOptsFn):
        raise Exception(f"Missing options file: {scipionOptsFn}")

    with open(scipionOptsFn) as f:
        opts = json.load(f)

    acq = opts['acquisition']
    importOpts = opts['import']
    picking = opts.get('picking', {})

    wf = Workflow(project)

    moviesFolder = importOpts['folder']
    moviesPattern = importOpts['pattern']  # "GridSquare_*/Data/FoilHole_*_fractions.tiff"

    protImport = wf.createProtocol(
        'pwem.protocols.ProtImportMovies',
        objLabel='import movies',
        filesPath=moviesFolder,
        filesPattern=moviesPattern,
        samplingRateMode=0,
        samplingRate=acq['pixel_size'],
        magnification=130000,
        scannedPixelSize=7.0,
        voltage=acq['voltage'],
        sphericalAberration=acq['cs'],
        doseInitial=0.0,
        dosePerFrame=acq['dose'],
        gainFile=importOpts.get("gain", "gain.mrc"),
        dataStreaming=False
    )
    #protImport = wf.launchProtocol(protImport, wait={OUT_MOVS: 1})
    wf.launchProtocol(protImport, wait=True)
    protMc = wf.createProtocol(
        'motioncorr.protocols.ProtMotionCorrTasks',
        objLabel='motioncor',
        patchX=7, patchY=5,
        numberOfThreads=1,
        streamingBatchSize=16,
        gpuList=' '.join(str(g) for g in params['mcGpus'])
    )
    _setPointer(protMc.inputMovies, protImport, 'outputMovies')
    wf.launchProtocol(protMc, wait={OUT_MICS: 8})

    protCTF = wf.createProtocol(
        'cistem.protocols.CistemProtCTFFind',
        objLabel='ctffind4',
        streamingBatchSize=8,
        streamingSleepOnWait=60,
        numberOfThreads=5,
    )
    _setPointer(protCTF.inputMicrographs, protMc, OUT_MICS)
    wf.launchProtocol(protCTF, wait={OUT_CTFS: 16})

    protCryolo = wf.createProtocol(
        'sphire.protocols.SphireProtCRYOLOPicking',
        objLabel='cryolo picking',
        boxSize=0,  # let cryolo estimate the box size
        conservPickVar=0.05,  # less conservative than default 0.3
        useGpu=False,  # use cpu for picking, fast enough
        numCpus=8,
        gpuList='',
        streamingBatchSize=16,
        streamingSleepOnWait=60,
        numberOfThreads=1,
        inputModelFrom=0  # General model (low pass filtered)
    )
    _setPointer(protCryolo.inputMicrographs, protMc, OUT_MICS)
    wf.launchProtocol(protCryolo, wait={OUT_COORD: 100})

    calculateBoxSize(protCryolo)

    protRelionExtract = wf.createProtocol(
        'relion.protocols.ProtRelionExtractParticles',
        objLabel='relion - extract',
        boxSize=params['boxSize'],
        doRescale=True,
        rescaledSize=100,
        doInvert=True,
        doNormalize=True,
        backDiameter=params['partSizeA'],
        numberOfMpi=8,  # 16,
        downsamplingType=0,  # Micrographs same as picking
        streamingBatchSize=16,  # 32,
        streamingSleepOnWait=60,
    )

    _setPointer(protRelionExtract.ctfRelations, protCTF, OUT_CTFS)
    _setPointer(protRelionExtract.inputCoordinates, protCryolo, OUT_COORD)
    # Ensure there are at least some particles
    wf.launchProtocol(protRelionExtract, wait={OUT_PART: 100})


def print_prot(prot, label='Protocol'):
    print(f">>> {label} {prot.getObjId():>6}   {prot.getClassName():<30} {prot.getRunName()}")


def write_config(workingDir):
    """ Write example configuration file. """
    configFn = os.path.join(workingDir, 'scipion_options.json')
    if os.path.exists(configFn):
        raise Exception(f"Config file {configFn} already exists.")

    config = {
        "acquisition": {
            "voltage": "300",
            "magnification": "130000",
            "pixel_size": "0.6485",
            "dose": "1.09",
            "cs": "2.7"
        },
        "import": {
            "folder": "data/Images-Disc1",
            "pattern": "GridSquare_*/Data/FoilHole_*_fractions.tiff",
            "gain": "data/gain.mrc"
        }
    }

    with open(configFn, 'w') as f:
        json.dump(config, f, indent=4)

    print(f"Written config file: {Color.bold(configFn)}.")


def main():
    p = argparse.ArgumentParser(prog='scipion-apo')
    g = p.add_mutually_exclusive_group()

    g.add_argument('--create', action='store_true',
                       help="Create a new Scipion project in the working "
                            "directory. This will overwrite any existing "
                            "'scipion' folder there.")
    g.add_argument('--test', action='store_true',
                   help="Some test code")
    g.add_argument('--clean', action="store_true",
                   help="Clean Scipion project files/folders.")
    g.add_argument('--write_config', action="store_true")

    args = p.parse_args()

    if args.create:
        create_project(cwd)
    elif args.test:
        project = Project(pw.Config.getDomain(), cwd)
        project.load()
        for prot in project.getRuns():
            print_prot(prot)
        pass  # debugging/testing code
    elif args.clean:
        clean_project(cwd)
    elif args.write_config:
        write_config(cwd)
    else:  # by default open the GUI
        from pyworkflow.gui.project import ProjectWindow
        ProjectWindow(cwd).show()


if __name__ == '__main__':
    main()
