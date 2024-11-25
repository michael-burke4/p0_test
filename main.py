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

from print_color import (print_fail, print_header, print_warning, print_okblue,
                         print_okcyan, print_okgreen)
from sm import State


if not os.path.isdir(config.GRADINGDIR):
    print_fail(f'Grading directory "{config.GRADINGDIR}" does not exist!')
    print_fail(f'Create this directory and populate the submissions '
               f'directory ({config.SUBSDIR}) before running again...')
    exit(1)

if not os.path.isdir(config.SUBSDIR):
    print_fail(f'Submissions directory "{config.SUBSDIR}" does not exist!')
    print_fail('Create this directory and populate it before running '
               'again...')
    exit(1)

if len(os.listdir(config.SUBSDIR)) == 0:
    print_fail(f'Submissions directory "{config.SUBSDIR}" is empty!')
    print_fail('Populate this directory before running again...')
    exit(1)


level = None
user = None


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
            db.Level.get_or_create(name=level)
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
        print(f'id:{t.id}\t{t.test_text}')


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
    exit_code = None
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
        exit_code = p.wait()
    return result[mo], result[me], timed, exit_code


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

    for name in names:
        db.Submitter.get_or_create(name=name)
        for test in tests_q:
            if db.Result.get_or_none(level=level, submitter=name, test=test):
                continue
            res = db.Result.get_or_create(submitter=name, level=lev, test=test)[0] # NOQA: 501
            out = run_test(f'{leveldir}/{name}',
                           test.test_text.replace('\\n', '\n'))
            res.stdout, res.stderr, res.timedout, res.exit_code = out
            res.save()
    print_okcyan("Done!")


def run_test(bin_path, test):
    res = tty_capture(bin_path, bytes(test, 'utf-8'))

    def clean(s):
        return s.decode('utf-8').replace('\r\n', '\\n').replace('\n', '\\n')

    return [clean(res[0]), clean(res[1]), res[2], res[3]]


def do_grade_level():
    R = db.Result
    res_at_lev = (R.select()
                   .where(R.level == level))
    tests = db.Level.get_or_none(name=level).tests
    for t in tests:
        u_at_t = res_at_lev.where(R.test == t)
        for r in u_at_t:
            if r.okness:
                continue
            print_report(r.submitter, t)
            mtch = (u_at_t.select()
                          .where(R.submitter != r.submitter)
                          .where(R.stdout == r.stdout)
                          .where(R.stderr == r.stderr)
                          .where(R.timedout == r.timedout)
                          .where(R.exit_code == r.exit_code))
            okmtch = mtch.where((R.okness == 'manual_ok') | (r.okness == 'match_ok')).first()  # NOQA: 501
            nokmtch = mtch.where((R.okness == 'manual_not_ok') | (r.okness == 'match_not_ok')).first()  # NOQA: 501
            if okmtch:
                if nokmtch:
                    print_fail('Result has both an OK and a Not Ok match!')
                else:
                    r.okness = 'match_ok'
                    r.out_match = okmtch
                    r.save()
                    print_okgreen(f'Found an existing OK match: {okmtch}. '
                                  'Automatically marking as ok...')
                    continue
            elif nokmtch:
                r.okness = 'match_not_ok'
                r.out_match = nokmtch
                r.save()
                print_fail(f'Found an existing not ok match: {okmtch}. '
                           'Automatically marking as not ok...')
                continue
            while True:
                print_header('[o]k, [n]ot ok, [s]kip for now, or [e]xit '
                             'this grading menu: ')
                inp = input()
                if inp == 'o':
                    r.okness = 'manual_ok'
                    r.save()
                    break
                elif inp == 'n':
                    r.okness = 'manual_not_ok'
                    r.save()
                    break
                elif inp == 's':
                    break
                elif inp == 'e':
                    return
    print_okcyan("Done!")


def do_run_all_tests():
    print_okcyan('This may take a while...')
    for level in sorted(os.listdir(config.SUBSDIR)):
        run_level_tests(level)


def do_level_report():
    q = db.Submitter.select()
    for u in q:
        print(u.name)
        results = u.results.select().where(db.Result.level == level)
        if results.count() == 0:
            print_fail('\tNo submission!')
            continue
        for res in results:
            prfx = f'\tTest id {res.test}, Result id {res.id}:'
            if res.okness == 'manual_ok':
                print_okgreen(f'{prfx} manually marked as ok')
            elif res.okness == 'manual_not_ok':
                print_fail(f'{prfx} manually marked as NOT ok')
            elif res.okness == 'match_ok':
                print_okgreen(f'{prfx} automatically marked as ok')
            elif res.okness == 'match_not_ok':
                print_fail(f'{prfx} automatically marked as NOT ok')
            else:
                print_warning(f'{prfx} ungraded!')


def pick_a_user():
    global user
    q = db.Submitter.select()
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
    print_okblue(f'Test input: {test.test_text}')
    if not usr_t_res:
        print_fail('No results for this test! Maybe re-run tests at '
                   f'level {test.level}?')
        return
    print(f'\tSubmitter: {usr_t_res.submitter}')
    print(f'\tResult ID:{usr_t_res.id}')
    print(f'\tstdout: {usr_t_res.stdout}')
    print(f'\tstderr: {usr_t_res.stderr}')
    print(f'\texit code: {usr_t_res.exit_code}')
    print(f'\ttimed out: {usr_t_res.timedout}')
    if usr_t_res.okness.startswith('match_'):
        print(f'\tOutput matches result with id {usr_t_res.out_match}')
    if usr_t_res.okness == 'manual_ok' or usr_t_res.okness == 'match_ok':
        print_okgreen(f'\tokness: {usr_t_res.okness}')
    elif not usr_t_res.okness:
        print_warning('\tUngraded!')
    else:
        print_fail(f'\tokness: {usr_t_res.okness}')


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


def do_okness():
    while True:
        print_header('Input the result ID of the result to mark as not-ok: ',
                     end='')
        inp = input()

        if r := db.Result.get_or_none(id=inp):
            break
    while True:
        print_header('Mark as [ok]/[not] ok/[rem]ove manual ok mark: ', end='')
        inp = input()
        if inp == 'ok':
            r.okness = 'ok'
            break
        elif inp == 'not':
            r.okness = 'not_ok'
            break
        elif inp == 'rem':
            r.okness = None
            break
        elif inp == 'c':
            return
    r.save()


def do_remove_tests():
    while True:
        do_print_tests()
        print_header('Input the ID of the test to remove (or [c]ancel:) ')
        print_warning('WARNING: this will also delete all results '
                      'for this test!')
        inp = input()
        if inp == 'c':
            return

        if r := db.Test.get_or_none(id=inp):
            (db.Result.delete()
                      .where(db.Result.test == r)
                      .execute())
            r.delete_instance()


begin = State('[m]ain menu of this program')
select_level = State('[l]evel selection', action=do_select_level)
current_level = State('[c]urrent level menu', action=do_current_level)
write_tests = State('[n]ew test creation at current level',
                    action=do_write_tests)
remove_tests = State('[rem]ove tests', action=do_remove_tests)
print_tests = State('[tests] list at current level',
                    action=do_print_tests)
run_tests = State('[r]un tests at this level against binaries where results '
                  'don\'t exist yet', action=lambda: run_level_tests(level))
grade_level = State('[g]rade results at this level', action=do_grade_level)
run_all_tests = State('[run all] tests at all levels against all binaries',
                      action=do_run_all_tests)
view_menu = State('[v]iew grading results at the current level')
level_report = State('[o]verview for all submissions at the '
                     'current level', do_level_report)
inspect_specific_user = State('[i]spect a specific user\'s test outputs',
                              action=do_inspect_specific_user)
import_tests = State('[im]port new tests', action=do_import_tests)
export_tests = State('[ex]port tests to json', action=do_export_tests)
okness = State('[ok] mark a result as ok/not ok', action=do_okness)
end = State('[q]uit this program', stop=True)


begin.add_connections([select_level, run_all_tests, import_tests, export_tests,
                       end])
run_all_tests.add_connection(begin)
grade_level.add_connection(current_level)
import_tests.add_connection(begin)
export_tests.add_connection(begin)

select_level.add_connection(current_level)
current_level.add_connections([run_tests, grade_level, view_menu,
                              write_tests, remove_tests, print_tests,
                              select_level, begin, end])
write_tests.add_connection(current_level)
remove_tests.add_connection(current_level)
print_tests.add_connection(current_level)
run_tests.add_connection(current_level)
view_menu.add_connections([level_report, inspect_specific_user,
                          okness, current_level, end])
inspect_specific_user.add_connection(view_menu)
level_report.add_connection(view_menu)
okness.add_connection(view_menu)

cur_state = begin
while not cur_state.stop:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
