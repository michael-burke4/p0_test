#!/usr/bin/python3

import errno
import json
import os
import pty
import select
import subprocess
import shutil
import time

SUBMISSIONS_DIRNAME = "submissions"

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

def prompt_level():
    while True:
        lvl = input("Which level would you like to grade? (or [e]xit) ")
        if lvl == "e":
            return "e"
        if lvl in os.listdir(f"./{SUBMISSIONS_DIRNAME}"):
            return lvl

def prompt_grading(outs, good_outs, tests):
    while True:
        inp = input("[o]verview, [i]nspect a specific submission, [c]ontinue grading, or [e]xit the grading program:  ")
        if inp == "o":
            print_overview(outs, good_outs)
        if inp == "i":
            prompt_inspect(outs, good_outs, tests)
        if inp == "c":
            return
        if inp == "e":
            exit()

def select_from_list_by_name(li):
    selection = []
    if li == []:
        print(f"tried to select from empty list!", file=sys.stderr)
        exit(1)
    for i in li:
        print(i["name"])
    while selection == []:
        select_name = input("Select from the above list... ")
        selection = [s for s in li if s["name"] == select_name]
    return selection[0]

def prompt_list_index(li):
    l = len(li)
    while True:
        inp = input(f"select an index between 0 and {l - 1} ")
        try:
            inp = int(inp)
            if inp >= 0 and inp < l - 1:
                return inp
        except:
            pass

def do_comparison(selection, good_out, tests):
    print("Here is an overview of which tests passed and failed:")
    print_single_overview(selection, good_out)
    print("Which binary would you like to compare against?")
    comp = select_from_list_by_name(good_out)
    print("which test would you like to compare?")
    i = prompt_list_index(tests)
    comp_test = comp["test_outputs"][i]
    select_test = selection["test_outputs"][i]
    print_color(OKCYAN, f"test input:\t{bytes(tests[i], 'UTF-8')}")
    if select_test["stdout"] == comp_test["stdout"]:
        print_color(OKGREEN, "standard output matched.")
    else:
        print_color(FAIL, "standard output mismatch!")
        print_color(OKGREEN, f"\t{comp['name']}'s output: {comp_test['stdout']}")
        print_color(WARNING, f"\t{selection['name']}'s output: {select_test['stdout']}")
    if select_test["stderr"] == comp_test["stderr"]:
        print_color(OKGREEN, "standard error matched")
    else:
        print_color(FAIL, "standard error mismatch!")

    if select_test["timeout"] == comp_test["timeout"]:
        if select_test["timeout"]:
            print_color(OKGREEN, "both versions timed out")
        else:
            print_color(OKGREEN, "both versions did not time out")
    else:
        if select_test["timeout"]:
            print_color(FAIL, "The student's submission timed out while the known good submission didn't!")
        else:
            print_color(FAIL, "The good submission timed out while the student's didn't!")


def _prompt_inspect(selection, good_outs, tests):
    print(f"What would you like to do with submission '{selection['name']}'? ")
    while True:
        inp = input("[c]ompare outputs against a known good version, [w]rite and run a new test, [i]nspect a different submission, or [e]xit the grading program ")
        if inp == "c":
            do_comparison(selection, good_outs, tests)
        if inp == "w":
            pass # TODO
        if inp == "i":
            return
        if inp == "e":
            exit()

def prompt_inspect(outs, good_outs, tests):
    while True:
        print("Which submission would you like to inspect?")
        selection = select_from_list_by_name(outs)
        _prompt_inspect(selection, good_outs, tests)
        while True:
            inp = input("[i]nspect another submission, [r]eturn to main menu, or [e]xit the grading program ")
            if inp == "i":
                break
            if inp == "r":
                return
            if inp == "e":
                exit()

def print_single_overview(out, good_outs):
    i = 0
    print(f"binary name: {out['name']}")
    for test in out["test_outputs"]:
        match = search_for_good_match(i, test, good_outs)
        print(f"\tTest #{i}: ", end="")
        if match != None:
            print_color(OKGREEN, f"Output matches with {match}")
        else:
            print_color(FAIL, "Output did not match any known good outputs!")
        i += 1

def print_overview(outs, good_outs):
    for out in outs:
        print_single_overview(out, good_outs)

def tests_agree(output, g):
    return output["stdout"] == g["stdout"] and output["stderr"] == g["stderr"] and output["timeout"] == g["timeout"]

def search_for_good_match(test_index, output, good_outs):
    ret = []
    for good in good_outs:
        g = good["test_outputs"][test_index]
        if tests_agree(output, g):
            return good["name"]
    return None

def load_bins(lvl):
    return [f"{os.getcwd()}/{SUBMISSIONS_DIRNAME}/{lvl}/{x}" for x in os.listdir(f"./{SUBMISSIONS_DIRNAME}/{lvl}") if not x.startswith("good_")]

def load_good_bins(lvl):
    return [f"{os.getcwd()}/{SUBMISSIONS_DIRNAME}/{lvl}/{x}" for x in os.listdir(f"./{SUBMISSIONS_DIRNAME}/{lvl}") if x.startswith("good_")]

def run_bins(test_inputs, bins):
    ret = []
    for binary in bins:
        entry = {}
        entry["name"] = binary.split("/")[-1]
        entry["test_outputs"] = []
        for t in test_inputs:
            out = tty_capture(binary, bytes(t, "utf-8"))
            test_out = {}
            test_out["stdout"] = out[0]
            test_out["stderr"] = out[1]
            test_out["timeout"] = out[2]
            entry["test_outputs"].append(test_out)
        ret.append(entry)
    return ret

def main():
    print("Welcome to the kdlp grading system!")
    while True:
        lvl = prompt_level()
        if lvl == "e":
            exit()
        bins = load_bins(lvl)
        good = load_good_bins(lvl)
        tests = ["a\n", "b\n", "abc\n"]
        print("OK! running tests...")
        outs = run_bins(tests, bins)
        good_outs = run_bins(tests, good)
        print("Tests complete!")
        prompt_grading(outs, good_outs, tests)



if __name__ == '__main__':
    main()
