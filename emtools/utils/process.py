import subprocess


class Process:
    def __init__(self, *args, **kwargs):
        """ Create a process using subprocess.run. """
        self.args = args
        self._p = subprocess.run(args, capture_output=True, text=True)
        self.stdout = self._p.stdout
        self.stderr = self._p.stderr
        #FIXME: Maybe some cases returncode could be non-zero
        if self._p.returncode != 0:
            raise Exception(self.stderr)

    def lines(self):
        for line in self.stdout.split('\n'):
            yield line

    def print(self, args=True, stdout=False):
        if args:
            print(">>> ", *self.args)
        if stdout:
            print(self.stdout)

