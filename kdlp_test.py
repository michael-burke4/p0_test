import errno
import json
import os
import pty
import select
import subprocess
import git

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

def main():
    file = open('tests.json')
    js = json.load(file)
    patch_dir = js['meta']['patches_dir']
    files = os.listdir(patch_dir)
    files.sort()
    patches = [patch_dir + x for x in files if (('.patch' in x or '.eml' in x) and 'cover-letter' not in x)]
    os.chdir(js['meta']['working_dir'])
    repo = git.Repo.init('.')
    level_no = 1
    for patch, level in zip(patches, js['levels']):
        repo.git.execute(['git', 'am', patch])
        test_no = 1
        for test in level:
            out, err = run_test(test)
            if out == bytes(test['expected'], 'UTF-8'):
                print('Level', level_no, 'Test', test_no, 'PASSED')
            else:
                print('Level', level_no, 'Test', test_no, 'FAILED: got', out, 'expected', bytes(test['expected'], 'UTF-8'))
            test_no += 1
        level_no += 1


if __name__ == '__main__':
    main()
