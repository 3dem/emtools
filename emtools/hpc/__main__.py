
import argparse

parser = argparse.ArgumentParser(prog='emtools.hpc')
subparsers = parser.add_subparsers(
    help='Type of job submission system (e.g LSF)',
    dest='command')

submit_parser = subparsers.add_parser("submit")
lsf_parser = subparsers.add_parser("lsf")
slurm_parser = subparsers.add_parser("slurm")

submit_parser.add_argument('input',
                           help="Input template to generate the "
                                "submission script")


lsf_parser.add_argument('queues', nargs='?', help="")
args = parser.parse_args()

cmd = args.command

if not cmd:
    parser.print_help()

elif cmd == "submit":
    from .submit import submit_script
    print("template: ", args.input)

elif cmd == 'lsf':
    from .lsf import show_queues
    show_queues(args.queues)

else:
    print("command: ", args.command)
