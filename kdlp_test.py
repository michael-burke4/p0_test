import errno
import json
import os
import pty
import select
import subprocess
import git
import shutil

# this function is courtesy of
# https://stackoverflow.com/a/52954716
def tty_capture(cmd, bytes_input, output_bytes=512):
    # Capture the output of cmd with bytes_input to stdin,
    # with stdin, stdout and stderr as TTYs.
    # Based on Andy Hayden's gist:
    # https://gist.github.com/hayd/4f46a68fc697ba8888a7b517a414583e
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

    timeout = 0.04  # seconds
    readable = [mo, me]
    result = {mo: b'', me: b''}
    try:
        while readable:
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
                    if not data: # EOF
                        readable.remove(fd)
                    result[fd] += data
    finally:
        for fd in [mo, me, mi]:
            os.close(fd)
        if p.poll() is None:
            p.kill()
        p.wait()
    return result[mo], result[me]

def run_test(test):
    return tty_capture(test['args'], bytes(test['input'], 'UTF-8'))

def clean_cur_dir():
    for file in os.scandir():
        if file.is_file():
            os.remove(file)
        else:
            shutil.rmtree(file)

def check_repo_exists(directory):
    inpt = 0
    if os.listdir() != []:
        while inpt != 'y' and inpt != 'n':
            inpt = input("WARNING: %s is not empty. Remove all files and directories in %s? [y/n]: " % (directory, directory))
        if inpt == 'y':
            clean_cur_dir()



def main():
    file = open('tests.json')
    js = json.load(file)
    working_dir = js['meta']['working_dir']
    os.chdir(working_dir)

    check_repo_exists(working_dir)

    repo = git.Repo.init('.')


    level_no = 0
    for level in js['levels']:
        while True:
            inp = input("Apply patches until level %d is complete. `h`elp, `c`ontinue, `a`bort, or `e`xit: " % level_no)
            if inp == 'a':
                return
            elif inp == 'e':
                clean_cur_dir()
                return
            elif inp == 'h':
                print("CONTINUE: Patches for the current level have been applied, proceed to run the tests for that level.")
                print("ABORT: Exit the program, perform no further tests, Will not delete any files in the testing directory.")
                print("EXIT: Exit the program, perform no further tests, and completely clean the testing directory.")
                break
            elif inp == 'c':
                break

        test_no = 0
        passed = 0
        for test in level:
            out, err = run_test(test)
            if out == bytes(test['expected'], 'UTF-8'):
                print('Level', level_no, 'Test', test_no, 'PASSED')
                passed += 1
            else:
                print('Level', level_no, 'Test', test_no, 'FAILED: got', out, 'expected', bytes(test['expected'], 'UTF-8'))
            test_no += 1
        level_no += 1
        print("LEVEL %d %d/%d PASSED" % (level_no, passed, test_no))


    done = 0
    while done != 'y' and done != 'n':
        done = input("Testing finished. Remove all files and directories in %s? [y/n]: " % (working_dir))
    if done == 'y':
        clean_cur_dir()
    return

if __name__ == '__main__':
    main()
