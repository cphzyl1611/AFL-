# Task 4 Dependencies

The supported delivery smoke is an offline Python 3.12 path. Its project
runtime uses the Python standard library; `requirements.txt` is intentionally
empty apart from its declaration comment. Test tooling and its direct wheel
dependencies are pinned in `requirements-dev.txt` (`pytest==9.1.1`). Optional live multipart execution
uses `requirements-live.txt` (`requests==2.32.4`) and is never installed or
started by the offline command.

On Ubuntu 24.04/WSL2, the native AFL++ smoke requires these system packages:

```text
build-essential   # gcc, make, libc development files
python3.12
python3.12-dev    # Python.h and libpython3.12
python3.12-venv
python3-pip
zlib1g-dev
coreutils          # timeout
```

The equivalent setup is `sudo apt-get install -y build-essential
python3.12-dev python3.12-venv python3-pip zlib1g-dev coreutils`. `python3`
must resolve to Python 3.12 for the tested environment. `python3-config
--embed` must be available; if a virtual environment does not provide a
wrapper, the guide uses the system tool without changing project code.

Optional tools are not part of the offline acceptance path: `curl` is used by
the loopback API smoke, `requests` is for the live multipart harness, Docker
is for externally managed platform deployment, and clang/LLVM are for optional
instrumentation modes. PyTorch, NumPy, pandas, and matplotlib are model or
analysis extras and are not required for the AFL++/validity/report smoke.

No O2OA or Alfresco credential is read by the offline commands. Live runs
must provide credentials through environment variables or an external
mode-0600 file; values must never be committed or placed in task/profile JSON.
