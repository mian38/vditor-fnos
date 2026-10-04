// 1.4 专项测试（前端逻辑，无浏览器）：解耦 Vditor + 轻量计数 + 模式切换按钮 + 自动换行
// 该测试只覆盖本轮改动相关逻辑，不执行全量回归。
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, 'app', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) { console.error('FAIL: 未找到主内联脚本'); process.exit(1); }
const code = m[1];

// ---------- 极简 DOM / 浏览器 桩 ----------
function makeEl(id) {
  return {
    _id: id, textContent: '', title: '', value: '', hidden: false, innerHTML: '',
    style: {}, dataset: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, f) { if (f === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); } else { f ? this._s.add(c) : this._s.delete(c); } },
      contains(c) { return this._s.has(c); }
    },
    addEventListener() {}, removeEventListener() {}, setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, removeChild() {}, click() {}, focus() {},
    querySelector() { return makeEl('q'); }, querySelectorAll() { return []; }, closest() { return null; }
  };
}
const elCache = {};
function getEl(id) { return elCache[id] || (elCache[id] = makeEl(id)); }

const documentStub = {
  getElementById: (id) => getEl(id),
  querySelector: () => getEl('qs'),
  querySelectorAll: () => [],
  addEventListener() {}, createElement: () => makeEl('created'),
  body: { classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, f) { f ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } } },
  documentElement: { getAttribute: () => null, setAttribute() {} }
};

const allVditorStubs = [];
class VditorStub {
  constructor(sel, opts) {
    this.sel = sel; this.opts = opts; this._val = ''; this._destroyed = false;
    this.vditor = { destroy() {}, options: { upload: { extraData: {} } } };
    allVditorStubs.push(this);
    // 真实 Vditor 在编辑器就绪后异步调用 after()；此处同步调用以驱动 setContent 等副作用
    if (opts && typeof opts.after === 'function') { try { opts.after(); } catch (e) { console.error('after() threw:', e.message); throw e; } }
  }
  getValue() { return this._val; }
  setValue(v) { this._val = (v == null ? '' : String(v)); }
  setTheme() {}
  destroy() { this._destroyed = true; }
}

const localStorageStub = { _m: {}, getItem(k) { return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; }, setItem(k, v) { this._m[k] = v; }, removeItem(k) { delete this._m[k]; } };

const windowStub = {
  isSecureContext: false,
  matchMedia: () => ({ matches: false }),
  addEventListener() {}, removeEventListener() {},
  performance: { now: () => Date.now() },
  requestAnimationFrame: (cb) => { cb(0); return 1; },
  localStorage: localStorageStub,
  navigator: { mediaDevices: undefined },
  fetch: fetchStub
};

function fetchStub() { return Promise.resolve({ json: () => Promise.resolve({ authenticated: false, needsSetup: true }) }); }

const sandbox = {
  document: documentStub, window: windowStub, Vditor: VditorStub,
  localStorage: localStorageStub, navigator: windowStub.navigator,
  performance: windowStub.performance, requestAnimationFrame: windowStub.requestAnimationFrame,
  fetch: fetchStub, setTimeout, clearTimeout, console, JSON, Math, Date, RegExp, Promise,
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
  queueMicrotask
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// ---------- 断言工具 ----------
let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name); }
}

// ---------- 运行脚本（顶层会调用 initTheme + checkAuth） ----------
try {
  vm.runInContext(code, sandbox, { filename: 'index-inline.js' });
  console.log('[1] 脚本加载与顶层执行无异常');
} catch (e) {
  console.error('FAIL: 脚本加载抛错: ' + e.message);
  console.error(e.stack);
  process.exit(1);
}
check('initEditorAndFiles 为可调用函数', typeof sandbox.initEditorAndFiles === 'function');

// ---------- [2] 启动构建 Vditor（默认教程，小体积） ----------
sandbox.initEditorAndFiles();
check('启动后创建 Vditor 实例', allVditorStubs.length === 1 && !allVditorStubs[0]._destroyed);
check('_buildVditorImpl 已注入', typeof sandbox.buildVditor === 'function' && typeof sandbox.destroyVditor === 'function');

// ---------- [3] 进入超大文档纯文本模式 -> 应销毁 Vditor（解耦核心） ----------
const BIG = '数据 '.repeat(3_000_000); // ~ 6MB，远超 RAW_AUTO_CHARS(30万)
getEl('raw-editor').value = BIG;
sandbox.enterRawMode('自动进入纯文本', BIG.length);
check('超大文档进入纯文本后销毁 Vditor', allVditorStubs[0]._destroyed === true);
check('#vditor 容器被清空', getEl('vditor').innerHTML === '');
check('body 进入 raw-mode', documentStub.body.classList.contains('raw-mode'));

// ---------- [4] 轻量计数：Vditor 销毁后计数仍正常工作（不依赖 vditor） ----------
let threw = false, wcText = '';
try {
  sandbox.updateCounter();
  wcText = getEl('wc-text').textContent;
} catch (e) { threw = true; console.error('updateCounter 抛错:', e.message); }
check('Vditor 为 null 时 updateCounter 不抛错', !threw);
check('updateCounter 写入正文字数', typeof wcText === 'string' && wcText.length > 0);

// ---------- [5] 按钮文案与真实模式一致（歧义修复） ----------
sandbox.updateRawModeBtn();
check('纯文本模式下按钮显示「富文本」（点击即切回）', getEl('btn-raw-mode').textContent === '富文本');
check('纯文本模式下按钮 title 说明切回', /富文本/.test(getEl('btn-raw-mode').title));

// ---------- [6] 切回富文本 -> 惰性重建 Vditor 并灌入来源文本（pendingRichText） ----------
const beforeCount = allVditorStubs.length;
sandbox.exitRawMode();
check('切回富文本触发 Vditor 惰性重建', allVditorStubs.length === beforeCount + 1);
const rebuilt = allVditorStubs[allVditorStubs.length - 1];
sandbox.setContent(BIG); // setContent 现在走 vditor.setValue（富文本已重建）
check('重建后 setContent 把来源文本写入 Vditor', rebuilt._val === BIG);
sandbox.updateRawModeBtn();
check('富文本模式下按钮显示「纯文本」（点击即切纯文本）', getEl('btn-raw-mode').textContent === '纯文本');

// ---------- [7] 手动切纯文本：富文本内容须被带入 textarea（不丢内容） ----------
sandbox.setContent('手动切换保留内容测试');   // 富文本模式下写入
sandbox.enterRawMode('手动切纯文本', 100);    // 小规模，不销毁
check('手动切纯文本把富文本内容带入编辑框', getEl('raw-editor').value === '手动切换保留内容测试');

// ---------- [8] leaveRawMode：打开小文件不把旧超大内容误灌进 Vditor ----------
const c1 = allVditorStubs.length;
sandbox.leaveRawMode();
check('leaveRawMode 不重复重建 Vditor（已有则不建）', allVditorStubs.length === c1);
sandbox.updateRawModeBtn();
check('离开纯文本后按钮回到「纯文本」', getEl('btn-raw-mode').textContent === '纯文本');

// ---------- [9] 轻量计数性能：15MB 采样估算应远小于全文 O(n) ----------
const huge = ('中文正文内容用于字数统计采样测试 '.repeat(200000)); // ~ 15MB
const t0 = Date.now();
const r = sandbox.countReaderWords(huge);
const dt = Date.now() - t0;
check('countReaderWords 对 15MB 返回正整数', Number.isInteger(r) && r > 0);
check('countReaderWords 采样估算 O(200K) 耗时 < 300ms', dt < 300);
// 采样外推正确性：取前 200K 精确值 * 比例，应与整体量级一致
const sample = huge.slice(0, 200000);
const nSample = sandbox.countReaderWordsExact(sample);
const expected = Math.round(nSample * (huge.length / sample.length));
check('采样外推与公式一致 r≈预期', Math.abs(r - expected) <= 1);

// ---------- 汇总 ----------
console.log('\n静态结构校验：');
check('openFile 自动进/出纯文本后调用 updateRawModeBtn()', /updateRawModeBtn\(\);\s*\/\/\s*自动进\/出纯文本/.test(code));
check('textarea wrap="soft"（软换行）', /id="raw-editor"[^>]*wrap="soft"/.test(html));
check('#raw-editor CSS white-space: pre-wrap', /#raw-editor\s*\{[\s\S]*?white-space:\s*pre-wrap/.test(html));
check('enterRawMode 超大时调用 destroyVditor()', /if \(typeof len === 'number' && len > RAW_AUTO_CHARS && vditor\) \{\s*destroyVditor\(\);/.test(code));
check('exitRawMode 重建走 pendingRichText + buildVditor()', /else \{ pendingRichText = text; buildVditor\(\); \}/.test(code));
check('updateCounter 不再以 vditor 存在为前提', /if \(!rawMode && !vditor\) return;/.test(code));

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
