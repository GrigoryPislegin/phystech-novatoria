"""Prove graceful Docker shutdown after the real HTTP server becomes ready."""
import argparse
import json
import subprocess
import time
import uuid


def run(*args, check=True):
    return subprocess.run(['docker', *args], check=check, capture_output=True, text=True, timeout=30)


def check(image):
    name = 'recruiter-stop-check-' + uuid.uuid4().hex
    run('run', '-d', '--name', name, '--network', 'none', image)
    try:
        deadline = time.monotonic() + 15
        while True:
            ready = run('exec', name, 'python', '-c',
                "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/api/session', timeout=2).close()",
                check=False)
            if ready.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('container_not_ready')
            time.sleep(.1)
        run('stop', '-t', '3', name)
        code = run('inspect', '-f', '{{.State.ExitCode}}', name).stdout.strip()
        if code != '0':
            raise RuntimeError('container_stop_exit_' + code)
        print(json.dumps({'status': 'pass', 'container_exit_code': 0, 'network': 'none'}))
    finally:
        run('rm', '-f', name, check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='recruiter-ci')
    args = parser.parse_args()
    check(args.image)
