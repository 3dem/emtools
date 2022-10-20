
import argparse

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(
    help='Type of job submission system (e.g LSF)',
    dest='command')

submit_parser = subparsers.add_parser("submit")
lsf_parser = subparsers.add_parser("LSF")
slurm_parser = subparsers.add_parser("SLURM")

submit_parser.add_argument('input',
                           help="Input template to generate the "
                                "submission script")


lsf_parser.add_argument('queues',
                        help="")
args = parser.parse_args()

cmd = args.command

if cmd == "submit":
    from .submit import submit_script
    print("template: ", args.input)
elif cmd == 'LSF':
    from .lsf import show_queues
    show_queues(args.queues)
else:
    print("command: ", args.command)
