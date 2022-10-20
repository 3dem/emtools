import subprocess


class Process:
    def __init__(self, *args, **kwargs):
        """ Create a process using subprocess.run. """
        self._args = args
        self._p = subprocess.run(args, capture_output=True, text=True)
        #FIXME: Maybe some cases returncode could be non-zero
        if self._p.returncode != 0:
            raise Exception(self._p.stderr)

    def lines(self):
        for line in self._p.stdout.split('\n'):
            yield line

    def print(self, args=True, stdout=False):
        if args:
            print(">>> ", *self._args)
        if stdout:
            print(self._p.stdout)

