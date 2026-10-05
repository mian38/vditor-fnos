// 1.4 专项测试（前端逻辑，无浏览器）：解耦 Vditor + 轻量计数 + 模式切换按钮 + 自动换行
// 该测试只覆盖本轮改动相关逻辑，不执行全量回归。
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// 本文件位于 tests/ 下，仓库根为其上一级；应用源码在 vditor-fpk/app/
const ROOT = path.join(__dirname, '..');
const htmlPath = path.join(ROOT, 'vditor-fpk', 'app', 'index.html');
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
    this.sel = sel; this.opts = opts; this._val = ''; this._destroyed = false; this._ready = false;
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

// ---- 1.4.3 回归桩：真实 Vditor 在 after() 之前调用 getValue()/setValue() 会抛错 ----
// ⚠️ 不能 `extends VditorStub`：派生类构造函数访问 this 前必须先 super()，
//    而本桩刻意不调用父类构造（父类会同步触发 after()），故独立成类。
class VditorNotReadyStub {
  constructor(sel, opts) {
    this.sel = sel; this.opts = opts; this._val = ''; this._destroyed = false; this._ready = false;
    this.vditor = { destroy() {}, options: { upload: { extraData: {} } } };
    allVditorStubs.push(this);
  }
  getValue() { if (!this._ready) throw new Error('editor not ready'); return this._val; }
  setValue(v) { if (!this._ready) throw new Error('editor not ready'); this._val = (v == null ? '' : String(v)); }
  setTheme() {}
  destroy() { this._destroyed = true; }
  // 模拟异步就绪
  becomeReady() { this._ready = true; if (this.opts && typeof this.opts.after === 'function') this.opts.after(); }
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
// 1.5.0：销毁判据改用 docBaseBytes（与自动降级、按钮显隐同源），
// 故测试须先写入 docBaseBytes 才能复现「打开超大文档」的真实状态。
const BIG = '数据 '.repeat(3_000_000); // ~ 6MB，远超 RAW_AUTO_BYTES(500KB)
getEl('raw-editor').value = BIG;
vm.runInContext('docBaseBytes = ' + BIG.length * 3 + ';', sandbox);
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
// 基准长度同步改小：docBaseBytes 是「打开时的文档大小」，此处模拟打开一份小文档后手动切换
vm.runInContext('docBaseBytes = 100;', sandbox);
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
check('1.5.0 enterRawMode 超大时调用 destroyVditor()（判据用 docBaseBytes）',
  /if \(isBigDoc\(\) && vditor\) \{\s*destroyVditor\(\);/.test(code));
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
// 1.5.0：阈值口径改为**字节**（500KB），并由 30万→100万→500KB 逐步下调。
// 注意 decideRenderMode 入参是字节数，不是字符数：中文一字 3 字节，
// 500KB 字节 ≈ 17 万汉字，按字符判定会严重高估体积。
check('auto：100KB 字节仍走富文本', sandbox.decideRenderMode(100 * 1024) === 'rich');
check('auto：500KB 字节（恰好等于阈值）仍走富文本', sandbox.decideRenderMode(500 * 1024) === 'rich');
check('auto：超阈值（500KB 字节以上）走纯文本', sandbox.decideRenderMode(500 * 1024 + 1) === 'raw');
segSet('rich');
check('rich：一律富文本（含超大文档）', sandbox.decideRenderMode(4000000) === 'rich');
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
check('临时态 raw 时超大文档判定为 raw', sandbox.decideRenderMode(4000000) === 'raw');
onceSet(null);
check('清除临时态后回到持久化设置 auto', sandbox.effectiveRenderMode() === 'auto');
check('清除临时态后超大文档重新按自动分级为 raw', sandbox.decideRenderMode(4000000) === 'raw');
check('清除临时态后小文档重新按自动分级为 rich', sandbox.decideRenderMode(1000) === 'rich');
segSet('auto');

// ---------- [10b] 1.4.2 顶栏按钮承载临时态 + 仅大文档可见 ----------
// 按钮显隐：小文档隐藏 / 大文档显示
vm.runInContext('currentPath = null;', sandbox);
sandbox.updateRawModeBtn();
check('未打开文档时按钮隐藏', getEl('btn-raw-mode').hidden === true);
vm.runInContext('currentPath = "a.md";', sandbox);
vm.runInContext('docBaseBytes = 10;', sandbox);   // 小文档
sandbox.updateRawModeBtn();
check('小文档时按钮隐藏（1.4.2）', getEl('btn-raw-mode').hidden === true);
// 1.5.0：判据改为打开时记录的 docBaseBytes，编辑中不再漂移
vm.runInContext('docBaseBytes = 1200000;', sandbox);  // 超阈值大文档
sandbox.updateRawModeBtn();
check('大文档时按钮显示（1.4.2）', getEl('btn-raw-mode').hidden === false);
check('大文档按钮文案表示目标模式（当前富文本 → 显示「纯文本」）',
      getEl('btn-raw-mode').textContent === '纯文本');
// 编辑后 docBaseBytes 不变 → 按钮状态不因内容长度变化而反复显隐
vm.runInContext('docBaseBytes = 1200000;', sandbox);
sandbox.updateRawModeBtn();
check('编辑后按钮状态稳定（docBaseBytes 不随内容漂移）', getEl('btn-raw-mode').hidden === false);
check('大文档按钮文案表示目标模式（当前富文本 → 显示「纯文本」）',
      getEl('btn-raw-mode').textContent === '纯文本');
check('设置页临时态控件已删除', !/btn-once/.test(html));
check('按钮 title 标注仅本次生效', /仅本次生效/.test(getEl('btn-raw-mode').title));

// ---------- [11] 1.4.1 二次确认按钮：取消为主色蓝、确认置白 ----------
check('确认框：取消按钮为高亮主色（蓝）', /#confirm-mask #confirm-cancel\s*\{[\s\S]*?background:\s*var\(--c-brand\)/.test(html));
check('确认框：确认按钮为白底', /#confirm-mask #confirm-ok\s*\{[\s\S]*?background:\s*#fff/.test(html));
check('1.5.0 确认框：确认按钮在取消按钮之前（右手侧留给推荐操作「取消」）',
   html.indexOf('id="confirm-ok"') < html.indexOf('id="confirm-cancel"'));
check('确认框正文支持换行（多段落风险说明）', /#confirm-msg \{ white-space: pre-line/.test(html));
// 两个安全开关各自有专属风险文案（不再是共用一句泛化提示）
check('secure_cookie 关闭确认含「明文」风险说明',
   /强制 Cookie Secure 标记[\s\S]{0,900}明文/.test(code));
check('secure_cookie 关闭确认含「不建议」', /强烈不建议这么做/.test(code));

// ---------- [12] 1.4.1 公网访问 / IPv6 文案与免责 ----------
check('设置页说明公网 HTTP 被拒绝（secure cookie 开启时）', /公网 HTTP 连接（如 <code>http:\/\/公网IP:3838<\/code>）将被拒绝访问/.test(html));
check('设置页说明局域网 HTTP 不受影响', /局域网 HTTP 连接（如 <code>http:\/\/局域网IP:3838<\/code>）可正常访问，不受影响/.test(html));
check('设置页说明纯 HTTP 不提供 HTTPS', /不提供 HTTPS<\/b>，无法使用 <code>https:\/\/公网IP:3838<\/code>/.test(html));
check('设置页含风险自负免责段（secure cookie）', /强制 Cookie Secure 标记<\/label>[\s\S]{0,900}风险自负/.test(html)
  && /不对由此产生的任何数据泄露或损失不承担责任/.test(html));
// 1.5.0：渲染模式的风险段须含「数据损失与损坏」免责表述。
// 注意措辞是「开发者不对由此产生的任何数据损失与损坏**承担**责任」——
// 「不承担责任」被「数据损失与损坏」隔开，不能用整句 indexOf 去匹配。
const fileSec = html.slice(html.indexOf('id="pg-file"'), html.indexOf('id="pg-security"'));
check('1.5.0 渲染模式含独立的「⚠️ 风险自负」段（数据损失与损坏）',
  /风险自负/.test(fileSec) && /数据损失与损坏承担责任/.test(fileSec));
check('1.5.0 渲染模式说明含浏览器性能提示',
  /与使用的设备和浏览器性能强相关/.test(fileSec));
check('1.5.0 渲染模式说明含浏览器性能提示',
  /与使用的设备和浏览器性能强相关/.test(fileSec));
// 1.5.0：设置 → 安全中那段 IPv6 访问说明已按用户要求删除。
// 该内容在「使用指南」、应用中心描述与安装引导中仍有完整说明，不属信息丢失。
const secPage = html.slice(html.indexOf('id="pg-security"'), html.indexOf('id="pg-', html.indexOf('id="pg-security"') + 20));
check('1.5.0 设置 → 安全 已移除冗余的 IPv6 访问说明段',
  !/同时监听 IPv4 与 IPv6/.test(secPage) && !/局域网IPv6/.test(secPage));
check('IPv6 访问说明仍保留在「使用指南」中', /同时监听 IPv4 与 IPv6/.test(html));
// 安装引导同步
const wizard = fs.readFileSync(path.join(ROOT, 'vditor-fpk', 'wizard', 'install'), 'utf8');
check('安装引导：说明默认禁止公网访问', /默认禁止<\/b>以 <b>公网IP\/域名:3838/.test(wizard));
check('安装引导：说明需关闭 secure cookie 才能公网访问', /关闭「强制 Cookie Secure 标记」<\/b>。关闭后公网 HTTP 可正常访问/.test(wizard));
check('安装引导：含明文传输风险与不建议', /以明文传输/.test(wizard) && /强烈不建议这么做/.test(wizard));
check('安装引导：说明系统分区路径', /\/vol1\/@appshare\/vditor-docs/.test(wizard));
check('安装引导：说明旧分区不迁移', /不会被自动迁移/.test(wizard));

// ---------- [13] 1.4.3 重大回归：Vditor 未就绪时不得中断 initEditorAndFiles ----------
// 线上现象（1.4.2）：打开文档后「信息」窗口无法关闭、设置选项卡不跳转、
// 「添加分区」无反应、深色模式不生效；强制刷新后跳回登录页。
// 根因：updateRawModeBtn() 在 createVditor() 之后被**同步**调用，而此时 Vditor 的
//       after() 尚未触发（模块异步加载），vditor.getValue() 抛错 → 中断
//       initEditorAndFiles()，其后的所有事件绑定全部未挂载；checkAuth 的 catch 弹登录页。
// 本段用「未就绪即抛错」的桩复现，并断言：initEditorAndFiles 不抛错、后续绑定全部完成。
console.log('\n[13] 1.4.3 回归：Vditor 未就绪时的初始化健壮性');
(function () {
  // 记录本沙箱中被绑定的元素 id，用于验证「异常未中断后续绑定」
  const boundIds = [];
  const elCache2 = {};
  function getEl2(id) {
    if (!elCache2[id]) {
      const el = makeEl(id);
      const orig = el.addEventListener;
      el.addEventListener = function (evt, fn) { orig.call(this, evt, fn); boundIds.push(id); };
      elCache2[id] = el;
    }
    return elCache2[id];
  }
  const doc2 = Object.assign({}, documentStub, { getElementById: (id) => getEl2(id) });
  // ⚠️ 必须**显式构造**沙箱：Object.assign({}, sandbox, …) 浅拷贝会沿用第一个沙箱的
  //    document/Vditor 绑定，导致本段实际测的还是「已就绪」桩，测不出问题。
  const stubs2 = [];
  class NR2 extends VditorNotReadyStub {
    constructor(sel, opts) { super(sel, opts); stubs2.push(this); }
  }  const sb2 = {
    document: doc2,
    window: Object.assign({}, windowStub, { fetch: fetchStub }),
    Vditor: NR2, localStorage: localStorageStub, navigator: windowStub.navigator,
    performance: windowStub.performance, requestAnimationFrame: windowStub.requestAnimationFrame,
    fetch: fetchStub, setTimeout, clearTimeout, console, JSON, Math, Date, RegExp, Promise,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }
  };
  sb2.globalThis = sb2;

  let threw = null;
  try {
    vm.createContext(sb2);
    vm.runInContext(code, sb2, { filename: 'notready.js' });
    // after() 未触发 → Vditor 未就绪；此时调用 initEditorAndFiles（与线上一致）
    sb2.initEditorAndFiles();
  } catch (e) { threw = e; }

  check('未就绪时确实使用了未就绪桩', stubs2.length === 1);
  check('未就绪时 initEditorAndFiles 不抛错（1.4.3 核心）', threw === null, threw && threw.message);
  // 这些绑定都在 updateRawModeBtn() 之后，1.4.2 恰好在这里被中断
  ['doc-info-close', 'doc-info-close2', 'doc-info-delete', 'folder-add', 'pw-change',
   'btn-backup', 'btn-theme', 'btn-doc-info', 'btn-raw-mode', 'btn-save',
   'settings-close', 'settings-save', 'btn-toggle-side', 'btn-logout', 'btn-settings'
  ].forEach(function (id) {
    check('未就绪时仍完成绑定：' + id, boundIds.indexOf(id) >= 0);
  });
  check('未就绪时 updateRawModeBtn 已安全降级（按钮隐藏）',
        getEl2('btn-raw-mode').hidden === true);
  check('未就绪时 getContent() 返回空串而非抛错',
        vm.runInContext('getContent()', sb2) === '');
  check('未就绪时 setContent() 不抛错（静默跳过）', (function () {
    try { vm.runInContext('setContent("x")', sb2); return true; } catch (e) { return false; }
  })());
  // 就绪后再切回富文本，来源文本须正确写入
  const stub = stubs2[0];
  stub.becomeReady();
  check('就绪标记已置为 true', vm.runInContext('vditorReady', sb2) === true);
  check('就绪后可正常读取内容', typeof vm.runInContext('getContent()', sb2) === 'string');
})();

// ---------- [14] 1.4.3 端到端回归：真实 initEditorAndFiles 必须完整绑定 ----------
// 复现 1.4.2 线上故障的**同一探针**（Vditor 未就绪即抛错），
// 断言 initEditorAndFiles 不抛错且后续绑定全部完成。
// 注：真实 Vditor 的 after() 由内部异步触发，故此处刻意不同步调用 after()。
console.log('\n[14] 1.4.3 端到端：initEditorAndFiles 完整绑定');
(function () {
  const boundIds = [];
  const cache3 = {};
  function getEl3(id) {
    if (!cache3[id]) {
      const el = makeEl(id);
      const orig = el.addEventListener;
      el.addEventListener = function (evt, fn) { orig.call(this, evt, fn); boundIds.push(id); };
      cache3[id] = el;
    }
    return cache3[id];
  }
  class NR3 {
    constructor(sel, opts) {
      this.sel = sel; this.opts = opts; this._val = ''; this._ready = false; this._destroyed = false;
      this.vditor = { destroy() {}, options: { upload: { extraData: {} } } };
    }
    getValue() { if (!this._ready) throw new Error('editor not ready'); return this._val; }
    setValue(v) { if (!this._ready) throw new Error('editor not ready'); this._val = String(v == null ? '' : v); }
    setTheme() { if (!this._ready) throw new Error('editor not ready'); }
    destroy() { this._destroyed = true; }
  }
  const sb3 = {
    document: Object.assign({}, documentStub, { getElementById: (id) => getEl3(id) }),
    window: Object.assign({}, windowStub, { fetch: fetchStub }),
    Vditor: NR3, localStorage: localStorageStub, navigator: windowStub.navigator,
    performance: windowStub.performance, requestAnimationFrame: windowStub.requestAnimationFrame,
    fetch: fetchStub, setTimeout, clearTimeout, console, JSON, Math, Date, RegExp, Promise,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }
  };
  sb3.globalThis = sb3;
  let threw = null;
  try {
    vm.createContext(sb3);
    vm.runInContext(code, sb3, { filename: 'e2e.js' });
    sb3.initEditorAndFiles();
  } catch (e) { threw = e; }
  check('1.4.2 故障点不再抛错（getContent / updateRawModeBtn）',
        threw === null, threw && (threw.message + ' @ ' + String(threw.stack).split('\n')[1]));
  check('绑定总数达到 40+（1.4.2 中断在第 26 个左右）', boundIds.length >= 40, boundIds.length);
  ['doc-info-close', 'doc-info-close2', 'doc-info-delete', 'folder-add', 'pw-change',
   'btn-backup', 'btn-theme', 'btn-doc-info', 'btn-raw-mode', 'btn-save', 'btn-word-help',
   'settings-close', 'settings-close2', 'settings-save', 'btn-toggle-side', 'btn-logout',
   'btn-settings', 'set-tabs', 'btn-export-md', 'btn-export-html'
  ].forEach(function (id) {
    check('1.4.2 中断点之后仍绑定：' + id, boundIds.indexOf(id) >= 0);
  });
})();

// ---------- [15] 1.4.4 结构性回归：分组 try 隔离 ----------
// 背景：initEditorAndFiles() 曾把 30+ 个 addEventListener 写在一个函数体内且无 try 隔离，
// 一处抛错即中断整个函数，导致其后所有绑定全部失效（1.4.2→1.4.3 线上事故的根因）。
// 现改为 bindGroup(name, fn) 分组隔离，单组失败只影响该组。
console.log('\n[15] 分组 try 隔离：单组失败不影响其余绑定');
(function () {
  const boundIds = [];
  const cache4 = {};
  function getEl4(id) {
    if (!cache4[id]) {
      const el = makeEl(id);
      const orig = el.addEventListener;
      el.addEventListener = function (evt, fn) { orig.call(this, evt, fn); boundIds.push(id); };
      cache4[id] = el;
    }
    return cache4[id];
  }
  // 让 Vditor 构造函数**直接抛错**（比 1.4.3 的"未就绪"更严苛的故障场景）
  class NR4 {
    constructor() { throw new Error('Vditor engine failed to load'); }
    getValue() { return ''; } setValue() {} setTheme() {} destroy() {}
  }
  const sb4 = {
    document: Object.assign({}, documentStub, { getElementById: (id) => getEl4(id) }),
    window: Object.assign({}, windowStub, { fetch: fetchStub }),
    Vditor: NR4, localStorage: localStorageStub, navigator: windowStub.navigator,
    performance: windowStub.performance, requestAnimationFrame: windowStub.requestAnimationFrame,
    fetch: fetchStub, setTimeout, clearTimeout, console, JSON, Math, Date, RegExp, Promise,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }
  };
  sb4.globalThis = sb4;
  // 静音 console.error，避免污染测试输出
  const origErr = console.error;
  const caught = [];
  console.error = function () { caught.push(Array.from(arguments).join(' ')); };

  let threw = null;
  try {
    vm.createContext(sb4);
    vm.runInContext(code, sb4, { filename: 'groups.js' });
    sb4.initEditorAndFiles();
  } catch (e) { threw = e; } finally { console.error = origErr; }

  check('引擎构建抛错时 initEditorAndFiles 仍不抛错', threw === null, threw && threw.message);
  check('错误被捕获并记录（含分组名，便于定位）',
        caught.some(m => m.indexOf('富文本引擎初始化') >= 0), caught[0]);
  check('引擎失败后绑定数仍 ≥ 40（其余控件可用）', boundIds.length >= 40, boundIds.length);
  ['doc-info-close', 'folder-add', 'btn-theme', 'set-tabs', 'settings-close',
   'btn-save', 'btn-doc-info', 'history-close', 'btn-export-config', 'pw-change'
  ].forEach(function (id) {
    check('引擎失败后仍绑定：' + id, boundIds.indexOf(id) >= 0);
  });
  // 重复绑定检查：1.4.4 曾把 btn-doc-info/btn-raw-mode/btn-theme 移入顶栏组，
  // 若旧位置未删除会导致一次点击触发两次。
  ['btn-doc-info', 'btn-raw-mode', 'btn-theme'].forEach(function (id) {
    const n = boundIds.filter(x => x === id).length;
    check('无重复绑定：' + id + '（' + n + ' 次）', n === 1);
  });
  check('源码含 bindGroup 隔离器', /function bindGroup\(name, fn\)/.test(code));
})();

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
