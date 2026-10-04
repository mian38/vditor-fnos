# 第三方组件许可声明（THIRD PARTY NOTICES）

本项目（Vditor 应用，Copyright (c) 2026 mian38）以 MIT 许可发布，详见根目录 [`LICENSE`](LICENSE)。

**本项目的 MIT 许可不覆盖随包分发的第三方组件。** 下列组件保留各自原始版权与许可，
其条款独立于本项目许可，且不因顶层 MIT 而被放宽或覆盖。凡涉及署名与保留声明的要求
（如 BSD 的版权声明、Apache-2.0 的 LICENSE 与 NOTICE、SIL OFL 的字体声明、EPL-1.0 全文）
均已在本仓库中落实——**每个组件目录内均附有其许可文本全文**。

---

## 组件总览

编辑器内核为 [Vditor](https://github.com/Vanessa219/vditor) **4.0.0**（MIT），
其 `dist` 目录随包分发，内含下列第三方渲染组件。

> **版本指纹说明**：本仓库中 `dist/js/lute/lute.min.js`、`dist/js/method.min.js`、
> `dist/js/katex/katex.min.js`、`dist/js/mermaid/mermaid.min.js`、`dist/js/echarts/echarts.min.js`、
> `dist/js/i18n/zh_CN.js`、`dist/js/icons/ant.js`、`dist/index.css` 的 MD5 与官方
> `vditor@4.0.0`（npm / unpkg）**完全一致**，据此确证版本为 4.0.0。
> 其中仅 `dist/index.min.js` 含本项目的本地改动（297,444 字节，官方为 297,357 字节，+87 字节）。

下表路径均相对 `vditor-fpk/app/vditor/`。

| 组件 | 用途 | 许可 | 许可文件（随包） |
|---|---|---|---|
| [Vditor](https://github.com/Vanessa219/vditor) 4.0.0 | 编辑器内核 | MIT | `LICENSE` |
| [KaTeX](https://github.com/KaTeX/KaTeX) 0.16.9 | 公式渲染（库代码） | MIT | `dist/js/katex/LICENSE` |
| KaTeX 字体 | 公式字体（60 个 ttf/woff/woff2） | **SIL OFL 1.1** | `dist/js/katex/fonts/OFL.txt` |
| [Apache ECharts](https://github.com/apache/echarts) 5.6.0 | 图表渲染 | **Apache-2.0** | `dist/js/echarts/LICENSE` + `NOTICE` |
| [highlight.js](https://github.com/highlightjs/highlight.js) 11.7.0 | 代码高亮（249 主题） | **BSD-3-Clause** | `dist/js/highlight.js/LICENSE` |
| [Graphviz Viz.js](https://github.com/mdaines/viz-js) 2.1.2 | 图形渲染 | MIT（封装）+ **EPL-1.0** + MIT(Expat) + zlib | `dist/js/graphviz/EPL-1.0.txt` |
| [Mermaid](https://github.com/mermaid-js/mermaid) 11.16.1 | 流程图/时序图 | MIT | `dist/js/mermaid/LICENSE` |
| [markmap](https://github.com/gera2ld/markmap) 0.14.3 | 思维导图 | MIT | 见下方说明 |
| d3 6.7.0 | markmap 内嵌 | **ISC** | `dist/js/markmap/LICENSE.d3` |
| [abcjs](https://github.com/JonathanRaiman/abcjs) 5.10.3 | 乐谱渲染 | MIT | `dist/js/abcjs/abcjs_basic_5.10.3-min.js.LICENSE` |
| [WaveDrom](https://github.com/Bool-hat/wavedrom) 3.6.2 | 数字电路时序图 | MIT | `dist/js/wavedrom/LICENSE.WaveDrom` |
| [flowchart.js](https://github.com/adrai/flowchart.js) 1.18.0 | 流程图 | MIT | `dist/js/flowchart.js/LICENSE` |
| [smiles-drawer](https://github.com/reymond-group/smilesDrawer) 2.4.1 | 分子结构式 | MIT | `dist/js/smiles-drawer/LICENSE` |
| Lute（随 [Vditor](https://github.com/Vanessa219/vditor) 分发） | Markdown 解析 | MIT | `dist/js/lute/LICENSE` |
| [PlantUML Encoder](https://github.com/markushedvall/plantuml-encoder) 1.4.0 | PlantUML 编码 | MIT | `dist/js/plantuml/LICENSE` |
| [ant-design icons](https://github.com/ant-design/ant-design-icons) | 图标 | MIT | 随 Vditor 分发 |
| Vditor i18n | 中文语言包 | MIT | 随 Vditor 分发 |

---

## 需特别说明的四项

### 1. Apache ECharts —— Apache-2.0 的 NOTICE 义务

Apache-2.0 §4(d) 要求：若原始发行版附带 `NOTICE` 文件，则再分发时必须保留其内容。

本仓库已落实：

- `dist/js/echarts/LICENSE` —— Apache License 2.0 全文
  （取自 <https://www.apache.org/licenses/LICENSE-2.0.txt>）
- `dist/js/echarts/NOTICE` —— ECharts 官方 NOTICE 原文
- `echarts.min.js` 文件头的完整 ASF 授权 banner 原样保留

`echarts.min.js` 内另有 Microsoft Corporation 的独立著作权声明
（`Copyright (c) Microsoft Corporation`，Visual Studio 2013 图标等资源），同样原样保留。

### 2. KaTeX —— 库代码与字体许可是两套独立条款

KaTeX 的**库代码**为 MIT（`dist/js/katex/LICENSE`），但 `dist/js/katex/fonts/` 下的
**60 个字体文件**（`.ttf` / `.woff` / `.woff2`）采用 **SIL Open Font License 1.1**。

SIL OFL 1.1 与 MIT 是**两套独立条款**，MIT 不覆盖这些字体。OFL §2 要求随字体分发
附带许可副本，故 `dist/js/katex/fonts/OFL.txt` 存放 OFL 1.1 全文（官方模板，
<https://openfontlicense.org/documents/OFL.txt>），版权归属为：

- Copyright 2009-2010 Design Science
- Copyright 2014-2018 Khan Academy

OFL 允许自由使用、修改与再分发（含商业用途），要求：

- 保留版权与许可声明，随字体一并分发 ✅（`OFL.txt`）
- **不得单独售卖字体本身**——本项目未单独提取或售卖字体
- 不得使用 Reserved Font Names 冒名——本项目未改名、未单独提取 ✅

本仓库保留全部字体文件原样，符合 OFL 1.1 的保留声明要求。

### 3. Graphviz Viz.js —— EPL-1.0 与其他许可并存（非二选一）

`dist/js/graphviz/viz.js` 文件头（原文保留）声明本发行包含以下第三方组件：

| 组件 | 许可 | 处理 |
|---|---|---|
| Viz.js 2.1.2 封装 | MIT | 保留文件头声明 |
| **Graphviz 2.40.1** | **EPL-1.0** | 全文见 `dist/js/graphviz/EPL-1.0.txt` |
| Expat 2.2.5 | MIT | 保留文件头声明 |
| zlib | zlib 许可 | 保留文件头声明 |

**注意：这不是「MIT OR EPL-1.0」的二选一关系**，而是 Viz.js 以 MIT 封装、
其内嵌的 Graphviz 本体为 EPL-1.0，两种许可在同一发行中并存。

EPL-1.0 属文件级弱 copyleft。Viz.js 官方以 MIT 授权整体分发，允许聚合使用；
本项目原样保留上游文件与全部第三方声明，并补充 EPL-1.0 全文，未剥离任何上游声明。

### 4. markmap —— MIT 主体 + 内嵌 d3（ISC）

markmap 本体为 MIT，但其打包产物 `dist/js/markmap/markmap.min.js` **内嵌 d3 v6.7.0**
（文件头实证：`// https://d3js.org v6.7.0 Copyright 2021 Mike Bostock`），
d3 采用 **ISC** 许可。ISC 要求随分发保留版权与许可声明，故补入
`dist/js/markmap/LICENSE.d3`。

> 另：markmap 产物中另含 js-yaml（MIT）与 @gera2ld/jsx-dom（ISC），
> 其声明保留于产物文件内 banner。

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
- `bump_version.py` —— 版本号同步工具
- `test_*.py` —— 回归测试脚本
- `docs/`、`README.md`、`CHANGELOG.md`、`CHANGELOG_USER.md` —— 文档

所有源文件均带 SPDX 标识：

```python
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
```

---

## 核实方法

本清单的许可信息依据以下方式核实，**未使用任何推测性信息**：

1. **权威上游原文** —— 各组件许可文件取自其官方来源（npm 包、GitHub 仓库、
   官方站点），逐字保留：

   | 许可文件 | 取自 |
   |---|---|
   | `katex/fonts/OFL.txt` | <https://openfontlicense.org/documents/OFL.txt>（SIL 官方） |
   | `graphviz/EPL-1.0.txt` | <https://gitlab.com/graphviz/graphviz/-/raw/2.40.1/epl-v10.txt>（Graphviz 官方，与包内 Graphviz 2.40.1 对应） |
   | `abcjs/..._5.10.3-min.js.LICENSE` | <https://cdn.jsdelivr.net/npm/abcjs@5.10.3/LICENSE.md> |
   | `katex/LICENSE` | <https://cdn.jsdelivr.net/npm/katex@0.16.9/LICENSE> |
   | `mermaid/LICENSE` | <https://cdn.jsdelivr.net/npm/mermaid@11.16.1/LICENSE> |
   | `plantuml/LICENSE` | <https://github.com/markushedvall/plantuml-encoder>（LICENSE） |
   | `smiles-drawer/LICENSE` | <https://cdn.jsdelivr.net/npm/smiles-drawer@2.4.1/LICENSE.md> |
   | `markmap/LICENSE.d3` | <https://cdn.jsdelivr.net/npm/d3@6.7.0/LICENSE> |
   | `echarts/LICENSE` | <https://www.apache.org/licenses/LICENSE-2.0.txt> |

2. **包内文件实证** —— 从 `*.min.js` 文件头直接提取版权与许可声明
   （ECharts 的完整 ASF banner、abcjs 的版权行与 LICENSE 指向、markmap 内 d3 的
   ISC 声明、viz.js 的 Graphviz/Expat/zlib 声明、highlight.js 的 BSD-3-Clause 声明）
3. **官方包元数据** —— 对无独立 LICENSE 文件的组件（flowchart.js、Lute），
   查其 npm `package.json` 的 `license` / `author` 字段确证

**特殊情况说明**：

- **Lute** ——   随 Vditor 主仓库一同分发，上游无独立仓库（原 `b3log/Lute` 地址已实测返回 404）。因与 Vditor 同源、著作权相同，按 MIT 处理，并由 Vditor 顶层
  `LICENSE`（MIT, Copyright (c) 2019-present B3log 开源, b3log.org）覆盖。
  该说明已写入 `dist/js/lute/LICENSE`。
- **flowchart.js** —— 上游未提供独立 LICENSE 文件，许可与作者取自其官方
  `package.json`（`license: MIT`, `author: adrai`），说明已写入对应文件。
