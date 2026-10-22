#!/usr/bin/env python3
"""Opt-in Task 4 O2OA write experiment, using the production AFL/mutator/harness.

Each create invocation is read back and deleted by exact receipt ID. Updates
target one draft created by this run, read it back after every mutation, then
delete it. A persistent invocation cap includes calibration executions.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import nv_http_harness as h
from nv_body_valid import body_validate, rpc_score_unix
from nv_http_body_adapter import extract_http_body

CREATE = "cms_document_create_save"
UPDATE = "cms_document_data_update"
CONFIG = ROOT / "targets/o2oa_query.json"
RULES = ROOT / "validity/o2oa_query_rules.json"


def put(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def journal(path: Path, value):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_gate(raw_body, endpoint, score_endpoint, threshold):
    success, score = rpc_score_unix(score_endpoint, "metadata_update", endpoint, raw_body)
    if not success or score is None or not math.isfinite(score):
        return False, "score_rpc_failed"
    return score < threshold, "score_pass" if score < threshold else "score_reject"


def request(method, path, body=None):
    cfg = read(CONFIG)
    headers = h.apply_auth_headers(cfg, {"Accept": "application/json"})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    req = h.urllib.request.Request(cfg["base"] + path, data=data, method=method, headers=headers)
    try:
        with h.open_direct(req, timeout=10) as response:
            code, raw = int(response.getcode()), response.read(131072)
    except urllib.error.HTTPError as exc:
        code, raw = int(exc.code), exc.read(131072)
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    return code, payload


def ok(code, payload):
    return 200 <= code < 300 and payload.get("type") == "success"


def document_data(payload):
    data = payload.get("data", {})
    # O2OA 9.5.2 returns the document view at data.document and the
    # document-data view at data.data. Older fixtures used the inverse
    # nesting, so accept both without weakening the ownership checks.
    if isinstance(data, dict) and isinstance(data.get("document"), dict):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        nested = data["data"]
        if isinstance(nested.get("document"), dict):
            data = nested
        else:
            data = {**data, "data": nested}
    return data if isinstance(data, dict) else {}


def document_check(payload, manifest, doc_id, expected=None):
    data = document_data(payload)
    doc = data.get("document", {})
    person = doc.get("creatorPerson")
    # O2OA 9.5.2 may serialize ACL person entries as the compact unique@P
    # form while creatorPerson is the display-name@unique@P DN. Treat those
    # two representations as the same owner, but require exactly one entry
    # and reject all-people/unit/group fallbacks.
    person_aliases = {str(person)} if person else set()
    if isinstance(person, str) and person.count("@") >= 2:
        person_aliases.add("@".join(person.split("@")[1:]))
    def sole_owner(value):
        return isinstance(value, list) and len(value) == 1 and str(value[0]) in person_aliases
    return bool(person) and all((
        doc.get("id") == doc_id,
        doc.get("categoryId") == manifest["category"],
        doc.get("creatorIdentity") == manifest["identity"],
        doc.get("docStatus") == "draft",
        doc.get("title") == manifest["title"],
        sole_owner(doc.get("readPersonList")),
        doc.get("readUnitList") == [], doc.get("readGroupList") == [],
        sole_owner(doc.get("authorPersonList")), sole_owner(doc.get("managerList")),
        all((data.get("data", data).get(key) == value) for key, value in (expected or {}).items()),
    ))


def absent(code, payload):
    return code == 404 or (code == 500 and payload.get("type") == "error"
        and "ExceptionDocumentNotExists" in str(payload.get("prompt", "")))


def cleanup(manifest, doc_id):
    path = "/x_cms_assemble_control/jaxrs/document/" + urllib.parse.quote(doc_id, safe="")
    code, payload = request("GET", path)
    if not ok(code, payload):
        # Only an explicit not-found result proves absence; a login or server
        # failure never authorizes a delete or masquerades as successful cleanup.
        return {"ok": absent(code, payload), "absence_http": code}
    if not document_check(payload, manifest, doc_id):
        raise RuntimeError("CLEANUP_OWNERSHIP_CHECK_FAILED")
    delete_code, deleted = request("DELETE", path)
    absence_code, absence = request("GET", path)
    missing = absent(absence_code, absence)
    return {"delete_http": delete_code, "absence_http": absence_code,
            "ok": ok(delete_code, deleted) and missing}


def fixture():
    for key in ("NV_TOKEN", "NV_O2OA_CATEGORY_ID", "NV_O2OA_CURRENT_USER_IDENTITY"):
        if not os.environ.get(key, "").strip():
            raise RuntimeError("MISSING_" + key)
    if read(CONFIG)["base"] != "http://127.0.0.1:20020":
        raise RuntimeError("LOCAL_TOPOLOGY_REQUIRED")
    code, auth = request("GET", "/x_organization_assemble_authentication/jaxrs/authentication")
    who = auth.get("data", {})
    if not ok(code, auth) or who.get("tokenType") in ("manager", "systemManager", "securityManager"):
        raise RuntimeError("DEDICATED_NONADMIN_TEST_TOKEN_REQUIRED")
    if who.get("name") != "Task4TestUser":
        raise RuntimeError("DEDICATED_TEST_PERSON_REQUIRED")
    if any(str(role).split("@")[0] in ("Manager", "CMSManager", "CMSCreator") for role in who.get("roleList", [])):
        raise RuntimeError("GLOBAL_CMS_ROLES_FORBIDDEN")
    code, apps = request("GET", "/x_cms_assemble_control/jaxrs/appinfo/list/user/publish")
    candidates = [x for x in apps.get("data", []) if x.get("appName", x.get("name")) == "Task4TestApplication"]
    if not ok(code, apps) or len(candidates) != 1:
        raise RuntimeError("DEDICATED_APPLICATION_REQUIRED")
    app_id = candidates[0]["id"]
    code, cats = request("GET", "/x_cms_assemble_control/jaxrs/categoryinfo/list/publish/app/" + urllib.parse.quote(app_id, safe=""))
    category = os.environ["NV_O2OA_CATEGORY_ID"]
    matches = [x for x in cats.get("data", []) if x.get("id") == category and x.get("categoryName", x.get("name")) == "Task4TestCategory"]
    if not ok(code, cats) or len(matches) != 1:
        raise RuntimeError("DEDICATED_CATEGORY_REQUIRED")
    return {"category": category, "identity": os.environ["NV_O2OA_CURRENT_USER_IDENTITY"],
            "fixture": "Task4TestApplication/Task4TestCategory", "admin_used": False}


def worker(phase: Path, testcase: Path):
    """Run one bounded AFL invocation through the complete same-document chain."""
    manifest = read(phase.parent / "runtime.json")
    count_file = phase / "invocations.json"
    count = read(count_file) if count_file.exists() else 0
    if count >= manifest["invocation_cap"]:
        raise RuntimeError("INVOCATION_CAP_REACHED")
    put(count_file, count + 1)
    task = read(phase / "task.json")
    if task["target_endpoint"] != CREATE:
        raise RuntimeError("WRITE_CHAIN_CREATE_ENDPOINT_REQUIRED")
    ctx = phase / ("context-%03d.json" % count)
    os.environ["NV_CTX_PATH"] = str(ctx)
    raw = testcase.read_bytes()
    body = json.loads(extract_http_body(raw))
    record = {
        "invocation": count + 1,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "chain": ["seed", "validity", "create_save", "readback", "content_update", "readback", "cleanup"],
    }
    doc_id = None
    try:
        os.environ["NV_ENDPOINT_NAME"] = CREATE
        os.environ["NV_BODY_SCORE_ENDPOINT"] = manifest["score_endpoint"]
        os.environ["NV_BODY_SCORE_THRESHOLD"] = str(
            read(phase.parent / "validity-calibration.json")[CREATE]["threshold"]
        )
        # Use the shared production harness unchanged for the create leg.
        sys.stdin = type("Input", (), {"buffer": io.BytesIO(raw)})()
        rc = h.main()
        create_status = read(Path(os.environ["NV_STATUS_PATH"]))
        record.update(
            create_exec_seq=create_status["exec_seq"],
            create_http=create_status["http_code"],
            create_validation_reject=bool(create_status["validation_reject"]),
        )
        if create_status["validation_reject"]:
            record["validity_decision"] = "reject_create"
            return 0
        record["validity_decision"] = "accept_create"
        if rc != 0 or not 200 <= create_status["http_code"] < 300:
            raise RuntimeError("WRITE_CREATE_HTTP_FAILED")
        doc_id = read(ctx).get("documentId")
        if not doc_id:
            raise RuntimeError("CREATE_DOCUMENT_RECEIPT_MISSING")
        record["document_id"] = doc_id
        get_path = "/x_cms_assemble_control/jaxrs/document/" + urllib.parse.quote(doc_id, safe="")
        code, payload = request("GET", get_path)
        record["create_readback_http"] = code
        record["create_readback_ok"] = ok(code, payload) and document_check(
            payload, manifest, doc_id, body["docData"]
        )
        if not record["create_readback_ok"]:
            raise RuntimeError("CREATE_READBACK_FAILED")

        # O2OA 9.5.2 replaces the title with an empty value when data update
        # omits it. Preserve the creator-only draft title explicitly as part of
        # the same-document content-update contract.
        update_body = {
            "title": manifest["title"],
            "nvMarker": "update-" + str(body.get("docData", {}).get("nvMarker", "seed")),
        }
        update_raw = json.dumps(update_body, ensure_ascii=False, separators=(",", ":")).encode()
        update_cfg = read(phase / "target.json")
        _, update_path, update_ep = h.resolve_named_endpoint(
            read(CONFIG), UPDATE, context={"documentId": doc_id}
        )
        concrete_update = dict(update_ep, path=update_path)
        concrete_update.pop("runtime_path_parameter", None)
        update_cfg["endpoints"] = [concrete_update]
        update_cfg["default_endpoint"] = UPDATE
        put(phase / "update-target.json", update_cfg)
        os.environ["NV_TARGET_CONFIG"] = str(phase / "update-target.json")
        os.environ["NV_ENDPOINT_NAME"] = UPDATE
        os.environ["NV_BODY_SCORE_THRESHOLD"] = str(
            read(phase.parent / "validity-calibration.json")[UPDATE]["threshold"]
        )
        sys.stdin = type("Input", (), {"buffer": io.BytesIO(update_raw)})()
        update_rc = h.main()
        update_status = read(Path(os.environ["NV_STATUS_PATH"]))
        record.update(
            update_exec_seq=update_status["exec_seq"],
            update_http=update_status["http_code"],
            update_validation_reject=bool(update_status["validation_reject"]),
            exec_seq=update_status["exec_seq"],
        )
        if update_status["validation_reject"]:
            record["validity_decision"] = "accept_create_reject_update"
            return 0
        if update_rc != 0 or not 200 <= update_status["http_code"] < 300:
            raise RuntimeError("WRITE_UPDATE_HTTP_FAILED")
        code, payload = request("GET", get_path)
        record["update_readback_http"] = code
        record["update_readback_ok"] = ok(code, payload) and document_check(
            payload, manifest, doc_id, update_body
        )
        data_code, updated = request(
            "GET", "/x_cms_assemble_control/jaxrs/data/document/" + urllib.parse.quote(doc_id, safe="")
        )
        update_data = updated.get("data", {}) if isinstance(updated, dict) else {}
        record["update_data_readback_http"] = data_code
        record["update_data_readback_ok"] = ok(data_code, updated) and all(
            update_data.get(key) == value for key, value in update_body.items()
        )
        if not record["update_readback_ok"] or not record["update_data_readback_ok"]:
            raise RuntimeError("UPDATE_READBACK_FAILED")
        return 0
    finally:
        if ctx.exists():
            doc_id = read(ctx).get("documentId")
            if doc_id:
                record["document_id"] = doc_id
                record["cleanup"] = cleanup(manifest, doc_id)
        journal(phase / "evidence/readback.jsonl", record)


def run_phase(out, endpoint, body, args):
    """Launch the explicit AFL++ entrypoint for the same-document chain."""
    if endpoint != CREATE:
        raise RuntimeError("WRITE_CHAIN_CREATE_ENDPOINT_REQUIRED")
    phase = out / "create_update_chain"
    (phase / "seed_input").mkdir(parents=True)
    (phase / "evidence").mkdir()
    cfg = read(CONFIG)
    method, path, ep = h.resolve_named_endpoint(cfg, endpoint)
    # Bind the disposable category and creator identity before the seed enters
    # AFL++; full-HTTP mode deliberately does not perform body substitution.
    bound_body = json.loads(h.bind_runtime_body_parameter(ep, json.dumps(body, ensure_ascii=False).encode()))
    seed = f"{method} {path} HTTP/1.1\r\nContent-Type: application/json\r\n\r\n".encode() + json.dumps(bound_body, ensure_ascii=False).encode()
    (phase / "seed_input/seed.http").write_bytes(seed)
    # The initial target contains the create endpoint only. The worker writes a
    # concrete context-bound update target after the create receipt arrives.
    concrete = dict(ep, path=path)
    concrete.pop("runtime_path_parameter", None)
    concrete.pop("runtime_body_parameter", None)
    concrete.pop("runtime_body_path_parameters", None)
    cfg["endpoints"] = [concrete]
    put(phase / "target.json", cfg)
    put(phase / "task.json", {"target_type": "http_api", "target_endpoint": endpoint,
        "seed_source": "seed_file", "seed_location": str(phase / "seed_input"),
        "mutation_scope": ["field_value", "boundary", "structure"],
        "max_test_cases": args.max_test_cases, "time_budget": args.time_budget,
        "enable_validity": 1, "mab_min_explore": 1,
        "validity_endpoint": read(out / "runtime.json")["score_endpoint"],
        "validity_threshold": read(out / "validity-calibration.json")[endpoint]["threshold"]})
    env = dict(os.environ)
    for name in list(env):
        if name.startswith("AFL_") or name.startswith("NV_") or name.lower().endswith("_proxy"):
            if name not in ("NV_TOKEN", "NV_O2OA_CATEGORY_ID", "NV_O2OA_CURRENT_USER_IDENTITY"):
                env.pop(name)
    env.update(AFL_NO_UI="1", AFL_SKIP_CPUFREQ="1", AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES="1",
        AFL_FAST_CAL="1", AFL_CUSTOM_MUTATOR_ONLY="1", AFL_DISABLE_TRIM="1", AFL_PYTHON_MODULE="nv_json_mutator",
        PYTHONPATH=str(ROOT), NV_BODY_ONLY_MODE="1", NV_ENDPOINT_NAME=endpoint,
        NV_TARGET_CONFIG=str(phase / "target.json"), NV_BODY_RULES=str(RULES), NV_TASK_PATH=str(phase / "task.json"),
        NV_STATUS_PATH=str(phase / "status.json"), NV_STATUS_LEDGER_PATH=str(phase / "evidence/status.jsonl"),
        NV_STATE_DB=str(phase / "state.json"), NV_PROBE_PATH=str(phase / "probe.json"),
        NV_STATE_TRACE_PATH=str(phase / "evidence/state.jsonl"), NV_BODY_VALID_STATS=str(phase / "validity.json"),
        NV_MAB_JOURNAL_PATH=str(phase / "evidence/mab.jsonl"), NV_EXECUTION_LEDGER_PATH=str(phase / "evidence/executions.jsonl"),
        NV_SEED_SELECTION_AUDIT_PATH=str(phase / "evidence/seeds.jsonl"), NV_KEEP_INITIAL_SEEDS="1")
    command = [str(ROOT / "afl-fuzz"), "-n", "-Z", "-m", "none", "-s", "20261022", "-t", "20000+", "-i", str(phase / "seed_input"), "-o", str(phase / "afl-out"), "--", sys.executable, str(Path(__file__).resolve()), "--worker", str(phase), "@@"]
    with (phase / "launch.log").open("w") as log:
        result = subprocess.run(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=args.time_budget + 60)
    records = rows(phase / "evidence/readback.jsonl")
    report = read(phase / "afl-out/eval_report.json")
    commits = [x for x in rows(phase / "evidence/mab.jsonl") if x.get("event") == "mab_update"]
    successful = [r for r in records if r.get("create_readback_ok") and r.get("update_readback_ok")
                  and r.get("update_data_readback_ok") and not r.get("create_validation_reject")]
    cov = report["security_state_cov"]
    capacity = int(cov.get("security_state_capacity", 0) or 0)
    metrics = {"Cov_proxy": (cov["security_state_new_total"] / capacity) if capacity else 0.0,
               "Err": report["err"]["err_rate"], "Rec": report["rec"]["rec_rate"]}
    metrics["overall"] = (metrics["Cov_proxy"] + 1/(1+metrics["Err"]) + metrics["Rec"]) / 3
    checks = {"afl_exit_zero": result.returncode == 0, "validity_enabled": report["task"]["enable_validity"] == 1,
        "mutated_readback": bool({r["exec_seq"] for r in successful} & {r["exec_seq"] for r in commits}),
        "all_writes_read_back": len(successful) == sum(not r.get("create_validation_reject") for r in records),
        "mab_reconciled": len(commits) == report["mab"]["total_pulls"] and bool(commits),
        "security_state_capacity": capacity > 0,
        "all_update_readbacks": all(r.get("update_data_readback_ok") for r in successful),
        "all_create_cleanup": all(r.get("cleanup", {}).get("ok") for r in successful)}
    summary = {"checks": checks, "metrics": metrics, "successful_writes": len(successful), "mab_commits": len(commits),
        "verdict": "PASS" if all(checks.values()) else "FAIL"}
    put(phase / "summary.json", summary)
    return summary


def calibrate(out, create, update, endpoint):
    """Small transfer check, frozen before any AFL/write execution.

    Reuse the saved normal-trained GAN without retraining or altering weights.
    Select a conservative threshold from ordinary request variations, then
    measure disjoint ordinary and excessive-repetition challenge samples.
    This establishes a bounded engineering use, not global model equivalence.
    """
    results = {}
    for name, base in ((CREATE, create), (UPDATE, update)):
        def sample(text):
            obj = json.loads(json.dumps(base))
            (obj["docData"] if name == CREATE else obj)["nvMarker"] = text
            return json.dumps(obj, ensure_ascii=False).encode()
        calibration = [sample(t) for t in ("ordinary draft", "task4 create value", "document data 123", "本地测试公文", "one line\nsecond line", "unchanged marker")]
        holdout = [(True, sample(t)) for t in ("independent document", "Task4Test safe content", "readback 987", "另一份本地公文")]
        holdout += [(False, sample(t)) for t in ("!@#" * 400, "A" * 2048, "\\u0000" * 256, "x" * 1024)]
        def scoring(body):
            good, score = rpc_score_unix(endpoint, "metadata_update", name, body)
            if not good or score is None or not math.isfinite(score):
                raise RuntimeError("MODEL_CALIBRATION_RPC_FAILED")
            return score
        values = [scoring(body) for body in calibration]
        threshold = max(values) * 1.10
        measured = [{"expected_ordinary": label, "score": scoring(body), "sha256": hashlib.sha256(body).hexdigest()} for label, body in holdout]
        for item in measured:
            item["accepted"] = item["score"] < threshold
        result = {"calibration_scores": values, "threshold": threshold, "threshold_rule": "1.10_times_max_ordinary_calibration_score",
            "holdout": measured, "ordinary_accepted": sum(x["accepted"] for x in measured if x["expected_ordinary"]),
            "challenge_rejected": sum(not x["accepted"] for x in measured if not x["expected_ordinary"]),
            "checkpoint_sha256": hashlib.sha256((ROOT / "model_stage/models/sefanogan_gan_model.pt").read_bytes()).hexdigest(),
            "frozen_before_write": True, "weights_changed": False}
        results[name] = result
    put(out / "validity-calibration.json", results)
    if any(x["ordinary_accepted"] < 4 or x["challenge_rejected"] < 4 for x in results.values()):
        raise RuntimeError("MODEL_TRANSFER_HOLDOUT_FAILED")


def start_scorer(out):
    import tempfile
    sockdir = Path(tempfile.mkdtemp(prefix="task4-o2oa-score-"))
    socket_path = sockdir / "score.sock"
    env = {key: value for key, value in os.environ.items() if not key.startswith(("NV_", "SEFANOGAN_", "AFL_"))}
    env.update(PYTHONPATH=str(ROOT), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", SEFANOGAN_MODE="sefanogan_es",
        SEFANOGAN_MODEL_PATH=str(ROOT / "model_stage/models/sefanogan_gan_model.pt"),
        SEFANOGAN_GAN_META_PATH=str(ROOT / "model_stage/models/sefanogan_gan_meta.json"),
        NV_VALID_SOCK=str(socket_path), NV_SCORER_TRACE_PATH=str(out / "scorer-trace.jsonl"))
    log = (out / "scorer.log").open("w")
    process = subprocess.Popen([sys.executable, str(ROOT / "model_stage/nv_valid_server_real.py")], env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(200):
        if socket_path.exists():
            return process, log, sockdir, "unix://" + str(socket_path)
        if process.poll() is not None:
            break
        time.sleep(0.1)
    process.terminate()
    log.close()
    raise RuntimeError("MODEL_SERVICE_START_FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--max-test-cases", type=int, default=5)
    parser.add_argument("--time-budget", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker", type=Path)
    parser.add_argument("testcase", nargs="?", type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker, args.testcase)
    if not 3 <= args.max_test_cases <= 6 or not 1 <= args.time_budget <= 60:
        raise RuntimeError("BOUNDED_BUDGET_REQUIRED_cases_3_to_6_seconds_1_to_60")
    out = (args.out_dir or Path("/home/cphzy/task4-evidence") / ("o2oa-formal-" + datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z"))).resolve()
    if out.is_relative_to(ROOT) or out.exists():
        raise RuntimeError("FRESH_EXTERNAL_OUTPUT_REQUIRED")
    if args.dry_run:
        print("O2OA_WRITE_DRY_RUN=PASS\nNETWORK_CONTACTED=NO\nMAX_CASES_PER_PHASE=" + str(args.max_test_cases))
        return 0
    manifest = fixture()
    out.mkdir(parents=True, mode=0o700)
    manifest.update(title="nv-task4-" + out.name, invocation_cap=args.max_test_cases + 6)
    create = read(ROOT / "in/o2oa_document_create/seed_create_draft_0.json")
    create["title"] = manifest["title"]
    result = {}
    process = log = sockdir = None
    try:
        process, log, sockdir, manifest["score_endpoint"] = start_scorer(out)
        put(out / "runtime.json", manifest)
        update = read(ROOT / "in/o2oa_document_data_update/seed_update_data_0.json")
        # Calibrate the exact update representation used by the worker,
        # including the title preservation field required by O2OA 9.5.2.
        update["title"] = manifest["title"]
        calibrate(out, create, update, manifest["score_endpoint"])
        result["create_save"] = run_phase(out, CREATE, create, args)
    finally:
        cleanup_records = []
        for context in sorted(out.glob("*/context-*.json")):
            if context.exists():
                cleanup_records.append(cleanup(manifest, read(context)["documentId"]))
        result["cleanup"] = {"ok": all(x["ok"] for x in cleanup_records), "records": cleanup_records}
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
            log.close()
            import shutil
            shutil.rmtree(sockdir)
        token = os.environ["NV_TOKEN"].encode()
        leaked = sum(p.read_bytes().count(token) for p in out.rglob("*") if p.is_file())
        result["secret_scan"] = {"exact_token_occurrences": leaked, "ok": leaked == 0}
        result["verdict"] = "PASS" if result.get("create_save", {}).get("verdict") == "PASS" and result["cleanup"]["ok"] and not leaked else "FAIL"
        put(out / "summary.json", result)
        print("O2OA_WRITE_EXPERIMENT_VERDICT=" + result["verdict"])
        print("NEW_EVIDENCE_ROOT=" + str(out))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not include request/response contents or urllib exception details.
        print("O2OA_WRITE_EXPERIMENT_ERROR=" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(2)
