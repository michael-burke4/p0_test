import config
import os

from print_color import print_fail


def check_everything():
    if not dir_exists(config.GRADINGDIR):
        print_fail(f'Grading directory "{config.GRADINGDIR}" does not exist!')
        print_fail(f'Create this directory and populate the submissions '
                   f'directory ({config.SUBSDIR}) before running again...')
        return False
    if not dir_exists(config.SUBSDIR):
        print_fail(f'Submissions directory "{config.SUBSDIR}" does not exist!')
        print_fail('Create this directory and populate it before running '
                   'again...')
        return False
    return True


def dir_exists(path):
    return os.path.isdir(path)
