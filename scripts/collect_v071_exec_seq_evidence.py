#!/usr/bin/env python3
"""Collect curated evidence for the v0.7.1 real-harness exec_seq upgrade.

Runs the real ``nv_http_harness.py`` as a separate process per execution --
exactly how AFL++ runs it -- against a local deterministic HTTP server, and
drives the real C replay consumer over the documents it produced.

    python3 scripts/collect_v071_exec_seq_evidence.py [--out out/v071_exec_seq]

Nothing here contacts a real O2OA, Alfresco or Flowable service.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.test_v071_exec_seq import (  # noqa: E402
    LocalServer,
    free_port,
    read_status,
    run_harness,
    write_config,
)
from tests.test_v071_platform_chains import redirect  # noqa: E402

SEED = b'POST /api/doc/query HTTP/1.1\r\n\r\n{"k":"v"}'

BOUNDARY = (
    "local deterministic HTTP server on 127.0.0.1; real nv_http_harness.py; "
    "not a platform experiment; not a real O2OA/Alfresco/Flowable service"
)


def jdump(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# --------------------------------------------------------------------------


def writer_matrix(out: Path) -> list[dict]:
    """Every writer of an NV status document, and its execution identity."""
    rows = [
        {
            "writer": "nv_http_harness.py",
            "platform_scenario": "real HTTP API (O2OA, Alfresco, any CFG)",
            "launcher": "scripts/run_*.sh, run_*.sh (10 scripts, all identical)",
            "lifecycle": "per_execution_process",
            "exec_seq_before": "NO",
            "exec_seq_after": "YES",
            "active": "ACTIVE",
        },
        {
            "writer": "targets/nv_p0_deterministic_target.py",
            "platform_scenario": "P0 deterministic integration profiles",
            "launcher": "scripts/run_p0_mab_feedback_experiment.sh",
            "lifecycle": "per_execution_process",
            "exec_seq_before": "YES",
            "exec_seq_after": "YES",
            "active": "ACTIVE",
        },
        {
            "writer": "test/p01/status_seq_target.c",
            "platform_scenario": "P0.1 M-2 / M-3 integration tests",
            "launcher": "tests/test_p01_status_attribution.py, "
                        "tests/test_p01_replay_identity.py",
            "lifecycle": "per_execution_process (instrumented C target)",
            "exec_seq_before": "YES",
            "exec_seq_after": "YES",
            "active": "ACTIVE",
        },
    ]

    with open(out / "writer_matrix.csv", "w", encoding="utf-8") as fh:
        cols = list(rows[0].keys())
        fh.write(",".join(cols) + "\n")
        for row in rows:
            fh.write(",".join('"%s"' % row[c] for c in cols) + "\n")

    jdump(out / "writer_matrix.json", {
        "note": "NV status writers are documents consumed by "
                "nv_observe_security_state() via NV_STATUS_PATH. "
                "nv_state_probe.py / nv_neuron_probe.py write NV_PROBE_PATH, "
                "a different document, and are not status writers. "
                "targets/alfresco_*_mock.py and *_online_filter_wrapper.py "
                "write their own JSONL and no NV status document.",
        "writers": rows,
    })
    return rows


def identical_requests(out: Path, server: LocalServer, tmp: Path) -> dict:
    cfg = tmp / "task.json"
    write_config(cfg, server.base)
    status = tmp / "nv_http_status.json"

    run_harness(status, cfg, SEED)
    first = read_status(status)
    run_harness(status, cfg, SEED)
    second = read_status(status)

    legacy_stamp_collides = (
        first["body_hash16"] == second["body_hash16"]
        and first["class"] == second["class"]
        and first["http_code"] == second["http_code"]
    )

    record = {
        "finding": "identical executions receive distinct execution identity",
        "boundary": BOUNDARY,
        "request_and_response_identical": legacy_stamp_collides,
        "exec_seq_first": first["exec_seq"],
        "exec_seq_second": second["exec_seq"],
        "exec_seq_distinct": first["exec_seq"] != second["exec_seq"],
        "legacy_fields_still_present": {
            "ts_ms": "ts_ms" in first,
            "body_hash16": "body_hash16" in first,
            "seq": "seq" in first,
        },
        "documents": {"first": first, "second": second},
    }
    jdump(out / "identical_requests.json", record)
    return record


def uniqueness(out: Path, server: LocalServer, tmp: Path, n: int = 100) -> dict:
    cfg = tmp / "task_uniq.json"
    write_config(cfg, server.base)
    status = tmp / "uniq_status.json"

    seqs, pids = [], set()
    for _ in range(n):
        pids.add(run_harness(status, cfg, SEED))
        seqs.append(read_status(status)["exec_seq"])

    record = {
        "finding": "no duplicate execution identity across separate processes",
        "boundary": BOUNDARY,
        "executions": n,
        "distinct_exec_seq": len(set(seqs)),
        "distinct_os_pids": len(pids),
        "strictly_increasing": all(seqs[i + 1] > seqs[i]
                                   for i in range(len(seqs) - 1)),
        "first_exec_seq": seqs[0],
        "last_exec_seq": seqs[-1],
    }
    jdump(out / "uniqueness.json", record)
    return record


def restart(out: Path, server: LocalServer, tmp: Path) -> dict:
    cfg = tmp / "task_restart.json"
    write_config(cfg, server.base)
    status = tmp / "restart_status.json"

    run_harness(status, cfg, SEED)
    run_harness(status, cfg, SEED)
    before = read_status(status)["exec_seq"]

    sidecar = Path(str(status) + ".seq")
    sidecar_existed = sidecar.exists()
    if sidecar_existed:
        sidecar.unlink()

    run_harness(status, cfg, SEED)
    after = read_status(status)["exec_seq"]
    run_harness(status, cfg, SEED)
    after_next = read_status(status)["exec_seq"]

    record = {
        "finding": "sequence store restart does not lock replay detection out",
        "boundary": BOUNDARY,
        "sidecar_path_pattern": "<NV_STATUS_PATH>.seq",
        "sidecar_existed_before_restart": sidecar_existed,
        "exec_seq_before_restart": before,
        "exec_seq_after_restart": after,
        "exec_seq_after_restart_next": after_next,
        "restart_resets_to_low_value": after < before,
        "still_advances_after_restart": after_next > after,
        "c_side_behaviour": "a lower exec_seq resynchronises rather than "
                            "deadlocking (nv_status_is_fresh)",
    }
    jdump(out / "restart.json", record)
    return record


def error_paths(out: Path, server: LocalServer, tmp: Path) -> dict:
    status = tmp / "err_status.json"
    results = {}

    cases = [
        ("2xx", "/api/doc/query", server.base),
        ("4xx", "/bad", server.base),
        ("5xx", "/boom", server.base),
        ("conn_refused", "/api/doc/query", f"http://127.0.0.1:{free_port()}"),
        ("timeout", "/slow", server.base),
    ]

    for label, path, base in cases:
        cfg = tmp / f"task_err_{label}.json"
        write_config(cfg, base, endpoint_path=path)
        seed = f'POST {path} HTTP/1.1\r\n\r\n{{"k":"v"}}'.encode()
        run_harness(status, cfg, seed)
        doc = read_status(status)
        results[label] = {
            "class": doc["class"],
            "http_code": doc["http_code"],
            "exec_seq": doc["exec_seq"],
            "has_exec_seq": doc.get("exec_seq", 0) > 0,
        }

    seqs = [r["exec_seq"] for r in results.values()]
    record = {
        "finding": "every outcome of a real execution attempt carries an identity",
        "boundary": BOUNDARY,
        "cases": results,
        "all_have_exec_seq": all(r["has_exec_seq"] for r in results.values()),
        "all_identities_distinct": len(set(seqs)) == len(seqs),
    }
    jdump(out / "error_paths.json", record)
    return record


def validity_reject(out: Path, server: LocalServer, tmp: Path) -> dict:
    cfg = tmp / "task_validity.json"
    write_config(cfg, server.base, body_only_mode=1,
                 default_endpoint="cms_doc_list",
                 endpoints=[{"name": "cms_doc_list", "method": "POST",
                             "path": "/api/doc/query"}])
    rules = REPO_ROOT / "validity" / "o2oa_query_rules.json"
    status = tmp / "validity_status.json"

    good = json.dumps({"docStatusList": ["p"], "categoryIdList": ["c"],
                       "key": "k"}).encode()
    run_harness(status, cfg, good, NV_ENDPOINT_NAME="cms_doc_list",
                NV_BODY_RULES=str(rules))
    baseline = read_status(status)["exec_seq"]
    hits_before = server.hit_count

    run_harness(status, cfg, b'{"unexpected": 1}',
                NV_ENDPOINT_NAME="cms_doc_list", NV_BODY_RULES=str(rules))
    after = read_status(status)["exec_seq"]

    record = {
        "finding": "a validity-rejected testcase mints no execution identity",
        "boundary": BOUNDARY,
        "exec_seq_before_rejected_case": baseline,
        "exec_seq_after_rejected_case": after,
        "identity_unchanged": baseline == after,
        "server_hits_during_rejected_case": server.hit_count - hits_before,
        "reason": "the validity layer returns before write_status(), which is "
                  "where the identity is allocated",
    }
    jdump(out / "validity_reject.json", record)
    return record


def platform_chain(out: Path, server: LocalServer, tmp: Path,
                   name: str, cfg_path: Path, body: bytes, **extra) -> dict:
    status = tmp / f"{name}_status.json"
    run_harness(status, cfg_path, body, **extra)
    first = read_status(status)
    run_harness(status, cfg_path, body, **extra)
    second = read_status(status)

    record = {
        "finding": f"{name} request shape carries execution identity",
        "boundary": BOUNDARY,
        "launcher": "afl-fuzz -n ... -- python3 nv_http_harness.py",
        "method": first["method"],
        "path": first["path"],
        "class": first["class"],
        "exec_seq_first": first["exec_seq"],
        "exec_seq_second": second["exec_seq"],
        "exec_seq_distinct": first["exec_seq"] != second["exec_seq"],
        "not_claimed": [
            f"real {name} full fuzzing campaign",
            "real-service cross-platform migration VERIFIED",
        ],
    }
    jdump(out / f"{name}_harness.json", record)
    return record


def replay_consumer(out: Path, server: LocalServer, tmp: Path) -> dict:
    """Drive the production C replay consumer over real harness documents."""
    probe_src = REPO_ROOT / "test" / "v071" / "status_consumer_probe.c"
    covset = REPO_ROOT / "src" / "afl-fuzz-nv-covset.c"
    cjson = REPO_ROOT / "src" / "third_party" / "cjson" / "cJSON.c"
    binary = tmp / "status_consumer_probe"

    build = subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-I", str(REPO_ROOT / "include"),
         "-o", str(binary), str(probe_src), str(covset), str(cjson), "-lm"],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        raise SystemExit(f"probe build failed:\n{build.stderr}")

    cfg = tmp / "task_consumer.json"
    write_config(cfg, server.base)
    status = tmp / "consumer_status.json"

    doc1, doc2 = tmp / "exec1.json", tmp / "exec2.json"
    run_harness(status, cfg, SEED)
    shutil.copy(status, doc1)
    run_harness(status, cfg, SEED)
    shutil.copy(status, doc2)

    proc = subprocess.run(
        [str(binary), str(doc1), str(doc2), str(doc2)],
        capture_output=True, text=True, timeout=60,
    )
    verdicts = [ln.split()[0] for ln in proc.stdout.strip().splitlines()]

    with open(out / "replay_consumer.txt", "w", encoding="utf-8") as fh:
        fh.write("# production nv_status_is_fresh() over real harness output\n")
        fh.write("# order: execution#1, execution#2 (identical), re-read of #2\n")
        fh.write(proc.stdout)

    record = {
        "finding": "the C replay consumer accepts the real harness identity",
        "boundary": BOUNDARY,
        "consumer": "nv_status_is_fresh() from src/afl-fuzz-nv-covset.c",
        "sequence": ["execution#1", "execution#2 (identical)", "re-read of #2"],
        "verdicts": verdicts,
        "expected": ["ACCEPT", "ACCEPT", "REPLAY"],
        "matches_expected": verdicts == ["ACCEPT", "ACCEPT", "REPLAY"],
        "raw": proc.stdout.strip().splitlines(),
    }
    jdump(out / "replay_consumer.json", record)
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/v071_exec_seq")
    args = ap.parse_args()

    out = (REPO_ROOT / args.out) if not Path(args.out).is_absolute() \
        else Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    server = LocalServer()
    tmp = Path(tempfile.mkdtemp(prefix="v071_evidence_"))
    try:
        summary = {
            "task": "v0.7.1 real HTTP harness exec_seq upgrade",
            "boundary": BOUNDARY,
            "writers": writer_matrix(out),
            "identical_requests": identical_requests(out, server, tmp),
            "uniqueness": uniqueness(out, server, tmp),
            "restart": restart(out, server, tmp),
            "error_paths": error_paths(out, server, tmp),
            "validity_reject": validity_reject(out, server, tmp),
            "replay_consumer": replay_consumer(out, server, tmp),
        }

        summary["o2oa"] = platform_chain(
            out, server, tmp, "o2oa",
            redirect(REPO_ROOT / "targets" / "o2oa_query.json",
                     server.base, tmp / "o2oa.json"),
            json.dumps({"docStatusList": ["p"], "categoryIdList": ["c"],
                        "key": "k"}).encode(),
            NV_ENDPOINT_NAME="cms_doc_list",
            NV_BODY_RULES=str(REPO_ROOT / "validity" / "o2oa_query_rules.json"),
            NV_TOKEN="local-evidence-token",
        )

        alf_cfg = tmp / "alfresco.json"
        jdump(alf_cfg, {
            "target_type": "http_api", "base": server.base,
            "health": "/health", "body_only_mode": 1,
            "default_endpoint": "metadata_update",
            "endpoints": [{
                "name": "metadata_update", "method": "PUT",
                "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/n1",
            }],
        })
        summary["alfresco"] = platform_chain(
            out, server, tmp, "alfresco", alf_cfg,
            (REPO_ROOT / "in" / "alfresco_afl_metadata_update_smoke"
             / "seed_ok_0.json").read_bytes(),
            NV_ENDPOINT_NAME="metadata_update",
            NV_BODY_RULES=str(REPO_ROOT / "validity"
                              / "alfresco_metadata_update_rules.json"),
        )

        jdump(out / "summary.json", summary)
        print(f"[OK] evidence written to {out}")
        return 0
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
