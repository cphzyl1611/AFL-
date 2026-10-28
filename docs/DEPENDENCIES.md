# Task 4 Dependencies

`pyproject.toml` is the authoritative Python dependency contract for
Deep2Fuzz-ES. The core package has no third-party runtime dependencies. Install
the CLI with `python -m pip install -e .`; add only the needed extras with
`deep2fuzz-es[dev]`, `[live]`, `[model]`, or `[analysis]`. The extras declare
pytest, requests, the NumPy/pandas/PyTorch model stack, and the pandas/matplotlib
analysis stack, respectively.

`requirements.txt`, `requirements-dev.txt`, and `requirements-live.txt` remain
compatibility installer exports for older project workflows. They are not
authoritative dependency declarations. The offline core path remains
standard-library-only; live and model extras are not installed or imported by
default.

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
