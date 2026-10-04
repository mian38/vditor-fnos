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

// ---------- 静态结构校验 ----------
console.log('\n静态结构校验：');
check('openFile 自动进/出纯文本后调用 updateRawModeBtn()', /updateRawModeBtn\(\);\s*\/\/\s*自动进\/出纯文本/.test(code));
check('textarea wrap="soft"（软换行）', /id="raw-editor"[^>]*wrap="soft"/.test(html));
check('#raw-editor CSS white-space: pre-wrap', /#raw-editor\s*\{[\s\S]*?white-space:\s*pre-wrap/.test(html));
check('enterRawMode 超大时调用 destroyVditor()', /if \(typeof len === 'number' && len > RAW_AUTO_CHARS && vditor\) \{\s*destroyVditor\(\);/.test(code));
check('exitRawMode 重建走 pendingRichText + buildVditor()', /else \{ pendingRichText = text; buildVditor\(\); \}/.test(code));
check('updateCounter 不再以 vditor 存在为前提', /if \(!rawMode && !vditor\) return;/.test(code));

// ---------- [10] 1.4.1 渲染模式三态 + 临时态 ----------
// 直接驱动 decideRenderMode / effectiveRenderMode 验证判定优先级：临时态 > 持久化 > 自动分级
// 注意：renderModeSetting 是脚本顶层的 let 绑定，不挂在 vm 的 global 上，
// 外部无法直接赋值；须用 runInContext 在同一词法环境内赋值。
function segSet(v) { vm.runInContext('renderModeSetting = ' + JSON.stringify(v) + ';', sandbox); }
function onceSet(v) { vm.runInContext('renderModeOnce = ' + (v === null ? 'null' : JSON.stringify(v)) + ';', sandbox); }
segSet('auto');
check('auto：小文档走富文本', sandbox.decideRenderMode(1000) === 'rich');
check('auto：超阈值走纯文本', sandbox.decideRenderMode(400000) === 'raw');
segSet('rich');
check('rich：一律富文本（含超大文档）', sandbox.decideRenderMode(400000) === 'rich');
segSet('raw');
check('raw：一律纯文本（含小文档）', sandbox.decideRenderMode(1000) === 'raw');
// 临时态覆盖持久化设置
segSet('rich');
onceSet('raw');
check('临时态 raw 覆盖持久化 rich', sandbox.effectiveRenderMode() === 'raw');
check('临时态下小文档也判定为 raw', sandbox.decideRenderMode(1000) === 'raw');
onceSet('rich');
check('临时态 rich 覆盖持久化 rich（仍为富文本）', sandbox.effectiveRenderMode() === 'rich');
onceSet('raw');
segSet('auto');
check('临时态 raw 覆盖持久化 auto', sandbox.effectiveRenderMode() === 'raw');
check('临时态 raw 时超大文档判定为 raw', sandbox.decideRenderMode(400000) === 'raw');
onceSet(null);
check('清除临时态后回到持久化设置 auto', sandbox.effectiveRenderMode() === 'auto');
check('清除临时态后超大文档重新按自动分级为 raw', sandbox.decideRenderMode(400000) === 'raw');
check('清除临时态后小文档重新按自动分级为 rich', sandbox.decideRenderMode(1000) === 'rich');
segSet('auto');

// ---------- [10b] 1.4.2 顶栏按钮承载临时态 + 仅大文档可见 ----------
// 按钮显隐：小文档隐藏 / 大文档显示
vm.runInContext('currentPath = null;', sandbox);
sandbox.updateRawModeBtn();
check('未打开文档时按钮隐藏', getEl('btn-raw-mode').hidden === true);
vm.runInContext('currentPath = "a.md";', sandbox);
sandbox.setContent('短');                      // 小文档
sandbox.updateRawModeBtn();
check('小文档时按钮隐藏（1.4.2）', getEl('btn-raw-mode').hidden === true);
sandbox.setContent('数据 '.repeat(300000));    // 超阈值大文档
sandbox.updateRawModeBtn();
check('大文档时按钮显示（1.4.2）', getEl('btn-raw-mode').hidden === false);
check('大文档按钮文案表示目标模式（当前富文本 → 显示「纯文本」）',
      getEl('btn-raw-mode').textContent === '纯文本');
check('设置页临时态控件已删除', !/btn-once/.test(html));
check('按钮 title 标注仅本次生效', /仅本次生效/.test(getEl('btn-raw-mode').title));

// ---------- [11] 1.4.1 二次确认按钮：取消为主色蓝、确认置白 ----------
check('确认框：取消按钮为高亮主色（蓝）', /#confirm-mask #confirm-cancel\s*\{[\s\S]*?background:\s*var\(--c-brand\)/.test(html));
check('确认框：确认按钮为白底', /#confirm-mask #confirm-ok\s*\{[\s\S]*?background:\s*#fff/.test(html));
check('确认框：取消按钮在确认按钮之前（默认视线落在取消）',
   html.indexOf('id="confirm-cancel"') < html.indexOf('id="confirm-ok"'));
check('确认框正文支持换行（多段落风险说明）', /#confirm-msg \{ white-space: pre-line/.test(html));
// 两个安全开关各自有专属风险文案（不再是共用一句泛化提示）
check('secure_cookie 关闭确认含「明文」风险说明',
   /强制 Cookie Secure 标记[\s\S]{0,900}明文/.test(code));
check('secure_cookie 关闭确认含「不建议」', /强烈不建议这么做/.test(code));

// ---------- [12] 1.4.1 公网访问 / IPv6 文案与免责 ----------
check('设置页说明公网 HTTP 被拒绝（secure cookie 开启时）', /公网 HTTP 连接（如 <code>http:\/\/公网IP:3838<\/code>）将被拒绝访问/.test(html));
check('设置页说明局域网 HTTP 不受影响', /局域网 HTTP 连接（如 <code>http:\/\/局域网IP:3838<\/code>）可正常访问，不受影响/.test(html));
check('设置页说明纯 HTTP 不提供 HTTPS', /不提供 HTTPS<\/b>，无法使用 <code>https:\/\/公网IP:3838<\/code>/.test(html));
check('设置页含风险自负免责段', /风险自负/.test(html) && /不对由此产生的任何数据泄露或损失承担责任/.test(html));
check('设置页说明支持 IPv6 访问', /同时监听 IPv4 与 IPv6/.test(html));
check('设置页说明 IPv6 需方括号', /http:\/\/\[局域网IPv6\]:3838/.test(html));
// 安装引导同步
const wizard = fs.readFileSync(path.join(__dirname, 'wizard', 'install'), 'utf8');
check('安装引导：说明默认禁止公网访问', /默认禁止<\/b>以 <b>公网IP\/域名:3838/.test(wizard));
check('安装引导：说明需关闭 secure cookie 才能公网访问', /关闭「强制 Cookie Secure 标记」<\/b>。关闭后公网 HTTP 可正常访问/.test(wizard));
check('安装引导：含明文传输风险与不建议', /以明文传输/.test(wizard) && /强烈不建议这么做/.test(wizard));
check('安装引导：说明系统分区路径', /\/vol1\/@appshare\/vditor-docs/.test(wizard));
check('安装引导：说明旧分区不迁移', /不会被自动迁移/.test(wizard));

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
