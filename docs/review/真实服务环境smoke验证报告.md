# 真实服务环境 smoke 验证报告

日期：2026-05-08

本报告只整理本轮真实服务 smoke 结果文件，不包含 token 原文，不记录 token 长度，不提交任何 token。adapter demo 与 synthetic fuzzer_stats 不作为本报告的实验依据。

## 1. 认证结论

O2OA：已通过手工提供的当前会话 token 完成认证。

说明：报告中不写入 token 原文、token 长度或任何可复用认证材料。

## 2. O2OA 真实 smoke 结果

结果目录：

- 主输出目录：`out/cms_body_valid_compare_real/`
- 本轮归档目录：`out/real_service_smoke_20260508/o2oa_real/`

两处 `summary.csv` 内容一致；`baseline`、`rule_only`、`rule_score` 下均存在 `fuzzer_stats` 与 `eval_report.json`。

### 2.1 summary.csv 关键字段

来源文件：

- `out/cms_body_valid_compare_real/summary.csv`
- `out/real_service_smoke_20260508/o2oa_real/summary.csv`

| mode | nv_total_valid_exec | nv_err_exec | nv_err_rate | saved_hangs | saved_crashes | last_http_code | last_latency_ms | body_rule_pass | body_rule_reject | body_score_pass | body_score_reject | body_score_rpc_ok | body_score_rpc_fail | summary_source | execution_scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| baseline | 888 | 0 | 0.000000 | 0 | 0 | 200 | 22 | 1327 | 842 | 0 | 0 | 0 | 0 | aflpp_harness | o2oa_aflpp_body_harness |
| rule_only | 1012 | 0 | 0.000000 | 0 | 0 | 200 | 20 | 1331 | 961 | 0 | 0 | 0 | 0 | aflpp_harness | o2oa_aflpp_body_harness |
| rule_score | 1144 | 0 | 0.000000 | 0 | 0 | 200 | 21 | 1342 | 1082 | 987 | 355 | 1342 | 0 | aflpp_harness | o2oa_aflpp_body_harness |

`metric_semantics` 为 `AFL++ fuzzer_stats plus nv_http_harness body validity counters`，说明 O2OA 本轮是 AFL++ 驱动的 body harness 真实服务 smoke。

### 2.2 fuzzer_stats 交叉核对

来源文件：

- `out/cms_body_valid_compare_real/baseline/fuzzer_stats`
- `out/cms_body_valid_compare_real/rule_only/fuzzer_stats`
- `out/cms_body_valid_compare_real/rule_score/fuzzer_stats`
- `out/real_service_smoke_20260508/o2oa_real/*/fuzzer_stats`

| mode | run_time | execs_done | execs_per_sec | nv_total_valid_exec | nv_err_exec | nv_err_rate | saved_hangs | saved_crashes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 35 | 2168 | 60.35 | 888 | 0 | 0.000000 | 0 | 0 |
| rule_only | 40 | 2292 | 56.67 | 1012 | 0 | 0.000000 | 0 | 0 |
| rule_score | 45 | 2424 | 53.09 | 1144 | 0 | 0.000000 | 0 | 0 |

补充说明：本轮 O2OA `eval_report.json` 中 `task.source=harness_only`，`NV_TASK_PATH` 未启用；因此 O2OA 业务有效性统计以 `summary.csv` 中的 harness body counters 为准，不把 `validity.valid_cnt=0` 误读为业务无有效样本。

### 2.3 O2OA 结论

O2OA 真实 smoke 通过。依据是：

- 三个模式 `last_http_code=200`；
- 三个模式 `nv_err_exec=0`、`nv_err_rate=0.000000`；
- 三个模式 `saved_hangs=0`、`saved_crashes=0`；
- `rule_score` 模式 `body_score_rpc_ok=1342`、`body_score_rpc_fail=0`，说明本轮评分服务在 O2OA 评分链路中可用；
- `rule_score` 模式产生 `body_score_pass=987`、`body_score_reject=355`，说明 score gate 在真实 smoke 中实际参与筛选。

## 3. Flowable 真实 smoke 结果

结果目录：

- 20s：`out/real_service_smoke_20260508/flowable_dur20/`
- 60s：`out/real_service_smoke_20260508/flowable_dur60/`

Flowable 本轮结果是 `python_static_loop / flowable_min_calibration`，即 Python 静态循环请求回放 + Flowable-AE v2 评分 + `flowable_rule_v1` 最小校准验证；不能表述为完整 AFL++ mutation-chain。

| duration | nv_total_valid_exec | nv_err_exec | nv_err_rate | saved_hangs | saved_crashes | last_http_code | last_latency_ms | body_rule_pass | body_rule_reject | body_score_pass | body_score_reject | body_score_rpc_ok | body_score_rpc_fail | summary_source | execution_scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 20s | 348 | 0 | 0.000000 | 0 | 0 | 201 | 5 | 348 | 0 | 284 | 64 | 348 | 0 | python_static_loop | flowable_min_calibration |
| 60s | 1064 | 0 | 0.000000 | 0 | 0 | 201 | 4 | 1064 | 0 | 883 | 181 | 1064 | 0 | python_static_loop | flowable_min_calibration |

`metric_semantics` 为 `Python static-loop Flowable request replay; not a full AFL++ mutation-chain execution`。

Flowable 真实最小 smoke 通过。依据是：

- 20s 与 60s 均 `last_http_code=201`；
- 20s 与 60s 均 `nv_err_exec=0`、`nv_err_rate=0.000000`；
- 20s 与 60s 均 `saved_hangs=0`、`saved_crashes=0`；
- 60s `body_score_rpc_ok=1064`、`body_score_rpc_fail=0`，说明 Flowable AE v2 评分服务在最小校准链路中可用；
- 60s `body_score_pass=883`、`body_score_reject=181`，说明 score gate 实际参与筛选。

## 4. 综合判断

score service 可用性：可用。依据来自本轮真实结果文件中的 `body_score_rpc_ok/body_score_rpc_fail`，其中 O2OA `rule_score` 为 `1342/0`，Flowable 60s 为 `1064/0`。

真实服务环境 smoke 验证已补齐到 O2OA + Flowable：

- O2OA：真实 O2OA 服务 + 手工提供的当前会话 token + AFL++ body harness smoke 通过；
- Flowable：真实 Flowable REST 服务 + Flowable-AE v2 + `flowable_rule_v1` 最小校准 smoke 通过。

仍然不能说：

- 不能说 Flowable-GAN 完成；
- 不能说 Flowable 完整 AFL++ mutation 主链完成；
- 不能说完整拟态系统级动态异构冗余完成。

## 5. 修改文件列表

- 新增：`docs/review/真实服务环境smoke验证报告.md`

本次未修改 token、未写入 token、未提交 token。

## 6. 验证命令

只读结果抽取命令：

```bash
find out/cms_body_valid_compare_real -maxdepth 2 -type f \( -name 'summary.csv' -o -name 'fuzzer_stats' -o -name 'eval_report.json' \) -print | sort
find out/real_service_smoke_20260508/o2oa_real -maxdepth 3 -type f -print | sort
python3 -c 'import csv,json; from pathlib import Path; paths=[Path("out/cms_body_valid_compare_real/summary.csv"),Path("out/real_service_smoke_20260508/o2oa_real/summary.csv"),Path("out/real_service_smoke_20260508/flowable_dur20/summary.csv"),Path("out/real_service_smoke_20260508/flowable_dur60/summary.csv")]; [print(p, list(csv.DictReader(p.open(encoding="utf-8")))) for p in paths]'
python3 -c 'from pathlib import Path; fields=["run_time","execs_done","execs_per_sec","saved_crashes","saved_hangs","nv_total_valid_exec","nv_err_exec","nv_err_rate"]; [print(p,{k:v.strip() for line in p.read_text(errors="replace").splitlines() if ":" in line for k,v in [line.split(":",1)] if k.strip() in fields}) for base in [Path("out/cms_body_valid_compare_real"),Path("out/real_service_smoke_20260508/o2oa_real")] for p in [base/"baseline/fuzzer_stats",base/"rule_only/fuzzer_stats",base/"rule_score/fuzzer_stats"]]'
python3 -m py_compile integration/decision_engine.py scripts/run_flowable_process_start_compare.py runner/fuzz_test_runner.py integration/fuzz_adapter.py
```

验证结果：

- O2OA `summary.csv`、`fuzzer_stats`、`eval_report.json` 均存在；
- O2OA 归档目录 `out/real_service_smoke_20260508/o2oa_real/` 与主输出目录统计一致；
- Flowable 20s/60s `summary.csv` 均存在；
- `py_compile` 通过。
