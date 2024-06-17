#!/usr/bin/python3

import errno
import json
import os
import pty
import select
import subprocess
import shutil
import time

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

def print_color(color_tag, *args, ending='\n'):
    print(color_tag, end='')
    for arg in args:
        print(arg, end=' ')
    print(ENDC, end=ending)

# this function is courtesy of
# https://stackoverflow.com/a/52954716
def tty_capture(cmd, bytes_input, output_bytes=2048):
    # Capture the output of cmd with bytes_input to stdin,
    # with stdin, stdout and stderr as TTYs.
    # Based on Andy Hayden's gist:
    # https://gist.github.com/hayd/4f46a68fc697ba8888a7b517a414583e
    mo, so = pty.openpty()  # provide tty to enable line-buffering
    me, se = pty.openpty()
    mi, si = pty.openpty()

    p = subprocess.Popen(
        cmd,
        bufsize=0, stdin=si, stdout=so, stderr=se,
        close_fds=True)
    for fd in [so, se, si]:
        os.close(fd)
    os.write(mi, bytes_input)

    timeout = 0.04  # seconds
    timed = False
    readable = [mo, me]
    result = {mo: b'', me: b''}
    tm = time.time()
    try:
        while readable:
            if time.time() - tm > timeout * 8:
                timed = True
                break
            ready, _, _ = select.select(readable, [], [], timeout)
            for fd in ready:
                try:
                    data = os.read(fd, output_bytes)
                except OSError as e:
                    if e.errno != errno.EIO:
                        raise
                    # EIO means EOF on some systems
                    readable.remove(fd)
                else:
                    if not data: # EOF
                        readable.remove(fd)
                    result[fd] += data
    finally:
        for fd in [mo, me, mi]:
            os.close(fd)
        if p.poll() is None:
            p.kill()
        p.wait()
    return result[mo], result[me], timed

def run_test(test):
    return tty_capture(test['args'], bytes(test['input'], 'UTF-8'))

def clean_cur_dir():
    for file in os.scandir():
        if file.is_file():
            os.remove(file)
        else:
            shutil.rmtree(file)

def check_dir_empty(directory):
    inpt = 0
    if os.listdir() != []:
        while inpt != 'y' and inpt != 'n':
            inpt = input('WARNING: %s is not empty. Remove all files and directories in %s? [y/n]: ' % (directory, directory))
        if inpt == 'y':
            clean_cur_dir()

def do_replacements(string, reps):
    for rep in reps:
        string = string.replace(rep, reps[rep])
    return bytes(string, 'UTF-8')

def prompt(level_no):
    while True:
        inp = input('Apply patches until level %d is complete. [h]elp, [c]ontinue, [a]bort, or [e]xit: ' % level_no)
        if inp == 'a':
            return False
        elif inp == 'e':
            clean_cur_dir()
            return False
        elif inp == 'h':
            print('CONTINUE: Patches for the current level have been applied, proceed to run the tests for that level.')
            print('ABORT: Exit the program, perform no further tests, Will not delete any files in the testing directory.')
            print('EXIT: Exit the program, perform no further tests, and completely clean the testing directory.')
        elif inp == 'c':
            return True

def check_ok():
    while True:
        inp = input('Is this ok? [y/n]: ')
        if inp == 'y':
            return 1
        elif inp == 'n':
            return 0

def make_log(name):
    if 'logs' not in os.listdir():
        os.mkdir('logs')
    filename = '%s-%d.log' % (name, time.time())
    logfile = open('logs/'+filename, 'a')
    return logfile

def log(log_file, *args, ending='\n'):
    for arg in args:
        print(arg, end=' ', file=log_file)
    print('', end=ending, file=log_file)

def print_and_log(color, log_file, *args, ending='\n'):
    print_color(color, *args, ending=ending)
    log(log_file, *args, ending=ending)

def prompt_level():
    while True:
        try:
            lvl = int(input("Which level would you like to grade? (0-9)\t"))
            return lvl
        except ValueError:
            print("INVALID! Enter a number between 0 and 9")

def main():
    print("Welcome to the kdlp grading system!")
    lvl = prompt_level()


if __name__ == '__main__':
    main()
