# JSON API 模糊测试框架使用说明

## 1. 项目定位

本项目是一套面向 **HTTP JSON API 平台** 的模糊测试实验框架。其核心目标不是绑定某一个特定业务系统，而是提供一套可迁移的实验流程，用于对真实业务平台的 JSON 接口开展结构保持型模糊测试，并结合有效性验证机制提升测试输入质量。

当前框架已经在 O2OA 平台上完成验证，但整体设计并不依赖 O2OA。本框架适用于满足以下条件的平台：

- 目标接口通过 HTTP/HTTPS 提供服务
- 输入主体主要为 JSON
- 可以获得测试账号、token 或其他必要认证信息
- 已知部分待测接口的 method/path 和请求体结构

当前正式主实验采用：

- 输入模式：body-only
- 变异对象：JSON body
- 基础执行器：`nv_http_harness.py`
- 一级有效性验证：规则过滤（rule-only）
- 二级有效性验证：score 过滤（增强实验，可选）

---

## 2. 目录结构建议

建议项目目录保持如下结构：

```text
~/AFLplusplus
├── README.md
├── README_O2OA_Local.md
├── nv_http_harness.py
├── nv_body_valid.py
├── nv_valid_server_mock.py
├── nv_target_xxx.json
├── run_o2oa_main_baseline_rule.sh
├── run_cms_body_valid_compare.sh
├── run_cms_score_sweep.sh
├── in_xxx_body/
├── validity/
│   └── xxx_rules.json
├── out_xxx/
└── docs/
```

说明：

- `nv_http_harness.py`：负责把输入 body 发给目标平台并收集执行状态
- `nv_body_valid.py`：body-level 有效性验证模块
- `nv_valid_server_mock.py`：score 验证 mock 服务
- `nv_target_xxx.json`：目标平台配置文件
- `validity/xxx_rules.json`：一级规则配置文件
- `in_xxx_body/`：输入种子目录
- `out_xxx/`：实验输出目录

---

## 3. 使用前提

在使用本框架测试任意现有平台前，需要先准备以下内容：

### 3.1 平台访问地址

需要明确目标平台基础地址，例如：

- `http://目标平台地址`
- `https://目标平台地址`

该地址将写入目标配置文件中的 `base` 字段。

### 3.2 认证信息

需要至少获得以下之一：

- token
- cookie
- bearer token
- 测试账号+密码（若需先手工登录获取 token）

当前框架已经支持通过环境变量注入 token，并在请求头或 cookie 中携带。

### 3.3 待测接口信息

至少需要明确：

- HTTP method
- path
- body 结构
- 哪些字段是必须字段
- 哪些字段类型固定（字符串、数组、时间等）

### 3.4 一组基础种子

建议先准备少量高质量正常种子，例如：

- 正常查询 JSON
- 边界合法 JSON
- 稍脏但仍合法 JSON

不要一开始就只放纯垃圾输入，否则自动变异很难进入有效区域。

---

## 4. 目标平台配置方法

目标平台通过 `nv_target_xxx.json` 描述。典型配置如下：

```json
{
  "base": "http://目标平台地址",
  "health": "/health_or_home",
  "auth": {
    "type": "raw_token",
    "header": "Authorization",
    "token_env": "NV_TOKEN",
    "also_cookie": "x-token"
  },
  "body_only_mode": 1,
  "default_endpoint": "example_api",
  "endpoints": [
    {
      "name": "example_api",
      "method": "POST",
      "path": "/api/example/query"
    }
  ],
  "biz_fields": ["type", "message", "msg", "code"],
  "body_templates": {
    "example_api": {
      "keyword": "",
      "page": 1,
      "size": 10
    }
  }
}
```

### 关键字段说明

- `base`：目标平台基础地址
- `health`：健康检查路径
- `auth`：认证方式
- `body_only_mode`：是否启用 body-only 模式，当前建议固定为 `1`
- `default_endpoint`：默认接口名
- `endpoints`：待测接口定义
- `body_templates`：基础请求体模板

> 无论使用本地实验环境还是对接已部署平台，实际请求目标都由 `nv_target_xxx.json` 中的 `base` 字段控制。

---

## 5. 一级规则验证配置方法

一级规则通过 `validity/xxx_rules.json` 配置。示例：

```json
{
  "common": {
    "max_bytes": 16384,
    "max_depth": 8,
    "max_keys": 128,
    "max_string": 2048
  },
  "endpoints": {
    "example_api": {
      "type": "object",
      "required": ["keyword"],
      "properties": {
        "keyword": { "type": "string", "maxLength": 256 },
        "page": { "type": "integer" },
        "size": { "type": "integer" }
      }
    }
  }
}
```

一级规则的作用：

- 拦截非法 JSON
- 拦截明显不满足接口约束的 body
- 保证进入真实平台执行的输入具备基本语义合法性

---

## 6. 运行前最小自检

在正式跑 AFL 之前，建议先做一次单次手工请求自检。

### 6.1 设置环境变量

```bash
cd ~/AFLplusplus
export NV_TARGET_CONFIG=$PWD/nv_target_xxx.json
export NV_TOKEN='你的真实token'
export NV_ENDPOINT_NAME='example_api'
unset NV_BODY_RULES
unset NV_BODY_SCORE_ENDPOINT
unset NV_BODY_SCORE_THRESHOLD
export NV_STATUS_PATH=/tmp/nv_http_status.json
```

### 6.2 执行单次验证

```bash
python3 nv_http_harness.py < in_xxx_body/seed_0.json || true
cat /tmp/nv_http_status.json
```

### 6.3 预期结果

如果配置正确，应该看到：

- `http_code: 200` 或者平台允许的业务返回状态
- `class: 2xx`（若该接口应成功）

如果这里失败，优先检查：

1. 平台地址是否可访问
2. token 是否过期
3. endpoint 配置是否正确
4. body 模板是否与真实接口匹配

---

## 7. 主实验推荐模式

当前推荐先做两种模式：

### 7.1 baseline

不做有效性过滤，直接把 body-only JSON 发给平台。

### 7.2 rule_only

先做一级规则过滤，再把通过的 body 发给平台。

这两种模式足以构成当前阶段的正式主实验。

---

## 8. 运行主实验

若已有统一脚本，可直接运行。例如：

```bash
cd ~/AFLplusplus
export NV_TOKEN='你的真实token'
DUR=120 ./run_o2oa_main_baseline_rule.sh
```

如果目标不是 O2OA，请自行准备与目标平台对应的运行脚本，原则上应完成：

- 若干接口的 `baseline`
- 相同接口的 `rule_only`
- 输出统一 `summary.csv`

### 8.1 查看结果

```bash
cat out_xxx/summary.csv
```

应重点保留以下字段：

- `nv_total_valid_exec`
- `nv_err_exec`
- `nv_err_rate`
- `saved_hangs`
- `saved_crashes`
- `last_http_code`
- `body_rule_pass`
- `body_rule_reject`

---

## 9. 二级 score 增强实验（可选）

当一级规则已经稳定后，可以继续加入二级 score 验证。

### 9.1 启动 score 服务

```bash
cd ~/AFLplusplus
export NV_RPC_FMT=text
export NV_VALID_SOCK=/tmp/nv_valid.sock
python3 nv_valid_server_mock.py
```

### 9.2 配置环境变量

```bash
export NV_BODY_RULES=$PWD/validity/xxx_rules.json
export NV_BODY_SCORE_ENDPOINT='unix:///tmp/nv_valid.sock'
export NV_BODY_SCORE_THRESHOLD='1.5'
export NV_BODY_VALID_STATS=/tmp/nv_body_valid_stats.json
```

### 9.3 单次测试

```bash
python3 nv_http_harness.py < in_xxx_body/seed_ok.json ; echo $?
python3 nv_http_harness.py < in_xxx_body/seed_bad.json ; echo $?
cat /tmp/nv_body_valid_stats.json
```

### 9.4 关注字段

- `body_score_pass`
- `body_score_reject`
- `body_score_rpc_ok`
- `body_score_rpc_fail`

> 当前建议将二级 score 作为增强实验，不作为当前阶段唯一正式结论支撑。

---

## 10. 输出文件说明

### `summary.csv`

统一结果表，用于报告和汇报。

### `fuzzer_stats`

AFL++ 原始统计，重点看：

- `nv_total_valid_exec`
- `nv_err_exec`
- `nv_err_rate`
- `saved_hangs`
- `saved_crashes`

### `/tmp/nv_http_status.json`

记录最后一次真实请求状态：

- `http_code`
- `class`
- `latency_ms`
- `ncov_total`

### `/tmp/nv_body_valid_stats.json`

记录 body-level 有效性验证统计：

- `body_rule_pass`
- `body_rule_reject`
- `body_score_pass`
- `body_score_reject`
- `body_score_rpc_ok`
- `body_score_rpc_fail`

---

## 11. 常见问题排查

### 11.1 单次请求不是 200

优先检查：

- 平台地址是否可达
- token 是否过期
- endpoint method/path 是否写错
- body 是否不符合真实接口要求

### 11.2 rule_only 没有体现作用

优先检查：

- `validity/xxx_rules.json` 是否配置过宽
- 输入种子是否太正常
- 是否确实开启了 `NV_BODY_RULES`

### 11.3 score 没有 reject

优先检查：

- mock score 服务是否在运行
- `NV_BODY_SCORE_ENDPOINT` 是否正确
- `NV_BODY_SCORE_THRESHOLD` 是否过高
- 种子是否覆盖到 score 敏感区

### 11.4 结果目录混乱

建议每次跑实验前先清理：

```bash
rm -rf out_xxx
rm -f /tmp/nv_http_status.json /tmp/nv_body_valid_stats.json
```

---

## 12. 当前推荐的项目推进方式

1. 先固定 `baseline + rule_only` 为正式主实验方案
2. 再单独做 `rule_score` 作为增强实验
3. 最后再考虑把 mock score 替换为真实模型服务

---

## 13. 当前阶段结论模板

可以直接参考以下表述：

> 在真实 JSON API 平台场景下，采用 body-only 输入模式开展结构保持型模糊测试是可行的。一级规则有效性验证能够在不显著影响执行效率的前提下过滤大量无效 JSON 变异样本，从而提高进入真实平台执行的输入质量。二级 score 验证链路已打通，并在手工异常样本上具备 reject 能力，后续将继续增强其在自动 fuzz 场景下的稳定筛选收益。
# AFL-
