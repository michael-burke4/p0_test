#!/usr/bin/env python3

import config
import errno
import json
import os
import peewee
import pty
import select
import subprocess
import time

import db

from preflight_checks import check_everything
from print_color import (print_fail, print_header, print_warning, print_okblue,
                         print_okcyan, print_okgreen)
from sm import State


level = None
user = None

if not check_everything():
    exit(1)

db.db.connect()
db.db.create_tables(peewee.Model.__subclasses__(), safe=True)


def do_select_level():
    global level
    while True:
        print_header('Select a level to grade... ')
        for f in sorted(os.listdir(config.SUBSDIR)):
            print(f'\t{f}')
        inp = input('')
        if inp in os.listdir(config.SUBSDIR):
            level = inp
            print(f'Proceeding to grade level {level}...')
            break
        else:
            print_fail(f'{inp} not in {config.SUBSDIR}')


def do_write_tests():
    global level
    print('When writing tests, write \\n where you intend for there to be a '
          'newline/enter character')
    while True:
        new_test = input('Write a new test now, or enter just the character '
                         '"q" to quit the test maker:\n')
        if new_test == 'q':
            return
        if not new_test.endswith('\\n'):
            while True:
                print_warning('Your new test is missing a terminal newline '
                              'character. Add one now? [y/n] (your test will '
                              'likely timeout without a terminal newline '
                              'char) ', end='')
                inp = input()
                if inp == 'y':
                    new_test += '\\n'
                    break
                if inp == 'n':
                    break
        add_test(level, new_test)


def add_test(lev, txt):
    if not db.Test.get_or_create(level=lev, test_text=txt)[1]:
        print_warning('Duplicate test! Skipping...')


def do_print_tests():
    print_okblue(f'Here are all of the tests at level {level}')
    for t in db.Test.select().where(db.Test.level == level):
        print(f'\t{t.test_text}')


def do_current_level():
    print_header(f'Currently selected level: {level}')


# Capture the output of cmd with bytes_input to stdin,
# with stdin, stdout and stderr as TTYs.
# From Andy Hayden's capture_tty.py:
# https://gist.github.com/hayd/4f46a68fc697ba8888a7b517a414583e:
def tty_capture(cmd, bytes_input, output_bytes=2048):
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
                    if not data:  # EOF
                        readable.remove(fd)
                    result[fd] += data
    finally:
        for fd in [mo, me, mi]:
            os.close(fd)
        if p.poll() is None:
            p.kill()
        p.wait()
    return result[mo], result[me], timed


def create_submitter_if_needed(name):
    S = db.Submitter
    if not S.get_or_none(db.Submitter.name == name):
        S.create(name=name,
                 known_good='t' if name.startswith('good_') else 'f')


def run_level_tests(lev):
    leveldir = f'{config.SUBSDIR}/{lev}'
    names = os.listdir(leveldir)

    if len(names) == 0:
        print_fail(f'There are no binaries in {leveldir}. Populate this '
                   'directory before trying again.')
        return

    tests_q = db.Test.select().where(db.Test.level == lev)
    if tests_q.count() == 0:
        print_fail(f'There are no tests at level {lev}')
        return

    good_names = [n for n in names if n.startswith('good_')]
    if len(good_names) == 0:
        print_fail(f'No known-good binaries were found in {leveldir}.')
        return

    for name in good_names:
        create_submitter_if_needed(name)
        for test in tests_q:
            res = db.Result.get_or_create(submitter=name, level=lev, test=test)[0]  # NOQA: 501
            out = run_test(f'{leveldir}/{name}',
                           test.test_text.replace('\\n', '\n'))
            res.stdout, res.stderr, res.timedout = out
            res.save()

    good_rs = (db.Result.select()
                        .join(db.Submitter)
                        .switch()
                        .join(db.Test, peewee.JOIN.LEFT_OUTER)
                        .where(db.Result.submitter.known_good == 't'))

    for name in [n for n in names if not n.startswith('good_')]:
        create_submitter_if_needed(name)
        for test in tests_q:
            res = db.Result.get_or_create(submitter=name, level=lev, test=test)[0] # NOQA: 501
            out = run_test(f'{leveldir}/{name}',
                           test.test_text.replace('\\n', '\n'))
            res.stdout, res.stderr, res.timedout = out
            res.save()
            test_good_rs = good_rs.where(db.Result.test == test)
            g_match = (test_good_rs.where(db.Result.stdout == res.stdout)
                                   .where(db.Result.stderr == res.stderr)
                                   .where(db.Result.timedout == res.timedout)
                                   .first())
            res.good_match = g_match
            res.save()


def run_test(bin_path, test):
    res = tty_capture(bin_path, bytes(test, 'utf-8'))

    def clean(s):
        return s.decode('utf-8').replace('\r\n', '\\n').replace('\n', '\\n')

    return [clean(res[0]), clean(res[1]), res[2]]


def do_run_all_tests():
    print_okcyan('This may take a while...')
    for level in sorted(os.listdir(config.SUBSDIR)):
        run_level_tests(level)


def do_level_report():
    q = db.Submitter.select().where(db.Submitter.known_good == 'f')
    for u in q:
        print(u.name)
        results = u.results.select().where(db.Result.level == level)
        if results.count() == 0:
            print_fail('\tNo submission!')
            continue
        for res in results:
            prfx = f'\tTest id {res.test}:'
            if res.good_match:
                print_okgreen(f'{prfx} output matches '
                              f'{res.good_match.submitter}')
            else:
                print_fail(f'{prfx} has no known-good matching output!')


def pick_a_user():
    global user
    q = db.Submitter.select().where(db.Submitter.known_good == 'f')
    print_header('Pick a user from the following list...')
    for u in q:
        print(u.name)

    while True:
        prompted = input('Make a selction... ')
        if sel := q.where(db.Submitter.name == prompted).first():
            user = sel.name
            print_okgreen(f'Selected {user}')
            break
        print('Selected user was not in the above list! Try again...')


def inspect_user(usr, lev):
    print_header(f'Inspecting {usr}')
    l_ts = db.Level.get_or_none(name=lev).tests
    if l_ts.count() == 0:
        print_fail('No tests at this level! Nothing to inspect...')
        return
    for t in l_ts:
        print_report(usr, t)


def print_report(usr, test):
    usr_t_res = (db.Result.select()
                          .where(db.Result.test == test)
                          .where(db.Result.submitter == usr)
                          .first())
    print_okblue(f'\tTest input: {test.test_text}')
    if not usr_t_res:
        print_fail('\t\tNo results for this test! Maybe re-run tests at '
                   f'level {test.level}?')
        return
    print(f'\t\tstdout: {usr_t_res.stdout}')
    print(f'\t\tstderr: {usr_t_res.stderr}')
    print(f'\t\ttimed out: {usr_t_res.timedout}')
    if m := usr_t_res.good_match:
        print_okgreen(f'\t\tOutput matches the output of {m.submitter}')
    else:
        print_fail('\t\tMatches no known-good outputs!')


def do_inspect_specific_user():
    pick_a_user()
    inspect_user(user, level)


def do_import_tests():
    inp = input('Enter the path to the json file containing your tests: ')
    with open(inp) as f:
        tests_json = json.load(f)
    for lev in tests_json:
        for t in tests_json[lev]:
            add_test(lev, t.replace('\r\n', '\\n').replace('\n', '\\n'))


def do_export_tests():
    inp = input('Enter the path to export to: ')
    out = {}
    levs = db.Level.select()
    for lev in levs:
        out[lev.name] = []
        for t in lev.tests:
            out[lev.name].append(t.test_text.replace('\\n', '\n'))
    with open(inp, 'w') as f:
        json.dump(out, f)


begin = State('[m]ain menu of this program')
select_level = State('[l]evel selection', action=do_select_level)
current_level = State('[c]urrent level menu', action=do_current_level)
write_tests = State('[n]ew test creation at current level',
                    action=do_write_tests)
print_tests = State('[tests] list at current level',
                    action=do_print_tests)
run_tests = State('[r]un all tests at this level against all binaries',
                  action=lambda: run_level_tests(level))
run_all_tests = State('[run all] tests at all levels against all binaries',
                      action=do_run_all_tests)
inspect_menu = State('[i]nspect grading status of the current level\'s '
                     'submissions')
level_report = State('[o]verview for all submissions at the '
                     'current level', do_level_report)
inspect_specific_user = State('[v]iew a specific user\'s test outputs',
                              action=do_inspect_specific_user)
import_tests = State('[im]port new tests', action=do_import_tests)
export_tests = State('[ex]port tests to json', action=do_export_tests)
end = State('[q]uit this program', stop=True)

begin.add_connections([select_level, run_all_tests, import_tests, export_tests,
                       end])
select_level.add_connection(current_level)
current_level.add_connections([select_level, run_tests, write_tests,
                              print_tests, inspect_menu, begin, end])
write_tests.add_connection(current_level)
print_tests.add_connection(current_level)
run_tests.add_connection(current_level)
run_all_tests.add_connection(begin)
inspect_menu.add_connections([level_report, inspect_specific_user,
                             current_level, end])
inspect_specific_user.add_connection(inspect_menu)
level_report.add_connection(inspect_menu)
import_tests.add_connection(begin)
export_tests.add_connection(begin)

cur_state = begin
while not cur_state.stop:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
