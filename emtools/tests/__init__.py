
import os

from emtools.utils import Color


EM_TESTDATA = os.environ.get('EM_TESTDATA', None)

_EM_TESTDATA_WARN = True  # Warn once if EM_TEST_DATA is not configured


def testpath(*paths):
    """ Return paths from EM_TESTDATA. """
    if EM_TESTDATA is None:
        global _EM_TESTDATA_WARN
        if _EM_TESTDATA_WARN:
            print(f">>> Warning, {Color.warn('EM_TESTDATA')} variable not "
                  f"defined, some test might not be executed.\n")
            _EM_TESTDATA_WARN = False
        return None
    
    p = os.path.abspath(os.path.join(EM_TESTDATA, *paths))

    if not os.path.exists(p):
        print(">>> Missing path: ", Color.red(p))
        return None

    print(">>> Using path: ",  Color.bold(p))
    return p
