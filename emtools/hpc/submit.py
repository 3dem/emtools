
import os
import imp

from emtools.utils import Color


def submit_script(template_path):
    print(">>> Parsing file: ", Color.green(template_path))

    #FIXME: replace implementation with imp
    template = imp.load_source('template', template_path)
    print(">>> Overwriting file: ", Color.green(template_path))
    with open(template_path, 'w') as f:
        f.write(template.TEMPLATE)
        f.flush()

    cmd = template.QSUB_COMMAND + ' ' + template_path
    print(">>>", Color.green(cmd))
    os.system(cmd)
