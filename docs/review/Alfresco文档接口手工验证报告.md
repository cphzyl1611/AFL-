# Alfresco文档接口手工验证报告

## 背景

Alfresco Community Edition 已在本地 Docker Compose 环境启动。本报告记录已完成的本地手工接口验证结果，用于评估 Alfresco 文档管理接口对“电子公文创建与保存 / 内容更新”业务语义的替代验证能力。

## Root node API 验证

Root node API 验证成功，接口返回 `Company Home`，说明 Alfresco Repository 基础文档空间可访问。

## 文档创建与保存验证

文档创建与保存验证成功。

验证结果：

- 创建文件：`official_doc_v1.txt`
- 返回 `nodeType=cm:content`
- 返回 `node id=ef8f299c-2109-4a85-8f29-9c21095a853f`
- 返回 `versionLabel=1.0`

结论：Alfresco 可通过文档节点创建接口完成标准内容节点创建，并返回稳定的节点标识和初始版本信息。

## 文档内容更新验证

文档内容更新验证成功。

验证方式：

```text
PUT /nodes/{id}/content
```

验证结果：

- 使用同一 `node id` 更新内容
- `versionLabel` 从 `1.0` 变为 `1.1`
- 返回 `versionType=MINOR`

结论：Alfresco 可在保持同一文档节点标识的前提下完成内容更新，并通过版本号体现内容变更。

## 文档元数据更新验证

文档元数据更新验证成功。

验证方式：

```text
PUT /nodes/{id}
```

验证结果：

- `name` 更新为 `official_doc_updated.txt`
- `cm:title` 更新成功
- `cm:description` 更新成功

结论：Alfresco 支持通过 JSON 请求更新文档节点元数据，适合承载电子公文标题、描述等结构化字段的替代验证。

## 结论

Alfresco 可作为标准文档管理平台，用于验证“电子公文创建与保存 / 内容更新”这类业务语义接口。

该验证不是 O2OA 原生电子公文接口覆盖。

后续优先接入 JSON 元数据更新接口，因为它最适配当前 body-only JSON fuzz 框架。

multipart 文件上传和 `text/plain` 内容更新作为后续扩展。
