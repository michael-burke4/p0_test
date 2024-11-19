import re

from print_color import print_fail, print_header


class Connection:
    def __init__(self, cmd_string, to_state):
        self.cmd_string = cmd_string
        self.letter = self.extract_command_letter()
        self.to_state = to_state

    def extract_command_letter(self):
        pat = r'\[(.+)\]'
        matches = re.findall(pat, self.cmd_string)
        if (le := len(matches)) != 1:
            raise BufferError('Command string expects exactly 1 specifier'
                              f'letter of the form [c]. Got {le}')
        return matches[0]

    def __str___(self):
        return self.cmd_string


class State:
    def __init__(self, action=None, connections=None, stop=False):
        self.connections = {}
        self.action = action
        self.add_connections(connections)
        self.stop = stop

    def add_connections(self, connections):
        if not connections:
            return
        for connection in connections:
            self.add_connection(connection)

    def add_connection(self, connection):
        if connection.letter in self.connections.keys():
            raise KeyError('Attempted to use duplicate connection '
                           f'letter "{connection.letter}"')
        self.connections[connection.letter] = connection

    def prompt_connection(self):
        if len(self.connections) == 1:
            return self.connections[next(iter(self.connections))].to_state
        i = None
        while True:
            print_header('Available actions:')
            for c in self.connections:
                print(f'\t{self.connections[c].cmd_string}')
            i = input('Select an action to perform... ')
            con = None
            try:
                con = self.connections[i]
            except KeyError:
                print_fail(f'Input "{i}" is not in the above actions list.'
                           'Try again.')
                continue
            return con.to_state

    def arrive(self):
        if self.action:
            self.action()
