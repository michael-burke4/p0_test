import re

from print_color import print_fail, print_header


class State:
    def __init__(self, command_string, action=None, stop=False):
        self.command_string = command_string
        self.prompt_sequence = self.extract_prompt_sequence()
        self.action = action
        self.stop = stop
        self.connections = {}

    def add_connections(self, states):
        for s in states:
            self.add_connection(s)

    def add_connection(self, state):
        if state.prompt_sequence in self.connections.keys():
            raise KeyError('Attempted to use duplicate prompt '
                           f'sequence "{state.prompt_sequence}"')
        self.connections[state.prompt_sequence] = state

    def prompt_connection(self):
        if len(self.connections) == 0:
            raise KeyError('Attempted to prompt a connection for a state '
                           'with no connections.')
        if len(self.connections) == 1:
            return self.connections[next(iter(self.connections))]
        inp = None
        while True:
            print_header('Available:')
            for s in self.connections:
                print(f'\t{self.connections[s].command_string}')
            inp = input('Proceed to... ')
            con = None
            try:
                con = self.connections[inp]
            except KeyError:
                print_fail(f'Input "{inp}" is not in the above actions list.'
                           'Try again.')
                continue
            return con

    def arrive(self):
        if self.action:
            self.action()

    def extract_prompt_sequence(self):
        pat = r'\[(.+)\]'
        matches = re.findall(pat, self.command_string)
        if (le := len(matches)) != 1:
            raise BufferError('Command string expects exactly 1 specifier'
                              f'letter of the form [c]. Got {le}')
        return matches[0]
