
import argparse
import os.path

parser = argparse.ArgumentParser(prog='emtools.hpc')
subparsers = parser.add_subparsers(
    help='Type of job submission system (e.g LSF)',
    dest='command')

submit_parser = subparsers.add_parser("submit")
lsf_parser = subparsers.add_parser("lsf")
slurm_parser = subparsers.add_parser("slurm")

submit_parser.add_argument('template_file',
                           help="Input template that will be overwritten "
                                "with variables to generate the queue "
                                "submission script.")

lsf_parser.add_argument('queues', nargs='?', help="")
args = parser.parse_args()

cmd = args.command

if not cmd:
    parser.print_help()

elif cmd == "submit":
    from .submit import submit_script
    if not os.path.exists(args.template_file):
        raise Exception("Provided file does not exists.")
    submit_script(args.template_file)

elif cmd == 'lsf':
    from .lsf import show_queues
    show_queues(args.queues)

else:
    print("command: ", args.command)
