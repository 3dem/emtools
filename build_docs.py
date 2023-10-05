
from emtools.utils import Process, Color

Process.system("rm -rf html", color=Color.green)
Process.system("sphinx-build -b html docs html", color=Color.green)
