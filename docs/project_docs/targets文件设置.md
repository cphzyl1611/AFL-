# targets 配置字段说明

## 1. 作用

`targets/*.json` 用于描述“被测平台目标配置”。

它负责定义：

- 平台基础地址
- 健康检查地址
- 鉴权方式
- body-only 模式
- endpoint 列表
- 默认 body 模板

它**不负责**定义输入有效性规则。
输入有效性规则统一放在 `validity/*.json` 中。

---

## 2. 推荐结构

```json
{
  "base": "http://127.0.0.1:20020",
  "health": "/x_desktop/index.html",
  "auth": {
    "type": "raw_token",
    "header": "Authorization",
    "token_env": "NV_TOKEN",
    "also_cookie": "x-token"
  },
  "body_only_mode": 1,
  "default_endpoint": "cms_doc_list",
  "endpoints": [
    {
      "name": "cms_doc_list",
      "method": "PUT",
      "path": "/x_cms_assemble_control/jaxrs/document/filter/list/1/size/5"
    }
  ],
  "body_templates": {
    "cms_doc_list": {
      "docStatusList": [],
      "categoryIdList": [],
      "key": ""
    }
  }
}
```

## 3. 字段说明

### 3.1 `base`

平台基础地址。

示例：

<pre class="overflow-visible! px-0!" data-start="1462" data-end="1506"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"base"</span><span>: </span><span class="ͼc">"http://127.0.0.1:20020"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

如果换平台，只需要改这里。

例如：

<pre class="overflow-visible! px-0!" data-start="1529" data-end="1575"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"base"</span><span>: </span><span class="ͼc">"http://example-api.local"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 3.2 `health`

健康检查路径。

用于在异常后检测平台是否恢复。

示例：

<pre class="overflow-visible! px-0!" data-start="1630" data-end="1675"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"health"</span><span>: </span><span class="ͼc">"/x_desktop/index.html"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

最终健康检查地址为：

<pre class="overflow-visible! px-0!" data-start="1689" data-end="1714"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span>base + health</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 3.3 `auth`

鉴权配置。

支持不同鉴权方式。

#### 常见字段

##### `type`

鉴权类型。

当前常用：

* `none`
* `bearer`
* `raw_token`

##### `header`

鉴权头字段名。

例如：

<pre class="overflow-visible! px-0!" data-start="1855" data-end="1892"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"header"</span><span>: </span><span class="ͼc">"Authorization"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

##### `token_env`

token 从哪个环境变量读取。

例如：

<pre class="overflow-visible! px-0!" data-start="1935" data-end="1970"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"token_env"</span><span>: </span><span class="ͼc">"NV_TOKEN"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

##### `prefix`

仅 `bearer` 模式常用。

例如：

<pre class="overflow-visible! px-0!" data-start="2010" data-end="2041"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"prefix"</span><span>: </span><span class="ͼc">"Bearer "</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

##### `also_cookie`

仅 `raw_token` 模式常用。

表示除了写请求头，还要把 token 写进 Cookie。

例如：

<pre class="overflow-visible! px-0!" data-start="2121" data-end="2157"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"also_cookie"</span><span>: </span><span class="ͼc">"x-token"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 3.4 `body_only_mode`

是否启用 body-only 模式。

取值：

* `1`：启用
* `0`：关闭

启用后，fuzz 输入只包含 JSON body，不再包含完整 HTTP 报文。

这是当前主实验推荐模式。

---

### 3.5 `default_endpoint`

默认 endpoint 名称。

当 body-only 模式启用，且没有显式设置 `NV_ENDPOINT_NAME` 时，使用该 endpoint。

示例：

<pre class="overflow-visible! px-0!" data-start="2404" data-end="2450"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span class="ͼc">"default_endpoint"</span><span>: </span><span class="ͼc">"cms_doc_list"</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 3.6 `endpoints`

endpoint 列表。

每个 endpoint 至少包含：

* `name`
* `method`
* `path`

示例：

<pre class="overflow-visible! px-0!" data-start="2545" data-end="2677"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span>{</span><br/><span>  "name": </span><span class="ͼc">"cms_doc_list"</span><span>,</span><br/><span>  "method": </span><span class="ͼc">"PUT"</span><span>,</span><br/><span>  "path": </span><span class="ͼc">"/x_cms_assemble_control/jaxrs/document/filter/list/1/size/5"</span><br/><span>}</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

#### 字段说明

##### `name`

endpoint 唯一名称。

用于：

* `NV_ENDPOINT_NAME`
* 规则文件 `validity/*.json`
* body 模板索引

##### `method`

HTTP 方法，如：

* `GET`
* `POST`
* `PUT`

##### `path`

请求路径，不含 `base`。

最终 URL 为：

<pre class="overflow-visible! px-0!" data-start="2875" data-end="2898"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼ5 ͼj"><div class="cm-scroller"><div class="cm-content q9tKkq_readonly"><span>base + path</span></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### 3.7 `body_templates`

每个 endpoint 对应的默认 body 模板。

用于：

* 生成种子
* 说明该接口预期 body 结构

示例：

```json
"body_templates": {
  "cms_doc_list": {
    "docStatusList": [],
    "categoryIdList": [],
    "key": ""
  }
}
```


## 4. 设计原则

### 4.1 target 只描述“目标平台”

不要把复杂验证规则写到 target 文件里。

### 4.2 验证规则统一放到 `validity/*.json`

例如：

* required 字段
* 字段类型
* 最大长度
* 最大数组项数

这些都不属于 target 配置，而属于 validity 配置。

### 4.3 换平台时优先改 target 文件

如果切换到另一个 JSON API 平台，优先修改：

* `base`
* `auth`
* `endpoints`
* `body_templates`

主逻辑代码尽量不改。
