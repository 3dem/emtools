
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

lsf_parser.add_argument('queue_name', nargs='?', help="")
lsf_parser.add_argument('--jobs', '-j', nargs='?',
                        default=argparse.SUPPRESS)
lsf_parser.add_argument('--json', action='store_true')
lsf_parser.add_argument('--debug', action='store_true')

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
    from .lsf import LSF

    lsf = LSF(debug=args.debug)

    if hasattr(args, 'jobs'):
        if args.jobs:
            lsf.show_jobs(user=args.jobs)
        else:
            lsf.show_jobs(queue=args.queue_name)
    else:
        lsf.show_queues(args.queue_name, outputJson=args.json)

else:
    print("command: ", args.command)
