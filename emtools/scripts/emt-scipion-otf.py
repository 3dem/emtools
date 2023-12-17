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


def load_otf():
    otf = {'2d': {}}
    if os.path.exists(OTF_FILE):
        with open(OTF_FILE) as f:
            otf = json.load(f)

    return otf


def save_otf(otf):
    with open(OTF_FILE, 'w') as f:
        json.dump(otf, f, indent=4)


def run2DPipeline(wf, protExtract):
    print(f"\n>>> Running 2D pipeline: input extract "
          f"{Color.bold(protExtract.getRunName())}")

    otf = load_otf()

    def _createBatch2D(gridsquare, subsetParts):
        rangeStr = f"{subsetParts[0].getObjId()} - {subsetParts[-1].getObjId()}"
        print(f"Creating subset with range: {rangeStr}")
        protSubset = wf.createProtocol(
            'pwem.protocols.ProtUserSubSet',
            objLabel=f'subset: {gridsquare} : {rangeStr}',
        )
        _setPointer(protSubset.inputObject, protExtract, OUT_PART)
        wf.saveProtocol(protSubset)
        protSubset.makePathsAndClean()
        # Create subset particles as output for the protocol
        inputParticles = protExtract.outputParticles
        outputParticles = protSubset._createSetOfParticles()
        outputParticles.copyInfo(inputParticles)
        for particle in subsetParts:
            outputParticles.append(particle)
        protSubset._defineOutputs(outputParticles=outputParticles)
        protSubset._defineTransformRelation(inputParticles, outputParticles)
        protSubset.setStatus(STATUS_FINISHED)
        wf.project._storeProtocol(protSubset)

        protRelion2D = wf.createProtocol(
            'relion.protocols.ProtRelionClassify2D',
            objLabel=f'relion2d: {gridsquare}',
            maskDiameterA=round(params['partSizeA'] * 1.5),
            numberOfClasses=200,
            extraParams='--maxsig 50',
            pooledParticles=50,
            doGpu=True,
            gpusToUse=','.join(str(g) for g in params['cls2dGpus']),
            numberOfThreads=32,
            numberOfMpi=1,
            allParticlesRam=True,
            useGradientAlg=True,
        )

        _setPointer(protRelion2D.inputParticles, protSubset, OUT_PART)
        wf.saveProtocol(protRelion2D)
        otf['2d'][gridsquare] = {
            'runId': protRelion2D.getObjId(),
            'runName': protRelion2D.getRunName(),
            'runDir': protRelion2D.getWorkingDir()
        }
        save_otf(otf)

        return {'gs': gridsquare, 'prot': protRelion2D}

    def _generate2D():
        """ Generated subset of 2D from the outputParticles from extract protocol.
        Subsets will be created based on the GridSquare of the micrographs. """
        lastParticleIndex = 0
        lastGs = None
        # Classify in batches
        lastMt = 0
        extractSqliteFn = protExtract.outputParticles.getFileName()
        tmpSqliteFn = '/tmp/particles.sqlite'

        while True:
            if lastGs:  # Not the first time, let's wait
                print("Sleeping...")
                time.sleep(30)  # wait for 5 minutes before checking for new jobs

            print("Wake up!!!")
            mt = os.path.getmtime(extractSqliteFn)
            if mt > lastMt:
                # Let's iterate over the particles to check if there is a
                # new GridSquare and launch a subset and 2D classification job
                # but Let's make a backup of the input particles to avoid DataBase
                # locked error from Sqlite when much concurrency
                print("Copying database....")
                Process.system(f'rm -rf {tmpSqliteFn}')
                SqliteFile.copyDb(extractSqliteFn, tmpSqliteFn, tries=10, wait=30)
                print("Copy done!")

            parts = SetOfParticles(filename=tmpSqliteFn)
            subsetParts = []

            md = dt.datetime.fromtimestamp(mt)
            td = dt.datetime.now() - md
            minutes = td.days * 1440 + td.seconds // 60
            print(f"Total particles: {parts.getSize()}, updated: {md} ({minutes} minutes ago)")

            newGrid = False

            # Find if there is a new subset of particles to launch a new 2D batch
            for i, p in enumerate(parts.iterItems()):
                if i < lastParticleIndex:
                    continue

                micName = p.getCoordinate().getMicName()
                loc = EPU.get_movie_location(micName)

                if loc['gs'] != lastGs:  # We found a new GridSquare

                    oldLastGs = lastGs
                    lastGs = loc['gs']
                    if oldLastGs:
                        newGrid = True
                        break

                subsetParts.append(p.clone())

            launchGs = None
            nParts = len(subsetParts)
            if newGrid:
                launchGs = oldLastGs
                print(f"Found new GS {lastGs}, old one: {oldLastGs}")
            elif td.days or td.seconds > 3600:  # There is some time with no new particles, 1h
                print(f"Some time without particles change. ")
                launchGs = lastGs

            if launchGs and nParts > 1:
                print(f"Launching 2D batch for GS: {launchGs} with "
                      f"{nParts} particles, lastParticleIndex: {lastParticleIndex}")
                yield _createBatch2D(launchGs, subsetParts)
                write_stars(cwd)
                lastParticleIndex = i
            else:
                if td.days or td.seconds > 18000:  # There is some time with no new particles, 5h
                    print("Not much to do, just quitting 2D batch generation")
                    break

            lastMt = mt


    def _run2D(batch):
        protRelion2D = batch['prot']
        wf.launchProtocol(protRelion2D, wait=True)

        protRelion2DSelect = wf.createProtocol(
            'relion.protocols.ProtRelionSelectClasses2D',
            objLabel=f"select 2d - {batch['gs']}",
            minThreshold=0.05,
            minResolution=30.0,
        )

        protRelion2DSelect.inputProtocol.set(protRelion2D)
        wf.launchProtocol(protRelion2DSelect, wait=True)

    ppl = Pipeline()
    g = ppl.addGenerator(_generate2D)
    ppl.addProcessor(g.outputQueue, _run2D)
    ppl.run()


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

    """
        {"acquisition": {"voltage": 200, "magnification": 79000, "pixel_size": 1.044, "dose": 1.063, "cs": 2.7}}
    """

    scipionOptsFn = _path('scipion_otf_options.json')
    relionOptsFn = _path('relion_it_options.py')

    if os.path.exists(scipionOptsFn):
        with open(scipionOptsFn) as f:
            opts = json.load(f)

    elif os.path.exists(relionOptsFn):
        with open(_path('relion_it_options.py')) as f:
            relionOpts = OrderedDict(ast.literal_eval(f.read()))
            opts = {'acquisition': {
                'voltage': relionOpts['prep__importmovies__kV'],
                'pixel_size': relionOpts['prep__importmovies__angpix'],
                'cs': relionOpts['prep__importmovies__Cs'],
                'magnification': 130000,
                'dose': relionOpts['prep__motioncorr__dose_per_frame']
            }}

    acq = opts['acquisition']
    picking = opts.get('picking', {})

    wf = Workflow(project)

    moviesFolder = _path('data', 'Images-Disc1')
    moviesPattern = "GridSquare_*/Data/FoilHole_*_fractions.tiff"

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
        gainFile="gain.mrc",
        dataStreaming=True
    )
    #protImport = wf.launchProtocol(protImport, wait={OUT_MOVS: 1})
    wf.launchProtocol(protImport, wait={OUT_MOVS: 1})
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

    protCryoloImport = None
    cryoloInputModelFrom = 0  # General model (low pass filtered)
    if 'cryolo_model' in picking:
        protCryoloImport = wf.createProtocol(
            'sphire.protocols.SphireProtCryoloImport',
            objLabel='import cryolo model',
            modelPath=picking['cryolo_model']
        )
        wf.launchProtocol(protCryoloImport, wait=True)
        cryoloInputModelFrom = 2  # Other

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
        inputModelFrom=cryoloInputModelFrom
    )
    _setPointer(protCryolo.inputMicrographs, protMc, OUT_MICS)

    if protCryoloImport:
        _setPointer(protCryolo.inputModel, protCryoloImport, 'outputModel')

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
        numberOfMpi=8,#16,
        downsamplingType=0,  # Micrographs same as picking
        streamingBatchSize=16, #32,
        streamingSleepOnWait=60,
    )

    _setPointer(protRelionExtract.ctfRelations, protCTF, OUT_CTFS)
    _setPointer(protRelionExtract.inputCoordinates, protCryolo, OUT_COORD)
    # Ensure there are at least some particles
    wf.launchProtocol(protRelionExtract, wait={OUT_PART: 100})
    run2DPipeline(wf, protRelionExtract)


def continue_project(workingDir):
    print(f"Loading project from {workingDir}")
    project = Project(pw.Config.getDomain(), workingDir)
    project.load()
    wf = Workflow(project)
    loadGpus()

    protExtract = protCryolo = None

    for run in project.getRuns():
        clsName = run.getClassName()
        print(f"Run {run.getObjId()}: {clsName}")
        if clsName == 'ProtRelionExtractParticles':
            protExtract = run
        elif clsName == 'SphireProtCRYOLOPicking':
            protCryolo = run

    if not protExtract.isActive():
        print("Re-running extract protocol...")
        wf.launchProtocol(protExtract, wait={OUT_PART: 100})

    calculateBoxSize(protCryolo)

    run2DPipeline(wf, protExtract)


def restart(workingDir, ids):
    """ Restart one or more protocols. """
    print(f"To relaunch {ids}")
    project = Project(pw.Config.getDomain(), workingDir)
    project.load()

    all_protocols = [2, 88, 198, 262, 318]

    for protId in all_protocols:
        prot = project.getProtocol(protId)
        clsName = prot.getClassName()
        print(f"- {prot.getObjId()}: {clsName}")
        if prot.getObjId() in ids:
            print("\t * Stopping...")
            project.stopProtocol(prot)
            print("\t * Re-running...")
            project.launchProtocol(prot, force=True)
            time.sleep(30)


def restart_rankers(workingDir):
    """ Restart one or more protocols. """
    print(f"Checking failed jobs")
    project = Project(pw.Config.getDomain(), workingDir)
    project.load()
    wf = Workflow(project)

    for prot in project.getRuns():
        if prot.isFailed():
            clsName = prot.getClassName()
            print(f"- {prot.getObjId()}: {prot.getRunName()} ({clsName})")
            if clsName == 'ProtRelionSelectClasses2D':
                print("   Re-launching...")
                wf.launchProtocol(prot, wait=True)
                print("\r     Done!")


def write_micrographs_star(micStarFn, ctfs):
    firstCtf = ctfs.getFirstItem()
    firstMic = firstCtf.getMicrograph()
    # firstCtf.printAll()
    acq = firstMic.getAcquisition()

    with StarFile(micStarFn, 'w') as sf:
        optics = Table(['rlnOpticsGroupName',
                        'rlnOpticsGroup',
                        'rlnMicrographOriginalPixelSize',
                        'rlnVoltage',
                        'rlnSphericalAberration',
                        'rlnAmplitudeContrast',
                        'rlnMicrographPixelSize'])
        ps = firstMic.getSamplingRate()
        op = 1
        opName = f"opticsGroup{op}"
        optics.addRowValues(opName, op, ps,
                            acq.getVoltage(),
                            acq.getSphericalAberration(),
                            acq.getAmplitudeContrast(),
                            ps)

        sf.writeLine("# version 30001")
        sf.writeTable('optics', optics)

        mics = Table(['rlnMicrographName',
                      'rlnOpticsGroup',
                      'rlnCtfImage',
                      'rlnDefocusU',
                      'rlnDefocusV',
                      'rlnCtfAstigmatism',
                      'rlnDefocusAngle',
                      'rlnCtfFigureOfMerit',
                      'rlnCtfMaxResolution',
                      'rlnMicrographMovieName'])
        sf.writeLine("# version 30001")
        sf.writeHeader('micrographs', mics)

        for ctf in ctfs:
            mic = ctf.getMicrograph()
            u, v, a = ctf.getDefocus()
            micName = mic.getMicName()
            movName = os.path.join('data', 'Images-Disc1',
                                   micName.replace('_Data_FoilHole_',
                                                   '/Data/FoilHole_'))
            row = mics.Row(mic.getFileName(), op,
                           ctf.getPsdFile(),
                           u, v, abs(u - v), a,
                           ctf.getFitQuality(),
                           ctf.getResolution(),
                           movName)

            sf.writeRow(row)


def write_coordinates(micStarFn, prot):
    coords = prot.outputCoordinates
    outputCoords = 'Coordinates'
    Process.system(f'rm -rf {outputCoords} && mkdir {outputCoords}')
    coordsMicTable = Table(['rlnMicrographName', 'rlnMicrographCoordinates'])
    coordsTable = Table(['rlnCoordinateX', 'rlnCoordinateY'])
    micIds = set()
    micDict = {mic.getObjId(): mic.getFileName()
               for mic in prot.getInputMicrographs()}

    sf = None

    for coord in coords.iterItems(orderBy='_micId', direction='ASC'):
        micId = coord.getMicId()
        if micId not in micIds:
            micIds.add(micId)
            micFn = micDict[micId]
            micBase = os.path.basename(micFn).replace('.mrc', '')
            micCoords = f"{outputCoords}/{micBase}_coordinates.star"
            coordsMicTable.addRowValues(micFn, micCoords)

            if sf:
                sf.close()
            sf = StarFile(micCoords, 'w')
            sf.writeLine('# version 30001')
            sf.writeHeader('', coordsTable)
        sf.writeRow(coordsTable.Row(coord.getX(), coord.getY()))

    if sf:
        sf.close()

    with StarFile(micStarFn, 'w') as sf:
        sf.writeLine('# version 30001')
        sf.writeTable('coordinate_files', coordsMicTable)


def write_stars(workingDir):
    """ Restart one or more protocols. """
    project = Project(pw.Config.getDomain(), workingDir)
    project.load()

    for prot in project.getRuns():
        clsName = prot.getClassName()
        if clsName == 'CistemProtCTFFind':
            ctfs = prot.outputCTF
            print(f"- {prot.getObjId()}: {prot.getRunName()} ({clsName})")
            print(f"            CTFs: {ctfs.getSize()}")
            write_micrographs_star('micrographs_ctf.star', ctfs)

        elif clsName == 'SphireProtCRYOLOPicking':
            write_coordinates('coordinates.star', prot)

def clone_project(src, dst):
    """ Clone an existing Scipion project into a new project.
    Existing run folders will not be copied but linked to save space. """

    #for r in /jude/facility/appdpcryoem/ 20231019_Krios01_cdk16_data_1_OTF/Runs/ *; do echo $r; ln -s $r; done
    #rsync - av - -exclude = {'EPU', 'Coordinates', 'Runs', 'Tmp'} / jude / facility / appdpcryoem / 20231019
    if not os.path.exists(os.path.join(src, 'project.sqlite')):
        raise Exception("Missing 'project.sqlite' from src folder, "
                        "please provide a valid project folder")

    srcRuns = os.path.join(src, 'Runs')
    runs = os.listdir(srcRuns)
    if not runs:
        raise Exception("There are no runs in src folder, "
                        "please provide a valid project folder")

    projectName = os.path.basename(src)
    cloneFolder = os.path.join(dst, projectName)

    dstRuns = os.path.join(cloneFolder, 'Runs')
    Process.system(f"mkdir -p {dstRuns}")
    Process.system(f"rsync -av --exclude={{'EPU','Coordinates','Runs','Tmp','logs'}} {src}/ {cloneFolder}/")

    print("Linking runs...")

    for r in runs:
        srcR = os.path.join(srcRuns, r)
        dstR = os.path.join(dstRuns, r)
        Process.system(f"ln -s {srcR} {dstR}")


def main():
    p = argparse.ArgumentParser(prog='scipion-otf')
    g = p.add_mutually_exclusive_group()

    g.add_argument('--create', action='store_true',
                       help="Create a new Scipion project in the working "
                            "directory. This will overwrite any existing "
                            "'scipion' folder there.")
    g.add_argument('--restart', nargs="+", type=int,
                   help="Restart one or more protocols. ")
    g.add_argument('--restart_rankers', action='store_true',
                   help="Restart failed ranker jobs. ")
    g.add_argument('--test', action='store_true',
                   help="Some test code")
    g.add_argument('--clean', action="store_true",
                   help="Clean Scipion project files/folders.")
    g.add_argument('--continue_2d', action="store_true")
    g.add_argument('--write_stars', action="store_true",
                   help="Generate STAR micrographs and particles STAR files.")
    g.add_argument('--clone_project', nargs=2, metavar=('SRC', 'DST'),
                   help="Clone an existing Scipion project")

    args = p.parse_args()

    if args.create:
        create_project(cwd)
    elif args.restart:
        restart(cwd, args.restart)
    elif args.restart_rankers:
        restart_rankers(cwd)
    elif args.test:
        pass  # debugging/testing code
    elif args.clean:
        clean_project(cwd)
    elif args.write_stars:
        write_stars(cwd)
    elif args.continue_2d:
        continue_project(cwd)
    elif args.clone_project:
        src, dst = args.clone_project
        clone_project(src, dst)
    else:  # by default open the GUI
        from pyworkflow.gui.project import ProjectWindow
        ProjectWindow(cwd).show()


if __name__ == '__main__':
    main()
