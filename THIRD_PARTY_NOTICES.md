# 第三方组件许可声明（THIRD PARTY NOTICES）

本项目（Vditor 应用，Copyright (c) 2026 mian38）以 MIT 许可发布，详见根目录 [`LICENSE`](LICENSE)。

**本项目的 MIT 许可不覆盖随包分发的第三方组件。** 下列组件保留各自原始版权与许可，
其条款独立于本项目许可，且不因顶层 MIT 而被放宽或覆盖。凡涉及署名与保留声明的要求
（如 BSD 的版权声明、Apache-2.0 的 LICENSE 与 NOTICE、SIL OFL 的字体声明）均已在本仓库中落实。

---

## 组件总览

编辑器内核为 [Vditor](https://github.com/Vditor/Vditor) **4.0.0**（MIT），
其 `dist` 目录随包分发，内含下列第三方渲染组件。

> **版本指纹说明**：本仓库中 `dist/js/lute/lute.min.js`、`dist/js/method.min.js`、
> `dist/js/katex/katex.min.js`、`dist/js/mermaid/mermaid.min.js`、`dist/js/echarts/echarts.min.js`、
> `dist/js/i18n/zh_CN.js`、`dist/js/icons/ant.js`、`dist/index.css` 的 MD5 与官方
> `vditor@4.0.0`（npm / unpkg）**完全一致**，据此确证版本为 4.0.0。
> 其中仅 `dist/index.min.js` 含本项目的本地改动（297,444 字节，官方为 297,357 字节，+87 字节）。

| 组件 | 用途 | 许可 | 原文位置 |
|---|---|---|---|
| [Vditor](https://github.com/Vditor/Vditor) 4.0.0 | 编辑器内核 | MIT | `app/vditor/LICENSE` |
| [KaTeX](https://github.com/KaTeX/KaTeX) | 公式渲染（库） | MIT | 见下方说明 |
| KaTeX 字体 | 公式字体（60 个 ttf/woff/woff2） | **SIL OFL 1.1** | 见下方说明 |
| [highlight.js](https://github.com/highlightjs/highlight.js) | 代码高亮（249 主题） | BSD-3-Clause | `dist/js/highlight.js/LICENSE` |
| [Apache ECharts](https://github.com/apache/echarts) | 图表渲染 | **Apache-2.0** | `dist/js/echarts/LICENSE` + `NOTICE` |
| [Mermaid](https://github.com/mermaid-js/mermaid) | 流程图/时序图 | MIT | 随Vditor 分发 |
| [markmap](https://github.com/gera2ld/markmap) | 思维导图 | ISC | 随 Vditor 分发 |
| [Graphviz viz.js](https://github.com/mdaines/viz-js) | 图形渲染 | MIT **OR** EPL-1.0 | `dist/js/graphviz/viz.js` |
| [abcjs](https://github.com/JonathanRaiman/abcjs) | 乐谱渲染 | MIT | 随 Vditor 分发 |
| [WaveDrom](https://github.com/Bool-hat/wavedrom) | 数字电路时序图 | MIT | `dist/js/wavedrom/LICENSE.WaveDrom` |
| [flowchart.js](https://github.com/adrai/flowchart.js) | 流程图 | MIT | 随 Vditor 分发 |
| [smiles-drawer](https://github.com/reymond-group/smilesDrawer) | 分子结构式 | MIT | 随 Vditor 分发 |
| [Lute](https://github.com/b3log/Lute) | Markdown 解析 | MIT | 随 Vditor 分发 |
| [ant-design icons](https://github.com/ant-design/ant-design-icons) | 图标 | MIT | 随 Vditor 分发 |
| Vditor i18n | 中文语言包 | MIT | 随 Vditor 分发 |
| [PlantUML Encoder](https://github.com/plantuml/plantuml-encoder) | PlantUML 编码 | MIT | 随 Vditor 分发 |

---

## 需特别说明的两项

### 1. Apache ECharts —— Apache-2.0 的 NOTICE 义务

Apache-2.0 §4(d) 要求：若原始发行版附带 `NOTICE` 文件，则再分发时必须保留其内容。

本仓库已落实：

- `vditor-fpk/app/vditor/dist/js/echarts/LICENSE` —— Apache License 2.0 全文
  （取自 <https://www.apache.org/licenses/LICENSE-2.0.txt>）
- `vditor-fpk/app/vditor/dist/js/echarts/NOTICE` —— ECharts 官方 NOTICE 原文
- `echarts.min.js` 文件头的完整 ASF 授权 banner 原样保留

`echarts.min.js` 内另有 Microsoft Corporation 的独立著作权声明
（`Copyright (c) Microsoft Corporation`，Visual Studio 2013 图标等资源），同样原样保留。

### 2. KaTeX —— 库代码与字体许可不同

KaTeX 的**库代码**为 MIT，但 `dist/js/katex/fonts/` 下的 **60 个字体文件**
（`.ttf` / `.woff` / `.woff2`）采用 **SIL Open Font License 1.1**。

SIL OFL 1.1 与 MIT 是**两套独立条款**，MIT 不覆盖这些字体。字体版权归：

- Copyright 2009-2010 Design Science
- Copyright 2014-2018 Khan Academy

OFL 允许自由使用、修改与再分发（含商业用途），要求：

- 保留版权与许可声明，随字体一并分发
- **不得单独售卖字体本身**
- 不得使用 Reserved Font Names 冒名

本仓库保留全部字体文件原样（未改名、未单独提取），符合 OFL 1.1 的保留声明要求。

---

## Vditor 本地改动说明

`dist/index.min.js` 相对官方 4.0.0 有 +87 字节的本地改动，用于中文语言包内联等适配。
改动不涉及任何第三方组件的许可条款，亦未移除上游版权声明。

其余 Vditor `dist` 文件与官方 4.0.0 逐字节一致（MD5 已逐一比对，见上方「版本指纹说明」）。

---

## 本项目自研代码

以下部分为本项目原创，采用 MIT 许可（Copyright (c) 2026 mian38）：

- `vditor-fpk/app/server.py` —— HTTP 服务、认证、会话、文档与资源 API
- `vditor-fpk/app/vd_util.py` —— 无副作用工具函数与常量
- `vditor-fpk/app/index.html` —— 单页前端（含内联样式 `ui_style_v414`）
- `vditor-fpk/app/ui/` —— 前端样式与脚本
- `make_nas.py`、`bump_version.py`、`build_fpk.py` —— 构建与发布工具
- `test_*.py` —— 回归测试脚本
- `docs/`、`README.md`、`CHANGELOG.md`、`CHANGELOG_USER.md` —— 文档

所有源文件均带 SPDX 标识：

```python
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
```

---

## 核实方法

本清单中标注「随 Vditor 分发」的组件，其许可信息依据以下方式核实：

1. **文件内banner 实证** —— 从 `*.min.js` 文件头直接提取版权与许可声明
   （ECharts 的完整 ASF banner、abcjs 的 MIT 声明、markmap 的 ISC 声明、
   viz.js 的 MIT/EPL 双许可声明、highlight.js 的 BSD-3-Clause 声明）
2. **随包许可文件** —— 读取 `highlight.js/LICENSE`、`wavedrom/LICENSE.WaveDrom`、
   `echarts/LICENSE`（本次补入）、`echarts/NOTICE`（本次补入）
3. **上游仓库核实** —— 对无内嵌 banner 的组件（flowchart.js、smiles-drawer、
   KaTeX 字体）查询其上游仓库的许可声明

**未使用任何推测性信息。** 凡无法从文件或上游仓库确证的，均已在上表注明来源。
