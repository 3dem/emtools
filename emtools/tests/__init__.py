
import os

from emtools.utils import Color


EM_TESTDATA = os.environ.get('EM_TESTDATA', None)


def testpath(*paths):
    """ Return paths from EM_TESTDATA. """
    if EM_TESTDATA is None:
        return None
    
    p = os.path.abspath(os.path.join(EM_TESTDATA, *paths))
    print(">>> Using path: ",  Color.bold(p))
    return p
