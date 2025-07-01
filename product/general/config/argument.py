import argparse

parser = argparse.ArgumentParser(description='SSD Simple Model')

parser.add_argument("--channel", type=int, default=16)
parser.add_argument("--way", type=int, default=2)
parser.add_argument("--plane", type=int, default=4)
parser.add_argument("--nand-io-mbps", type=int, default=0)
parser.add_argument("--nand-product", type=str, default='TLC_EXAMPLE')

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
args = parser.parse_args()
