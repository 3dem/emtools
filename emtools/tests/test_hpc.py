import os
import shutil
import tempfile
import unittest
import unittest.mock

from emtools.hpc import ClusterJob, ComputingEnv


class TestClusterJob(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='emtools_hpc_')
        self.script = os.path.join(self.tmp, 'inspect.sh')
        with open(self.script, 'w') as f:
            f.write('#!/bin/bash\n'
                    'if [ "$2" = "--json" ]; then echo "{\\"id\\": \\"$1\\"}"; '
                    'elif [ "$2" = "--fail" ]; then echo "bad job" >&2; exit 1; '
                    'else echo "job $1 text"; fi\n')
        os.chmod(self.script, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_command(self):
        self.assertEqual(ClusterJob.command('bkill {job_id}', ' 123 '), 'bkill 123')
        self.assertEqual(ClusterJob.command('bkill {job_id}', '123[4]'), 'bkill 123[4]')
        for bad in ['', 'abc', '123; rm -rf /', '12 34', '123[x]']:
            with self.assertRaisesRegex(Exception, 'Invalid cluster job id'):
                ClusterJob.command('bkill {job_id}', bad)

    def test_inspect_json(self):
        result = ClusterJob.inspect(self.script + ' {job_id} --json', '330047105')
        self.assertEqual(result['format'], 'json')
        self.assertEqual(result['data'], {'id': '330047105'})
        self.assertEqual(result['job_id'], '330047105')
        self.assertEqual(result['command'], self.script + ' 330047105 --json')

    def test_inspect_text(self):
        result = ClusterJob.inspect(self.script + ' {job_id}', '123[4]')
        self.assertEqual(result, {'job_id': '123[4]', 'format': 'text',
                                  'text': 'job 123[4] text',
                                  'command': self.script + ' 123[4]'})

    def test_inspect_failure_adds_stderr(self):
        result = ClusterJob.inspect(self.script + ' {job_id} --fail', '1')
        self.assertEqual(result['format'], 'text')
        self.assertEqual(result['text'], 'bad job')

    def test_run(self):
        p = ClusterJob.run(self.script + ' {job_id}', '7')
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), 'job 7 text')
        with self.assertRaisesRegex(Exception, 'Could not run'):
            ClusterJob.run(os.path.join(self.tmp, 'missing') + ' {job_id}', '7')
        with self.assertRaisesRegex(Exception, 'Timeout'):
            ClusterJob.run('sleep 5 {job_id}', '1', timeout=0.2)

    def test_current(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('LSB_', 'SLURM_'))}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(ClusterJob.current())
            os.environ.update(LSB_JOBID='42', LSB_QUEUE='gpu',
                              LSB_HOSTS='n1 n1 n2', LSB_DJOB_NUMPROC='3')
            self.assertEqual(ClusterJob.current(),
                             {'system': 'LSF', 'job_id': '42', 'queue': 'gpu',
                              'cpus': 3, 'hosts': 'n1 n2'})


class TestComputingEnv(unittest.TestCase):

    def test_collect_and_lines(self):
        info = ComputingEnv.collect(gpu_ids=[0, 1], cpus=8)
        self.assertEqual(info['cpus'], 8)
        self.assertEqual(info['gpus'], 2)
        self.assertEqual(info['gpu_ids'], [0, 1])
        lines = ComputingEnv.lines(info)
        self.assertEqual(lines[0], 'Computing environment')
        self.assertIn('  Job CPUs (params): 8', lines)


if __name__ == '__main__':
    unittest.main()
