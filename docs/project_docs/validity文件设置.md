# validity 规则字段说明

## 1. 作用

`validity/*.json` 用于描述 body-level 输入有效性验证规则。

它负责定义：

- 全局 JSON 限制
- 每个 endpoint 的 body 顶层类型
- 必需字段
- 是否允许未知字段
- 字段级类型与长度/数量限制

它**不负责**定义平台地址或鉴权信息。
平台地址与鉴权由 `targets/*.json` 负责。

---

## 2. 推荐结构

```json
{
  "common": {
    "max_bytes": 16384,
    "max_depth": 8,
    "max_keys": 128,
    "max_string": 2048
  },
  "endpoints": {
    "cms_doc_list": {
      "type": "object",
      "required": ["docStatusList", "categoryIdList", "key"],
      "allow_unknown": true,
      "properties": {
        "docStatusList": {
          "type": "array",
          "maxItems": 20
        },
        "categoryIdList": {
          "type": "array",
          "maxItems": 20
        },
        "key": {
          "type": "string",
          "maxLength": 256
        }
      }
    }
  }
}
```


## 3. 顶层字段说明

### 3.1 `common`

全局规则，所有 endpoint 共用。

### 3.2 `endpoints`

按 endpoint 名称分别定义规则。

endpoint 名称必须与 `targets/*.json` 中 `endpoints[].name` 一致。

---

## 4. `common` 字段说明

### 4.1 `max_bytes`

整个 JSON body 的最大字节长度。

超过时直接 reject。

示例：

<pre class="overflow-visible! px-0!" data-start="4574" data-end="4604"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"max_bytes"</span><span>: </span><span class="ͼb">16384</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 4.2 `max_depth`

JSON 最大嵌套深度。

超过时直接 reject。

示例：

<pre class="overflow-visible! px-0!" data-start="4665" data-end="4691"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"max_depth"</span><span>: </span><span class="ͼb">8</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 4.3 `max_keys`

整个 JSON 中允许出现的最大 key 总数。

超过时直接 reject。

示例：

<pre class="overflow-visible! px-0!" data-start="4763" data-end="4790"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"max_keys"</span><span>: </span><span class="ͼb">128</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 4.4 `max_string`

任意字符串字段允许的最大长度（全局兜底限制）。

超过时直接 reject。

示例：

<pre class="overflow-visible! px-0!" data-start="4863" data-end="4893"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"max_string"</span><span>: </span><span class="ͼb">2048</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## 5. `endpoints.<name>` 字段说明

### 5.1 `type`

body 顶层类型。

当前建议支持：

* `object`
* `array`

例如：

<pre class="overflow-visible! px-0!" data-start="4993" data-end="5021"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"type"</span><span>: </span><span class="ͼc">"object"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

如果 body 顶层类型不匹配，则 reject。

---

### 5.2 `required`

必需字段列表。

仅对顶层 `object` 生效。

例如：

<pre class="overflow-visible! px-0!" data-start="5107" data-end="5173"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span>"require</span><span class="ͼc">d"</span><span>: [</span><span class="ͼc">"docStatusList"</span><span>, </span><span class="ͼc">"categoryIdList"</span><span>, </span><span class="ͼc">"key"</span><span>]</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

如果缺少任一字段，则 reject。

---

### 5.3 `allow_unknown`

是否允许出现未在 `properties` 中声明的字段。

取值：

* `true`：允许未知字段
* `false`：出现未知字段直接 reject

例如：

<pre class="overflow-visible! px-0!" data-start="5308" data-end="5341"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"allow_unknown"</span><span>: </span><span class="ͼb">true</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 5.4 `properties`

字段级规则定义。

每个字段可配置：

* `type`
* `maxLength`
* `maxItems`

例如：

<pre class="overflow-visible! px-0!" data-start="5430" data-end="5517"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"properties"</span><span>: {</span><br/><span>  "key": {</span><br/><span>    "type": </span><span class="ͼc">"string"</span><span>,</span><br/><span>    "maxLength": </span><span class="ͼb">256</span><br/><span>  }</span><br/><span>}</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## 6. `properties.<field>` 字段说明

### 6.1 `type`

字段类型。

当前建议支持：

* `string`
* `array`
* `integer`
* `number`
* `boolean`
* `object`
* `null`

示例：

<pre class="overflow-visible! px-0!" data-start="5669" data-end="5697"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"type"</span><span>: </span><span class="ͼc">"string"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 6.2 `maxLength`

字符串最大长度。

仅当字段类型为字符串时生效。

示例：

<pre class="overflow-visible! px-0!" data-start="5755" data-end="5783"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"maxLength"</span><span>: </span><span class="ͼb">256</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 6.3 `maxItems`

数组最大元素数量。

仅当字段类型为数组时生效。

示例：

<pre class="overflow-visible! px-0!" data-start="5840" data-end="5866"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"maxItems"</span><span>: </span><span class="ͼb">20</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## 7. 当前 O2OA 示例

### `cms_doc_list`

```json
"cms_doc_list": {
  "type": "object",
  "required": ["docStatusList", "categoryIdList", "key"],
  "allow_unknown": true,
  "properties": {
    "docStatusList": {
      "type": "array",
      "maxItems": 20
    },
    "categoryIdList": {
      "type": "array",
      "maxItems": 20
    },
    "key": {
      "type": "string",
      "maxLength": 256
    }
  }
}
```

### `review_count`

```json
"review_count": {
  "type": "object",
  "required": ["credentialList"],
  "allow_unknown": true,
  "properties": {
    "credentialList": {
      "type": "array",
      "maxItems": 20
    }
  }
}
```

### `hotpic_list`

```json
"review_count": {
  "type": "object",
  "required": ["credentialList"],
  "allow_unknown": true,
  "properties": {
    "credentialList": {
      "type": "array",
      "maxItems": 20
    }
  }
}
```

---

## 8. 设计原则

### 8.1 规则文件只描述“输入有效性”

不要把平台 URL、token、path 写进 validity 文件。

### 8.2 endpoint 名称必须和 target 配置一致

否则验证器无法按 endpoint 正确选取规则。

### 8.3 先保持规则简单稳定

当前阶段建议只使用：

* `type`
* `required`
* `allow_unknown`
* `maxLength`
* `maxItems`

等主框架稳定后，再考虑扩展：

* `enum`
* `pattern`
* `minLength`
* `minItems`

### 8.4 未来可扩展为 score 辅助配置

例如后续可增加：

* `score_profile`
* `field_weights`

但当前阶段不强制实现。
