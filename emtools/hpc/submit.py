
import os
import importlib.machinery
import importlib.util

from emtools.utils import Color


def submit_script(template_path):
    print(">>> Parsing file: ", Color.green(template_path))

    spec = importlib.util.spec_from_loader(
        'template', importlib.machinery.SourceFileLoader('template', template_path))
    template = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(template)
    print(">>> Overwriting file: ", Color.green(template_path))
    with open(template_path, 'w') as f:
        f.write(template.TEMPLATE)
        f.flush()

    cmd = template.QSUB_COMMAND + ' ' + template_path
    print(">>>", Color.green(cmd))
    os.system(cmd)
