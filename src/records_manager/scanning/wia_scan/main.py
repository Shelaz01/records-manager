"""wia_scan 0.8.0.

Usage:
  wia_scan list_devices [-v]
  wia_scan single [--file=<output_file>] [--dpi=<dpi>] [--brightness=<brightness>]
                  [--contrast=<contrast>] [--mode=<mode>] [-v] [--uid=<uid>] [-q]
  wia_scan many [--out=<output_folder>] [--brightness=<brightness>] [--contrast=<contrast>] [-v]
  wia_scan calibrate brightness [--start=<start_range>] [--end=<end_range>]
                [--num_runs=<num_runs>] [--out=<output_folder>] [--uid=<uid>] [-q]
  wia_scan --help
  wia_scan --version

Options:
  -h --help                    Show this screen.
  --version                    Show version.
  -v --verbose                 Verbose output
  -q --quiet                   Quiet=no output
  --dpi=<dpi>                  Dots per inch; the higher this setting the higher the
                               output resolution [default: 200]
  --brightness=<brightness>    Brightness setting for the scanner, goes from -1000 to
                               1000 [default: 0]
  --contrast=<contrast>        Contrast setting for the scanner, goes from -1000
                               to 1000 [default: 0]
  --mode=<mode>                RGB for colored, L for grayscale [default: RGB]
  --file=<output_file>         Image output file
  --out=<output_folder>        Scanned images output folder [default: .]
  --start=<start_range>        Lowest value of brightness scanned [default: -200]
  --end=<end_range>            Highest value of brightness scanned [default: 200]
  --num_runs=<num_runs>        Number of scans for the "calibration" process [default: 9]
"""

import sys

from docopt import docopt
from .core import list_devices, get_device_manager, IndentPrinter, \
    scan_single_side_main, scan_many_documents_flatbed, get_default_profile, \
    run_calibration_process


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    arguments = docopt(__doc__, version='wia_scan 0.8.0', argv=argv)

    print_function = IndentPrinter(indent=0, print_function=print)
    verbose = arguments['--verbose']
    quiet = arguments['--quiet']
    device_uid = arguments['--uid']

    if arguments['list_devices']:
        device_manager = get_device_manager()
        list_devices(device_manager=device_manager,
                     print_function=print_function, verbose=verbose)
    elif arguments['calibrate']:
        run_calibration_process(
            int(arguments['--start']),
            int(arguments['--end']),
            num_runs=int(arguments['--num_runs']),
            device_uid=device_uid, output_folder=arguments['--out'],
            print_function=print_function, verbose=verbose, quiet=quiet)
    elif arguments['single']:
        if quiet and device_uid is None:
            print('Invalid input: uid has to be provided when quiet is used')
            sys.exit(-1)
        scan_profile = get_default_profile()
        scan_profile['brightness'] = int(arguments['--brightness'])
        scan_profile['contrast'] = int(arguments['--contrast'])
        scan_profile['dpi'] = int(arguments['--dpi'])
        scan_profile['mode'] = arguments['--mode']

        scan_single_side_main(
            scan_profile=scan_profile,
            print_function=print_function,
            verbose=verbose,
            quiet=quiet,
            device_uid=device_uid,
            output_file=arguments['--file'])
    elif arguments['many']:
        scan_many_documents_flatbed(
            brightness=int(arguments['--brightness']), contrast=int(arguments['--contrast']),
            print_function=print_function, verbose=verbose, output_folder=arguments['--out'])


if __name__ == '__main__':
    main()
