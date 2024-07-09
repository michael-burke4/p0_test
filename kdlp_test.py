#!/usr/bin/env python3

import errno
import json
import os
import pty
import select
import subprocess
import shutil
import time
import pandas as pd
import config

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

grading_mode_is_single = 0
single_level = None

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

    timeout = 0.32  # seconds
    timed = False
    readable = [mo, me]
    result = {mo: b'', me: b''}
    tm = time.time()
    try:
        while readable:
            if time.time() - tm > timeout:
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
    keys = get_level_names()
    ret = None
    for key in keys:
        print(key)
    while ret not in keys:
        ret = input("Which level would you like to grade? ")
    return ret

def prompt_grading(outs, good_outs, lvl, tests):
    while True:
        inp = input("[o]verview, [i]nspect a specific submission, [r]eturn to main menu, or [e]xit the grading program:  ")
        if inp == "o":
            print_overview(outs, good_outs, lvl)
        if inp == "i":
            prompt_inspect(outs, good_outs, tests, lvl)
        if inp == "r":
            return
        if inp == "e":
            exit()

def prompt_select_from_list_by_name(li):
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
        inp = input(f"Select an index between 0 and {l - 1}: ")
        try:
            inp = int(inp)
            if inp >= 0 and inp <= l - 1:
                return inp
        except:
            pass

def check_ok(submission_name, test_level, test_no):
    with open(config.OKFILE, "r") as okfile:
        ok_json = json.load(okfile)
    try:
        return ok_json[submission_name][f"{test_level}x{test_no}"]
    except:
        return None

def mark_ok_or_not(submission_name, test_level, test_no, okbool):
    with open(config.OKFILE, "r") as okfile:
        ok_json = json.load(okfile)
    if submission_name not in ok_json.keys():
        ok_json[submission_name] = {}
    ok_json[submission_name][f"{test_level}x{test_no}"] = 1 if okbool else 0
    with open(config.OKFILE, "w") as okfile:
        json.dump(ok_json, okfile)

def prompt_ok(submission, test_level, test_no):
    while True:
        inp = input("[c]ontinue and leave this test's status as it is, manually mark as [o]k, or manually mark as [n]ot ok ")
        if inp == "c":
            return
        if inp == "o":
            mark_ok_or_not(submission["name"], test_level, test_no, True)
            return
        if inp == "n":
            mark_ok_or_not(submission["name"], test_level, test_no, False)
            return

def do_comparison(selection, good_out, tests, level):
    print("which test would you like to compare?")
    i = prompt_list_index(tests)
    print("Which binary would you like to compare against?")
    comp = prompt_select_from_list_by_name(good_out)
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
    prompt_ok(selection, level, i)

def _prompt_inspect(selection, good_outs, tests, level):
    print(f"What would you like to do with submission '{selection['name']}'? ")
    print_single_overview(selection, good_outs, level)
    while True:
        inp = input("[v]iew output from a specific test, [c]ompare outputs against a known good version, [o]verview, [r]eturn to inspect a different submission, or [e]xit the grading program ")
        if inp == "v":
            ind = prompt_list_index(selection["test_outputs"])
            ind_out = selection["test_outputs"][ind]
            print_color(OKCYAN, f"test input:\t{bytes(tests[ind], 'UTF-8')}")
            print("Standard output:")
            print(f"\t{ind_out['stdout']}")
            print("Standard error:")
            print(f"\t{ind_out['stderr']}")
            print("Program timed out?")
            print(f"\t{ind_out['timeout']}")
            prompt_ok(selection, level, ind)
        if inp == "c":
            do_comparison(selection, good_outs, tests, level)
        if inp == "r":
            return
        if inp == "o":
            print_single_overview(selection, good_outs, level)
        if inp == "e":
            exit()

def prompt_inspect(outs, good_outs, tests, level):
    while True:
        print("Which submission would you like to inspect?")
        selection = prompt_select_from_list_by_name(outs)
        _prompt_inspect(selection, good_outs, tests, level)
        while True:
            inp = input(f"[i]nspect another submission, [r]eturn to level {level} main grading menu, or [e]xit the grading program ")
            if inp == "i":
                break
            if inp == "r":
                return
            if inp == "e":
                exit()

def find_goodness(output, good_outputs, submission_name, level, test_no):
    manual_ok = check_ok(submission_name, level, test_no)
    if manual_ok is not None:
        return ("manual", manual_ok)
    else:
        match = search_for_good_match(test_no, output, good_outputs)
        return ("automatic", match)

def print_goodness(goodness):
    if goodness[0] == "manual":
        if goodness[1] == 1:
            print_color(OKBLUE, f"Manually marked OK!")
        else:
            print_color(FAIL, f"{BOLD}Manually marked NOT OK!")
    elif goodness[0] == "automatic":
        if goodness[1] is None:
            print_color(FAIL, "Output did not match any known good outputs!")
        else:
            print_color(OKGREEN, f"Output matches with {goodness[1]}")

def print_single_overview(out, good_outs, level):
    i = 0
    print(f"binary name: {out['name']}")
    for test in out["test_outputs"]:
        goodness = find_goodness(test, good_outs, out["name"], level, i)
        print(f"\tTest #{i}: ", end="")
        print_goodness(goodness)
        i += 1

def print_overview(outs, good_outs, level):
    for out in outs:
        print_single_overview(out, good_outs, level)

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
    global grading_mode_is_single
    global single_level
    level = lvl if not grading_mode_is_single else single_level
    return [f"./{config.SUBMISSIONS_DIR}/{level}/{x}" for x in os.listdir(f"./{config.SUBMISSIONS_DIR}/{level}") if not x.startswith("good_")]

def load_good_bins(lvl):
    global grading_mode_is_single
    global single_level
    level = lvl if not grading_mode_is_single else single_level
    return [f"./{config.SUBMISSIONS_DIR}/{level}/{x}" for x in os.listdir(f"./{config.SUBMISSIONS_DIR}/{level}") if x.startswith("good_")]

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

def generate_report():
    with open(config.TESTSFILE, 'r') as testsfile:
        tests = json.load(testsfile)
    level_names = get_level_names()
    student_names = get_student_names()
    student_names.sort()
    student_names.append("possible_points")
    df = pd.DataFrame(index=student_names, columns=level_names)
    for level in tests:
        bins = load_bins(level)
        good_bins = load_good_bins(level)
        student_outs = run_bins(tests[level], bins)
        good_outs = run_bins(tests[level], good_bins)
        for sub in student_outs:
            i = 0
            level_score = 0.
            for output in sub["test_outputs"]:
                goodness = find_goodness(output, good_outs, sub["name"], level, i)
                if goodness[1] != None and goodness[1] != 0:
                    level_score += 1.
                i += 1
            df.at[sub["name"], level] = level_score
            df.at["possible_points", level] = i
    df = df.reindex(sorted(df.columns), axis=1)
    df = df.infer_objects(copy=False).fillna(0.)
    df.to_csv(f"{config.REPORT}")

def get_level_names():
    with os.scandir(config.SUBMISSIONS_DIR) as d:
        return [x.name for x in d]

def get_student_names():
    names_list = []
    for _, _, files in os.walk(config.SUBMISSIONS_DIR):
        for f in files:
            if f not in names_list and not f.startswith("good_"):
                names_list.append(f)
    return names_list


def add_test(tests_json, cur_lvl_name, new_test):
    tests_json[cur_lvl_name].append(new_test)
    with open(config.TESTSFILE, 'w') as testsfile:
        json.dump(tests_json, testsfile)

def do_new_tests(tests_json, cur_lvl_name):
    print("When writing tests, write \\n where you intend for there to be newline/enter character")
    while True:
        inp = input("Write a new test now, or enter just the character 'q' to quit the test maker:\n")
        if inp == 'q':
            return
        new_test = inp.replace("\\n", "\n")
        if not new_test.endswith("\n"):
            while True:
                inp = input("Your new test is missing a terminal newline character. Add one now? [y/n] (your test will likely time out without a terminal newline char) ")
                if inp == "y":
                    new_test += "\n"
                    break
                if inp == "n":
                    break
        add_test(tests_json, cur_lvl_name, new_test)

def prompt_new_tests(cur_lvl_name):
    with open(config.TESTSFILE, 'r') as testsfile:
        tests = json.load(testsfile)
    while True:
        inp = input("Would you like to write any new tests in this level? [y/n]: ")
        if inp == "y":
            do_new_tests(tests, cur_lvl_name)
        elif inp == "n":
            return

def prompt_intro():
    global grading_mode_is_single
    global single_level

    while True:
        inp = input(f"[g]rade submissions, generate a [r]eport, [t]oggle between single-/multi-binary grading mode (currently {'single' if grading_mode_is_single else 'multi'}), or [e]xit: ")
        if inp == "g":
            return
        elif inp == "r":
            generate_report()
        elif inp == "t":
            grading_mode_is_single = not grading_mode_is_single
            single_level = prompt_level()
        elif inp == "e":
            exit()

def make_empty_json_if_no_file(path):
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump({}, f)
            print_color(WARNING, f"File '{path}' did not exist. Empty JSON file created in its place")

# PRECONDITION: Before calling this, ensure the config.TESTSFILE exists.
def check_submissions_dir():
    if not os.path.exists(config.SUBMISSIONS_DIR):
        print_color(WARNING, f"Submissions directory '{config.SUBMISSIONS_DIR}' did not exist. This directory has now been created automatically.")
        print_color(WARNING, "Populate this directory before running kdlp test again.")
        os.makedirs(config.SUBMISSIONS_DIR)
        exit()
    with open(config.TESTSFILE, 'r') as testsfile:
        tests = json.load(testsfile)
    keys = list(tests.keys())
    with os.scandir(config.SUBMISSIONS_DIR) as d:
        for entry in d:
            if not entry.is_dir():
                print_color(FAIL, f"Error! Found non-directory file '{entry.name}' in {config.SUBMISSIONS_DIR}. Remove ALL non-directory files from {config.SUBMISSIONS_DIR}.")
                exit()
            try:
                keys.remove(entry.name)
            except:
                print_color(FAIL, f"Error! test level '{entry.name}' has no entry in {config.TESTSFILE}. "\
                "Ensure the testfile and the submissions directory have the same number of test levels and that the names are the same")
                exit()
        if not keys == []:
            plrl = len(keys) != 1
            print_color(FAIL, f"Error! The following test level{'s' if plrl else ''} {keys} {'have' if plrl else 'has'}"\
            f" no corresponding director{'ies' if plrl else 'y'} in '{config.SUBMISSIONS_DIR}'.")
            exit()

def preflight_checks():
    # Make sure tests file exists, OKFILE exists,
    # Make sure the submissions dir exists and isn't empty
    # Make sure test levels and submissions dir levels are equal
    make_empty_json_if_no_file(config.TESTSFILE)
    make_empty_json_if_no_file(config.OKFILE)
    check_submissions_dir()

def main():
    print("Welcome to the kdlp grading system!")
    preflight_checks()
    while True:
        prompt_intro()
        with open(config.TESTSFILE, 'r') as testsfile:
            tests = json.load(testsfile)
        lvl = prompt_level()
        prompt_new_tests(lvl)
        with open(config.TESTSFILE, 'r') as testsfile:
            tests = json.load(testsfile)
            bins = load_bins(lvl)
            good = load_good_bins(lvl)
            cur_tests = tests[lvl]
            print("OK! running tests...")
            outs = run_bins(cur_tests, bins)
            good_outs = run_bins(cur_tests, good)
            print("Tests complete!")
            prompt_grading(outs, good_outs, lvl, cur_tests)

if __name__ == '__main__':
    main()
