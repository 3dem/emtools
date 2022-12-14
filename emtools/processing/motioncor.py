#!/usr/bin/env python

import os
import sys
import argparse
import threading
from glob import glob
from uuid import uuid4

from emtools.utils import Timer, Color, Pipeline
from emtools.metadata import StarFile


class McPipeline(Pipeline):
    """ Pipeline specific to Motioncor processing. """
    def __init__(self, generateInputFunc, gpuList, outputDir, threads=1, **kwargs):
        Pipeline.__init__(self, **kwargs)
        self.mc = {
            'program': os.environ['MC_PROGRAM'],
            'args': os.environ['MC_ARGS'],
            'gain': os.environ['MC_GAIN']
        }
        self.run_id = f'R-{uuid4()}'
        self.outputDir = outputDir
        self.scratchDir = kwargs.get('scratchDir', self.outputDir)
        self.workingDir = os.path.join(self.scratchDir, self.run_id)

        g = self.addGenerator(generateInputFunc)
        f1 = self.addProcessor(g.outputQueue, self.convert)
        if threads > 1:
            for i in range(1, threads):
                self.addProcessor(g.outputQueue, self.convert,
                                  outputQueue=f1.outputQueue)
        moveQueue = f1.outputQueue
        if gpuList:
            mc1 = self.addProcessor(f1.outputQueue,
                                    self.get_motioncor_proc(gpuList[0]))
            for gpu in gpuList[1:]:
                self.addProcessor(f1.outputQueue, self.get_motioncor_proc(gpu),
                                  outputQueue=mc1.outputQueue)
            moveQueue = mc1.outputQueue

        self.addProcessor(moveQueue, self.moveout)

    def convert(self, batch):
        images = batch['images']
        thread_id = threading.get_ident()
        batch_id = f'{str(uuid4()).split("-")[0]}'
        batch_dir = os.path.join(self.workingDir, batch_id)

        print(f'T-{thread_id}: converting {len(images)} images...batch dir: {batch_dir}')

        batch = {
            'images': images,
            'batch_id': batch_id,
            'batch_dir': batch_dir
        }

        script = f"rm -rf {batch_dir} && mkdir -p {batch_dir}\n"

        # FIXME: Just create links if input is already in .mrc format
        cmd = 'tif2mrc'

        for fn in images:
            base = os.path.basename(fn)
            if cmd == 'tif2mrc':
                base = base.replace('.tiff', '.mrc')
            outFn = os.path.join(batch_dir, base)
            script += f'{cmd} {fn} {outFn}\n'

        prefix = f'{thread_id}_{batch_id}_tif2mrc'
        scriptFn = f'{prefix}_script.sh'
        logFn = f'{thread_id}_tif2mrc_log.txt'

        with open(scriptFn, 'w') as f:
            f.write(script)

        os.system(f'bash -x {scriptFn} &>> {logFn} && rm {scriptFn}')

        return batch

    def motioncor(self, gpu, batch):
        mc = self.mc
        batch_id = batch['batch_id']
        batch_dir = batch['batch_dir']
        script = f"""
        cd {batch_dir}
        {mc['program']} -InMrc ./FoilHole_ -InSuffix fractions.mrc -OutMrc aligned_ -Serial 1  -Gpu {gpu}  -Gain {mc['gain']} -LogDir ./ {mc['args']}
        """
        prefix = f'motioncor-gpu{gpu}'
        print(f'{prefix}: running Motioncor for batch {batch_id} on GPU {gpu}')

        scriptFn = f'{prefix}_{batch_id}_script.sh'
        logFn = f'{prefix}_motioncor_log.txt'
        with open(scriptFn, 'w') as f:
            f.write(script)
        os.system(f'bash -x {scriptFn} &>> {logFn} && rm {scriptFn}')
        return batch

    def get_motioncor_proc(self, gpu):
        def _motioncor(batch):
            return self.motioncor(gpu, batch)

        return _motioncor

    def moveout(self, batch):
        batch_dir = batch['batch_dir']
        thread_id = threading.get_ident()
        print(f'T-{thread_id}: moving output from batch dir: {batch_dir}')
        # FIXME: Check what we want to move to output
        os.system(f'mv {batch_dir}/* {self.outputDir}/ && rm -rf {batch_dir}')
        return batch


class Main:
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('input_images',
                            help='Input images, can be a star file, a txt file or '
                                 'a pattern.')

        parser.add_argument('--convert', choices=['default', 'tif2mrc', 'cp'])

        parser.add_argument('--nimages', '-n', nargs='?', type=int,
                            default=argparse.SUPPRESS)
        parser.add_argument('--output', '-o', default='output')
        parser.add_argument('-j', type=int, default=1,
                            help='Number of parallel threads')
        parser.add_argument('--batch', '-b', type=int, default=0,
                            help='Batch size')
        parser.add_argument('--gpu', default='', nargs='?',
                            help='Gpu list, separated by comma.'
                                 'E.g --gpu 0,1')
        parser.add_argument('--scratch', default='',
                            help='Scratch directory to do intermediate I/O')

    @staticmethod
    def run(args):
        n = args.nimages
        output = args.output

        if args.input_images.endswith('.star'):
            input_star = args.input_images

            with StarFile(input_star) as sf:
                # Read table in a different order as they appear in file
                # also before the getTableNames() call that create the offsets
                tableMovies = sf.getTable('movies')

            all_images = [row.rlnMicrographMovieName for row in tableMovies]
        elif '*' in args.input_images:
            all_images = glob(args.input_images)
        else:
            raise Exception('Please provide input as star file or files pattern (with * in it).')

        input_images = all_images[:n]

        run_id = f'R-{uuid4()}'

        print(f' run_id: {run_id}')
        print(f' images: {len(input_images)}')
        print(f' output: {output}')
        print(f'threads: {args.j}')
        print(f'   gpus: {args.gpu}')
        print(f'  batch: {args.batch or len(input_images)}')

        wd = args.scratch if args.scratch else output
        intermediate = os.path.join(wd, run_id)

        def generate():
            b = args.batch
            if b:
                n = len(input_images) // b
                for i in range(n):
                    yield {'images': input_images[i*b:(i+1)*b]}
            else:
                yield {'images': input_images}

        os.system(f'rm -rf {output} && mkdir {output}')
        os.system(f'rm -rf {intermediate} && mkdir {intermediate}')

        t = Timer()

        gpuList = args.gpu.split(',')
        mc = McPipeline(generate, gpuList, output, threads=args.j, debug=False)
        mc.run()

        os.system(f'rm -rf {intermediate}')

        t.toc()


