# https://stackoverflow.com/a/287944
HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKCYAN = '\033[96m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'


def print_color(color_tag, *args, end='\n'):
    print(color_tag, end='')
    for arg in args:
        print(arg, end=' ')
    print(ENDC, end=end)


def print_warning(*args, end='\n'):
    print_color(WARNING, *args, end=end)


def print_fail(*args, end='\n'):
    print_color(FAIL, *args, end=end)


def print_header(*args, end='\n'):
    print_color(HEADER, *args, end=end)


def print_okblue(*args, end='\n'):
    print_color(OKBLUE, *args, end=end)


def print_okcyan(*args, end='\n'):
    print_color(OKCYAN, *args, end=end)


def print_okgreen(*args, end='\n'):
    print_color(OKGREEN, *args, end=end)
