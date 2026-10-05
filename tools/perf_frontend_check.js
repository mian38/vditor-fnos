/**
 * perf_frontend_check.js —— 前端字数统计路径的性能验证
 *
 * 背景：旧的 readerVisibleText() 调用 vditor.getHTML()，会对全文再跑一次 Lute 渲染，
 * 并把生成的 HTML 用 innerHTML 重建一棵离屏 DOM，再 textContent 遍历——单次打开
 * 触发 3 次以上，是大文件卡顿的最大放大器。
 *
 * 优化后改为纯字符串正则剥离（stripMarkdown），不触碰 DOM、不触发渲染。
 * 本脚本从 index.html 提取该函数，用真实大样本测量其耗时，确认优化有效。
 *
 * 运行：node tools/perf_frontend_check.js
 */
const fs = require('fs');
const path = require('path');

// 本脚本位于 tools/ 下，仓库根为其上一级目录
const ROOT = path.join(__dirname, '..');
const HTML = path.join(ROOT, 'vditor-fpk', 'app', 'index.html');

// 样本来源优先级：命令行参数 > 环境变量 PERF_SAMPLES > 内置合成样本。
// 说明：不硬编码任何本机路径（避免把个人目录结构写进仓库）。
// 内置合成样本刻意做成「代码块 + 标题密集」的对话记录形态——因为渲染成本
// 与块级结构数量相关，而非字节数，只有高密度样本才能真正压出渲染路径开销。
function synth(targetChars) {
    const unit = '## 段落 {i}\n\n中英文混排 content {i} 用于压测。\n\n'
        + '```python\ndef f_{i}():\n    return sum(range({i}))\n```\n\n'
        + '| A | B |\n| --- | --- |\n| v{i} | d |\n\n';
    let out = [], size = 0, i = 0;
    while (size < targetChars) {
        const s = unit.replace(/\{i\}/g, String(i));
        out.push(s); size += s.length; i++;
    }
    return out.join('');
}

const argSamples = process.argv.slice(2);
const envSamples = process.env.PERF_SAMPLES
    ? process.env.PERF_SAMPLES.split(',').map(s => s.trim()).filter(Boolean) : [];

const SAMPLES = argSamples.length ? argSamples
    : envSamples.length ? envSamples
        : [{ name: 'synthetic-1M', text: synth(1000000), synthetic: true },
           { name: 'synthetic-5M', text: synth(5000000), synthetic: true }];

// 读取样本文本：真实文件走 fs，合成样本直接用
function readSample(s) {
    if (typeof s === 'string') {
        if (!fs.existsSync(s)) return null;
        return { name: path.basename(s), text: fs.readFileSync(s, 'utf8') };
    }
    return { name: s.name, text: s.text };
}

const html = fs.readFileSync(HTML, 'utf8');

// ---- 从 index.html 提取被测函数体（按括号配平取完整函数） ----
function extractFn(name) {
    const key = 'function ' + name + '(';
    const start = html.indexOf(key);
    if (start === -1) return null;
    let depth = 0, i = html.indexOf('{', start), end = -1;
    for (; i < html.length; i++) {
        if (html[i] === '{') depth++;
        else if (html[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
    }
    return html.slice(start, end);
}
eval(extractFn('stripMarkdown'));
const COUNT_SAMPLE_CHARS = 200000;          // 与 index.html 保持一致
eval(extractFn('countReaderWordsExact'));
eval(extractFn('countReaderWords'));
if (typeof stripMarkdown !== 'function' || typeof countReaderWords !== 'function') {
    console.error('FAIL: 未能从 index.html 提取函数'); process.exit(1);
}

// ---- 校验关键阈值常量存在 ----
// 1.5.0：自动降级阈值口径由字符数改为 UTF-8 字节数，符号随之改名。
const need = ['RAW_AUTO_BYTES', 'COUNT_FAST_CHARS', 'enterRawMode', 'exitRawMode', 'toggleRawMode'];
let ok = true;
for (const k of need) {
    const has = html.includes(k);
    console.log(`  ${has ? 'PASS' : 'FAIL'} index.html 含 ${k}`);
    if (!has) ok = false;
}

// ---- 用样本测量 ----
console.log('\n-- stripMarkdown 在样本上的耗时 --');
for (const s of SAMPLES) {
    const sample = readSample(s);
    if (!sample) { console.log(`  (跳过，不存在) ${typeof s === 'string' ? s : s.name}`); continue; }
    const text = sample.text;
    const chars = text.length;
    const bytes = Buffer.byteLength(text, 'utf8');

    // 预热一次，避免首次 JIT 编译计入
    stripMarkdown(text.slice(0, 1000));

    const t0 = process.hrtime.bigint();
    const out = stripMarkdown(text);
    const t1 = process.hrtime.bigint();
    const ms = Number(t1 - t0) / 1e6;

    console.log(`  ${sample.name}`);
    console.log(`    原文 ${chars.toLocaleString()} 字符 / ${(bytes / 1024 / 1024).toFixed(2)} MB`);
    console.log(`    剥离后 ${out.length.toLocaleString()} 字符，耗时 ${ms.toFixed(1)} ms`);
    console.log(`    缩减率 ${(100 - out.length / chars * 100).toFixed(1)}%`);
    if (ms > 3000) { console.log('    ⚠️ 耗时偏高'); ok = false; }
}

// ---- 字数统计在超大文本上的耗时（验证采样估算生效） ----
console.log('\n-- countReaderWords 在超大文本上的耗时 --');
for (const s of SAMPLES) {
    const sample = readSample(s);
    if (!sample) continue;
    const stripped = stripMarkdown(sample.text);
    countReaderWords(stripped.slice(0, 1000));      // 预热
    const t0 = process.hrtime.bigint();
    const n = countReaderWords(stripped);
    const t1 = process.hrtime.bigint();
    const ms = Number(t1 - t0) / 1e6;
    console.log(`  ${sample.name}: 统计 ${n.toLocaleString()} 字，耗时 ${ms.toFixed(1)} ms`);
    if (ms > 500) { console.log('    ⚠️ 耗时偏高'); ok = false; }
}

// ---- 正确性：几类语法应被剥离 ----
console.log('\n-- stripMarkdown 正确性抽查 --');
const cases = [
    ['# 标题', '标题'],
    ['**粗体**文本', '粗体文本'],
    ['`行内代码` 后', ' 后'],
    ['[链接文字](http://x.com)', '链接文字'],
    ['> 引用内容', '引用内容'],
    ['- 列表项', '列表项'],
    ['```\ncode block\n```\n可见', ' 可见'],
];
for (const [input, expect] of cases) {
    const got = stripMarkdown(input).trim();
    const okk = got === expect.trim();
    console.log(`  ${okk ? 'PASS' : 'FAIL'} ${JSON.stringify(input)} -> ${JSON.stringify(got)}`);
    if (!okk) ok = false;
}

console.log('\n' + (ok ? 'RESULT(frontend-perf): ALL OK' : 'RESULT(frontend-perf): HAS FAILURE'));
process.exit(ok ? 0 : 1);
