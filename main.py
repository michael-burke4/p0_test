#!/usr/bin/env python3

import config
import errno
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

if not check_everything():
    exit(1)

db.db.connect()
db.db.create_tables(peewee.Model.__subclasses__(), safe=True)


def select_level():
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


def add_tests():
    global level
    if not db.Level.get_or_none(name=level):
        db.Level.create(name=level)
        print_warning(f'Level {level} did not exist in the grading db. '
                      'It has been added automatically.')
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
        T = db.Test
        sel = T.select().where(T.test_text == new_test).where(T.level == level)
        if sel.first():
            print_warning('This is a duplicate test! Skipping...')
            continue
        db.Test.create(level=level, test_text=new_test)


def print_tests():
    print_okblue(f'Here are all of the tests at level {level}')
    for t in db.Test.select().where(db.Test.level == level):
        print(f'\t{t.test_text}')


def show_level():
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
        print_warning(f'No known-good binaries were found in {leveldir}. '
                      'It will appear as though all submissions at this '
                      'level are wrong.')

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
    return [res[0].decode('utf-8'), res[1].decode('utf-8'), res[2]]


def run_all_tests():
    print_okcyan('This may take a while...')
    for level in sorted(os.listdir(config.SUBSDIR)):
        run_level_tests(level)


def print_level_report():
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
                print_okgreen(f'{prfx} output matches {res.good_match.submitter}')
            else:
                print_fail(f'{prfx} has no known-good matching output!')


begin = State('return to the [m]ain menu of this program')
level_select = State('select a [l]evel to grade', action=select_level)
at_level = State('[ret]urn to current level menu', action=show_level)
new_tests = State('add [n]ew tests to the current level', action=add_tests)
tests_printer = State('list all of the [tests] at the current level',
                      action=print_tests)
run_tests = State('[r]un all tests at this level against all binaries',
                  action=lambda: run_level_tests(level))
run_all_tests = State('run [all] tests at all levels against all binaries',
                      action=run_all_tests)
inspect_menu = State('[i]nspect grading status of the current level\'s '
                     'submissions')
level_report = State('print a [g]rade report for all submissions at the '
                     'current level', print_level_report)
end = State('[q]uit this program', stop=True)

begin.add_connections([level_select, run_all_tests, end])
level_select.add_connection(at_level)
at_level.add_connections([level_select, run_tests, new_tests, tests_printer,
                         inspect_menu, begin, end])
new_tests.add_connection(at_level)
tests_printer.add_connection(at_level)
run_tests.add_connection(at_level)
run_all_tests.add_connection(begin)
inspect_menu.add_connections([level_report, at_level, end])
level_report.add_connection(inspect_menu)

cur_state = begin
while not cur_state.stop:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
