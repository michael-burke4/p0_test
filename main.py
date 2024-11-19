#!/usr/bin/env python3

from sm import Connection, State


def print_hi():
    print('hi!')


if __name__ == '__main__':
    quit_state = State()
    s1 = State()
    s2 = State()
    qt = Connection('[q]uit this program', quit_state, action=exit)
    one = Connection('state [1]', s1)
    two = Connection('state [2]', s2, action=print_hi)

    s1.add_connections([two, qt])
    s2.add_connections([one, qt])

    cur_state = s1

    while True:
        cur_state = cur_state.prompt_connection()
