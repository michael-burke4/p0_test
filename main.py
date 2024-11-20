#!/usr/bin/env python3

import config
import os
import peewee

import db

from preflight_checks import check_everything
from print_color import print_fail, print_header, print_warning, print_okblue
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
        if db.Test.get_or_none(test_text=new_test):
            print_warning('This is a duplicate test! Skipping...')
            continue
        db.Test.create(level=level, test_text=new_test)


def print_tests():
    print_okblue(f'Here are all of the tests at level {level}')
    for t in db.Test.select().where(db.Test.level == level):
        print(f'\t{t.test_text}')


def show_level():
    print_header(f'Currently selected level: {level}')


begin = State('return to the [m]ain menu of this program')
level_select = State('select a [l]evel to grade', action=select_level)
at_level = State('[v]iew possible actions at current level', action=show_level)
new_tests = State('add [n]ew tests to the current level', action=add_tests)
tests_printer = State('list all of the [tests] at the current level',
                      action=print_tests)
end = State('[q]uit this program', stop=True)

begin.add_connections([level_select, end])
level_select.add_connection(at_level)
at_level.add_connections([level_select, new_tests, tests_printer, end])
new_tests.add_connection(at_level)
tests_printer.add_connection(at_level)

cur_state = begin
while not cur_state.stop:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
