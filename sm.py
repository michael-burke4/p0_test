import re

from print_color import print_fail


class Connection:
    def __init__(self, cmd_string, to_state, action=None, clear_from=False):
        self.cmd_string = cmd_string
        self.letter = self.extract_command_letter()
        self.to_state = to_state
        self.action = action
        self.clear_from = clear_from

    def extract_command_letter(self):
        pat = r'\[(.)\]'
        matches = re.findall(pat, self.cmd_string)
        if (le := len(matches)) != 1:
            raise BufferError('Command string expects exactly 1 specifier'
                              f'letter of the form [c]. Got {le}')
        return matches[0]

    def act(self):
        if self.action:
            return self.action()
        return None

    def __str___(self):
        return self.cmd_string


class State:
    def __init__(self, connections=None):
        self.connections = {}
        self.add_connections(connections)
        self.data = None

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

    def clear_data(self):
        self.data = None

    def recieve_data(self, data):
        if data:
            self.data = data

    def prompt_connection(self):
        i = None
        while True:
            print('Available actions:')
            for c in self.connections:
                print(self.connections[c].cmd_string)
            i = input('Select an action to perform... ')
            con = None
            try:
                con = self.connections[i]
            except KeyError:
                print_fail(f'Input "{i}" is not in the above actions list.'
                           'Try again.')
                continue
            return self.__connect(con)

    def __connect(self, con):
        con.to_state.recieve_data(con.act())
        if con.clear_from:
            self.clear_data()
        return con.to_state
