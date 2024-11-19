#!/usr/bin/env python3

import config
import os

from print_color import print_fail, print_header
from sm import Connection, State


level = None


def select_level():
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


begin = State()
level_select = State(action=select_level)
end = State(action=exit)

q = Connection('[q]uit this program', end)
to_level_select = Connection('select a [l]evel to grade', level_select)

begin.add_connections([to_level_select, q])
level_select.add_connections([to_level_select, q])

cur_state = begin
while True:
    cur_state.arrive()
    cur_state = cur_state.prompt_connection()
