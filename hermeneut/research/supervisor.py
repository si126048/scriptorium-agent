"""One local process entry point supervises API and worker without a second URL."""
import subprocess
import sys
import time


def start():
    children = []
    try:
        for command in ('serve', 'worker'):
            children.append(subprocess.Popen([sys.executable, '-m', 'hermeneut.research.cli', command]))
        while True:
            for child in children:
                code = child.poll()
                if code is not None:
                    raise RuntimeError(f'RESEARCH_CHILD_EXITED:{code}')
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
