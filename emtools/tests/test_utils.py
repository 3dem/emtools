# **************************************************************************
# *
# * Authors:  J. M. de la Rosa Trevin (delarosatrevin@gmail.com)
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
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@gmail.com'
# *
# **************************************************************************

import unittest
import time
from pprint import pprint

from emtools.utils import Timer, System


class TestTimer(unittest.TestCase):

    def test_basics(self):
        t = Timer()
        time.sleep(1)
        t.toc()

        with Timer('Time in context:'):
            time.sleep(2)


class TestSystem(unittest.TestCase):
    def test_funcs(self):
        # Specs
        specs = System.specs()
        self.assertTrue('GPUs' in specs)
        self.assertTrue('CPUs' in specs)
        self.assertGreater(specs['CPUs'], 0)
        print(">>> CPUs: ", specs['CPUs'])
        print(">>> GPUs: ", specs['GPUs'])

        # Hostname
        h = System.hostname()
        print(">>> Hostname: ", h)
        self.assertTrue(bool(h))


class TestResourceMonitor(unittest.TestCase):
    def test_load_series(self):
        import os
        import tempfile
        from emtools.utils import ResourceMonitor

        with tempfile.TemporaryDirectory() as tmp:
            csvFile = os.path.join(tmp, 'run01.csv')
            with open(csvFile, 'w') as f:
                f.write('time,cpu,rss_gb,read_mbs\n')
                for i in range(10):
                    f.write(f"{i * 2},{i * 10},{i / 10},{'' if i < 4 else 1}\n")
            # Buckets of 4, 4 and 2 rows
            data = ResourceMonitor.load_series(csvFile, max_points=3)
            self.assertEqual(data['samples'], 10)
            series = data['series']
            self.assertEqual(series['time'], [0, 8, 16])
            self.assertEqual(series['cpu'], [15, 55, 85])  # mean
            self.assertEqual(series['rss_gb'], [0.3, 0.7, 0.9])  # max
            self.assertEqual(series['read_mbs'], [None, 1, 1])
            self.assertEqual(data['last']['time'], '18')

            open(csvFile, 'w').close()
            data = ResourceMonitor.load_series(csvFile)
            self.assertEqual(data, {'samples': 0, 'series': {}, 'last': None})

    def test_snapshot(self):
        import os
        import sys
        from emtools.utils import ResourceMonitor

        s = ResourceMonitor.snapshot(os.getpid(), dt=0.1)
        self.assertEqual(s['pid'], os.getpid())
        self.assertGreaterEqual(s['procs'], 1)
        self.assertGreater(s['rss_gb'], 0)
        # The command line must contain match
        self.assertIsNone(ResourceMonitor.snapshot(os.getpid(), match='no-such-job-xyz'))
        self.assertIsNotNone(ResourceMonitor.snapshot(os.getpid(), dt=0.1,
                                                      match=os.path.basename(sys.argv[0])))
