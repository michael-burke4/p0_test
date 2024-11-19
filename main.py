#!/usr/bin/env python3

import config
import os
import peewee

import db

from preflight_checks import check_everything
from print_color import print_fail, print_header, print_warning
from sm import Connection, State


level = None

db.db.connect()
db.db.create_tables(peewee.Model.__subclasses__(), safe=True)

if not check_everything():
    exit(1)


def select_level():
    global level
    while True:
        print_header('Select a level to grade... ')
        for f in os.listdir(config.SUBSDIR):
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
                inp = input('Your new test is missing a terminal newline '
                            'character. Add one now? [y/n] (your test will '
                            'likely timeout without a terminal newline char) ')
                if inp == 'y':
                    new_test += '\\n'
                    break
                if inp == 'n':
                    break
        if db.Test.get_or_none(test_text=new_test):
            print_warning('This is a duplicate test! Skipping...')
            continue
        db.Test.create(level=level, test_text=new_test)


begin = State()
level_select = State(action=select_level)
new_tests = State(action=add_tests)
end = State(action=exit)

q = Connection('[q]uit this program', end)
to_level_select = Connection('select a [l]evel to grade', level_select)
to_new_tests = Connection('add [n]ew tests to the current level', new_tests)

begin.add_connections([to_level_select, q])
level_select.add_connections([to_level_select, to_new_tests, q])
new_tests.add_connections([to_level_select, q])

cur_state = begin
while True:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
