import argparse


def parse_workload(arg):
    if arg == 'basic':
        return ('basic', None)

    if "=" in arg:
        name, val = arg.split("=")
        return name, int(val)
    else:
        raise argparse.ArgumentTypeError(
            f"Invalid format: '{arg}'. Must be 'workload=value' (e.g., pcmark10=200) or 'basic'."
        )


parser = argparse.ArgumentParser(description='SSD Simple Model')

parser.add_argument(
    "--pcie-gen",
    type=int,
    choices=[4, 5, 6],
    default=5,
    help='PCIe generation number. Choose from {4, 5, 6}.')

parser.add_argument("--channel", type=int, default=16)
parser.add_argument("--way", type=int, default=2)
parser.add_argument("--plane", type=int, default=4)
parser.add_argument("--nand-io-mbps", type=int, default=0)
parser.add_argument("--nand-product", type=str, default='TLC_EXAMPLE')
parser.add_argument("--nand-cell-type", type=str.upper, choices=['SLC', 'MLC', 'TLC'], default='TLC',)

parser.add_argument("--gc-threshold", type=float, default=0.2)
parser.add_argument("--urgent-gc-threshold", type=float, default=0.05)
parser.add_argument("--sustained-block-rate", type=float, default=0.8)
parser.add_argument("--sustained-page-rate", type=float, default=0.8)

parser.add_argument("--make-sustained", action='store_true')

parser.add_argument(
    "--workload-type",
    type=parse_workload, default=('basic', None),
    help="Workload type. Use 'basic' or 'name=value' (e.g., pcmark10=200)")

parser.add_argument("--enable-command-record", action='store_true')
parser.add_argument("--enable-performance-record", action='store_true')
parser.add_argument(
    "--enable-utilization",
    action='store_true',
    help='enable utilization')

parser.add_argument("--enable-qos", action='store_true')

parser.add_argument(
    "--pre-defined-workload",
    type=str,
    help='pre-defined workload name')
parser.add_argument("--folder-name", type=str, help='output folder name')

parser.add_argument(
    "--range-bytes",
    type=str,
    help='total data range (Bytes) of each TestCase')

parser.add_argument("--enable-power", action='store_true')
args = parser.parse_args()
