"""Isolated, bounded Linux process-tree fixture for termination contract tests."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import deep2fuzz_portability as portability
from integration.platforms.core_runner import _terminate_process_group


def node(directory: Path, depth: int, mode: str, detached: bool) -> None:
    ignore = mode == 'ignore' or mode == 'child_ignores' and depth > 0
    signal.signal(signal.SIGTERM, signal.SIG_IGN if ignore else signal.SIG_DFL)
    levels = int((directory / 'levels').read_text(encoding='utf-8'))
    if depth + 1 < levels:
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__)), '--node', str(directory),
             str(depth + 1), mode, str(int(detached))],
            start_new_session=detached and depth == 0,
        )
    record = {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgrp(),
              'sid': os.getsid(0), 'depth': depth}
    (directory / f'{depth}.json').write_text(json.dumps(record), encoding='utf-8')
    while True:
        signal.pause()


def state(pid: int) -> str:
    try:
        return Path(f'/proc/{pid}/stat').read_text(encoding='utf-8').rsplit(') ', 1)[1].split()[0]
    except FileNotFoundError:
        return 'ABSENT'


def run(case: str, destination: Path) -> dict:
    # Only this short-lived fixture becomes a subreaper; pytest's process state
    # is untouched. This allows finally to reap even intentionally orphaned nodes.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'fixture subreaper unavailable')
    levels = 3 if case in {'grandchild', 'detached'} else 2
    mode = 'graceful' if case == 'graceful' else 'child_ignores' if case == 'leader_exits' else 'ignore'
    result = {'case': case, 'network': 'NONE', 'nodes': [], 'returned_success': False}
    with tempfile.TemporaryDirectory(prefix='p3-tree-') as temp:
        directory = Path(temp)
        (directory / 'levels').write_text(str(levels), encoding='utf-8')
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__)), '--node', str(directory), '0', mode,
             str(int(case == 'detached'))],
            start_new_session=case != 'unisolated', stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        original_killpg = os.killpg
        original_system = portability.platform_module.system
        original_kill = process.kill
        saved_signal = None
        try:
            deadline = time.monotonic() + 5.0
            while len(list(directory.glob('*.json'))) < levels:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('fixture readiness deadline')
                time.sleep(0.005)
            result['nodes'] = [json.loads((directory / f'{depth}.json').read_text(encoding='utf-8'))
                               for depth in range(levels)]
            if case == 'parent_only_bug':
                def parent_only(group, signum):
                    if signum == signal.SIGKILL:
                        return os.kill(group, signum)
                    return original_killpg(group, signum)
                portability.os.killpg = parent_only
            elif case == 'force_ineffective':
                portability.os.killpg = lambda group, signum: (
                    None if signum == signal.SIGKILL else original_killpg(group, signum))
                process.kill = lambda: None
            elif case == 'signal_denied':
                def denied(group, signum):
                    raise PermissionError('fixture denied group signal')
                portability.os.killpg = denied
            elif case == 'windows':
                portability.platform_module.system = lambda: 'Windows'
            elif case == 'missing_signal':
                saved_signal = signal.SIGKILL
                delattr(portability.signal, 'SIGKILL')
            started = time.monotonic()
            try:
                if case == 'cleanup_assertion':
                    raise AssertionError('intentional fixture consumer failure')
                if case in {'parent_only_bug', 'force_ineffective'}:
                    value = portability.terminate_process(process, grace_seconds=0.1, force_seconds=0.2)
                else:
                    value = _terminate_process_group(process, grace_seconds=0.1)
                result.update({'returned_success': True, 'escalated': value[2] if isinstance(value, tuple) else value})
            except Exception as exc:
                result.update({'error_type': type(exc).__name__, 'error': str(exc), 'caller_verdict': 'FAIL'})
            result['elapsed_seconds'] = time.monotonic() - started
            result['states_after_api'] = {str(item['pid']): state(item['pid']) for item in result['nodes']}
            result['live_after_api'] = [pid for pid, status in result['states_after_api'].items()
                                        if status not in {'ABSENT', 'Z', 'X'}]
        finally:
            portability.os.killpg = original_killpg
            portability.platform_module.system = original_system
            process.kill = original_kill
            if saved_signal is not None:
                portability.signal.SIGKILL = saved_signal
            known = result['nodes'] or [json.loads(p.read_text(encoding='utf-8'))
                                        for p in directory.glob('*.json')]
            if case != 'unisolated':
                try:
                    original_killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for item in known:
                try:
                    os.kill(item['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                for item in known:
                    try:
                        os.waitpid(item['pid'], os.WNOHANG)
                    except ChildProcessError:
                        pass
                if all(state(item['pid']) == 'ABSENT' for item in known):
                    break
                time.sleep(0.005)
            result['states_after_cleanup'] = {str(item['pid']): state(item['pid']) for item in known}
            result['orphan_count'] = sum(status != 'ABSENT' for status in result['states_after_cleanup'].values())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    if sys.argv[1] == '--node':
        node(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4], bool(int(sys.argv[5])))
    else:
        print(json.dumps(run(sys.argv[1], Path(sys.argv[2])), sort_keys=True))
