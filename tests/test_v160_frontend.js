// 1.6.0 前端专项测试：顶栏长文件名自适应（②）+ 查找替换（③，后续增量追加）
// 覆盖：#topbar 禁滚动 / .fname 可收缩 / #cur-name 文本滚动 / 按钮不挤压；
//       setCurName→updateFilenameScroll→fnameTick 的 vm 真实调用（防跨作用域
//       ReferenceError 与逻辑回归），含悬停暂停/恢复、resize 重测路径。
// 依据 AGENTS.md §2：跨作用域错误只能靠 vm 真调抓住，静态正则必然误报。
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('vditor-fpk/app/index.html', 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) { console.error('FAIL: 未找到主内联脚本'); process.exit(1); }
const code = m[1];
const CSS = (html.match(/<style>([\s\S]*?)<\/style>/) || ['', ''])[1];

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS', name); }
  else { fail++; console.log('  FAIL', name, extra === undefined ? '' : JSON.stringify(extra)); }
}

// ---------- 静态断言：顶栏文件名自适应（1.6.0 需求二） ----------
console.log('== 顶栏文件名自适应（静态） ==');
check('#topbar 彻底禁止滚动（overflow:hidden，不再是 overflow-x:auto）',
  /#topbar\s*\{[^}]*overflow:\s*hidden/.test(CSS) && !/#topbar\s*\{[^}]*overflow-x:\s*auto/.test(CSS));
check('已移除 #topbar::-webkit-scrollbar 死规则', !/#topbar::-webkit-scrollbar/.test(CSS));
check('#topbar .fname 允许收缩（flex:1 1 auto）并裁剪（overflow:hidden）',
  /#topbar\s+\.fname\s*\{[^}]*flex:\s*1 1 auto[^}]*overflow:\s*hidden/.test(CSS));
check('#cur-name 为 inline-block 且 max-width:100%（仅文件名自身滚动）',
  /#cur-name\s*\{[^}]*display:\s*inline-block[^}]*max-width:\s*100%[^}]*white-space:\s*nowrap/.test(CSS));
check('按钮组不参与收缩（#topbar .top-actions > * flex:0 0 auto）',
  /#topbar\s+\.top-actions\s*>\s*\*\s*\{\s*flex:\s*0 0 auto/.test(CSS));
check('字数统计仍不收缩（flex:0 0 auto 保留）',
  /#topbar\s+\.word-counter\s*\{[^}]*flex:\s*0 0 auto/.test(CSS));
check('setCurName 处调用 updateFilenameScroll',
  /function setCurName\(name\)\s*\{\s*document\.getElementById\('cur-name'\)\.textContent = name \|\| '未选择';\s*updateFilenameScroll\(\);/.test(code));
check('updateFilenameScroll 用 rAF 延迟一帧测量（避免拿到旧 scrollWidth）',
  /function updateFilenameScroll\(\)[\s\S]{0,400}requestAnimationFrame/.test(code));
check('fnameTick 用 transform:translateX 往返滚动（不碰布局）',
  /function fnameTick\(\)[\s\S]{0,600}translateX/.test(code));
check('悬停暂停 / 移开恢复已绑定（mouseenter/mouseleave）',
  /addEventListener\('mouseenter'[\s\S]{0,200}addEventListener\('mouseleave'/.test(code));
check('容器宽度变化经 ResizeObserver 重测（含 typeof 守卫）',
  /typeof ResizeObserver === 'undefined'/.test(code) && /new ResizeObserver/.test(code));

// ---------- 运行时：vm 真调（防跨作用域 ReferenceError） ----------
console.log('== 顶栏文件名自适应（vm 运行时） ==');
const ids = {};
function mk(id) {
  const cls = new Set();
  return {
    _id: id, id: '', textContent: '', title: '', value: '', innerHTML: '', disabled: false,
    style: {}, dataset: {}, children: [], hidden: false,
    classList: { add(c) { cls.add(c); }, remove(c) { cls.delete(c); },
                 toggle(c, f) { f ? cls.add(c) : cls.delete(c); }, contains(c) { return cls.has(c); } },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {}, remove() {}, contains() { return false; },
    getAttribute() { return null; }, setAttribute() {},
    querySelector() { return mk('q'); }, querySelectorAll() { return []; },
    focus() {}, click() {}, closest() { return null; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
  };
}
// 富桩：cur-name 可配置 scrollWidth/clientWidth 并记录事件监听
function mkName() {
  const listeners = {};
  const el = mk('cur-name');
  el.scrollWidth = 500; el.clientWidth = 300;   // 默认溢出 200px
  el.addEventListener = (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); };
  el._fire = (t) => { (listeners[t] || []).forEach(fn => fn()); };
  return el;
}
function getEl(id) { return ids[id] || (ids[id] = mk(id)); }
const store = {};
const rafQueue = [];
const roInstances = [];
const ctx = {
  console, document: {
    getElementById: getEl, createElement: () => mk('created'),
    querySelector: () => mk('qs'), querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
    body: mk('body'), documentElement: mk('html'), cookie: ''
  },
  navigator: { userAgent: 'node', platform: 'Win32' },
  location: { href: 'http://x/', search: '', hash: '', protocol: 'http:' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  setTimeout() {}, clearTimeout() {}, setInterval() {}, clearInterval() {},
  fetch() { return Promise.reject(new Error('no-net')); },
  TextEncoder, TextDecoder, alert() {}, confirm() { return true; }, prompt() { return null; },
  btoa: s => Buffer.from(s).toString('base64'), atob: s => Buffer.from(s, 'base64').toString(),
  addEventListener() {}, removeEventListener() {}, history: {},
  performance: { now: () => Date.now() },
  requestAnimationFrame: (fn) => { rafQueue.push(fn); return rafQueue.length; },
  cancelAnimationFrame: () => {},
  ResizeObserver: function (cb) { this.cb = cb; this.observe = function () { roInstances.push(this); }; },
  Vditor: function () { throw new Error('no editor'); },
  JSON, Math, Date, RegExp, Promise, console,
  Uint8Array, ArrayBuffer, String, Number, Object, Array, Boolean, Map, Set,
  encodeURIComponent, decodeURIComponent, isNaN, parseInt, parseFloat
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx; ctx.top = ctx;
vm.createContext(ctx);
ids['cur-name'] = mkName();
let boot = null;
try { vm.runInContext(code, ctx, { filename: 'inline.js' }); } catch (e) { boot = e; }
check('脚本可加载（无跨作用域 ReferenceError）', boot === null, boot && boot.message);

check('updateFilenameScroll / fnameTick / fnameOverflow 已定义',
  typeof ctx.updateFilenameScroll === 'function'
  && typeof ctx.fnameTick === 'function'
  && typeof ctx.fnameOverflow === 'function');

const nameEl = ids['cur-name'];
// 有界步帧：tick 会自排队，禁止无界排空（会死循环）
function step(n) { for (let i = 0; i < n && rafQueue.length; i++) rafQueue.shift()(); }

// --- 场景 1：不溢出 → 不动画、transform 复位 ---
nameEl.scrollWidth = 100; nameEl.clientWidth = 300;
let err = null;
try { ctx.setCurName('短名.md'); } catch (e) { err = e; }
check('setCurName 短名不抛错', err === null, err && err.message);
check('setCurName 写入 textContent', nameEl.textContent === '短名.md', nameEl.textContent);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(3);
check('不溢出时无滚动动画（transform 为空）', nameEl.style.transform === '', nameEl.style.transform);

// --- 场景 2：溢出 → rAF 驱动 transform 递增（文本左移露出右侧） ---
nameEl.scrollWidth = 500; nameEl.clientWidth = 300;   // overflow = 200
err = null;
try { ctx.setCurName('一个非常长的文件名字段用来测试横向滚动行为.md'); } catch (e) { err = e; }
check('setCurName 长名不抛错', err === null, err && err.message);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(1);                                            // 测量帧：overflow=200 → 启动 tick
const transforms = [];
for (let i = 0; i < 5; i++) { step(1); transforms.push(nameEl.style.transform); }
check('溢出时启动滚动（transform 非空）', transforms[0] !== '', transforms[0]);
check('transform 逐步左移（translateX 负值递增）',
  /translateX\(-(\d+)px\)/.test(transforms[4])
  && parseInt(RegExp.$1, 10) > parseInt((/-(\d+)px\)/.exec(transforms[0]) || [0, 0])[1], 10),
  transforms);

// --- 场景 3：悬停暂停 / 移开恢复 ---
nameEl._fire('mouseenter');
step(3);
const before = nameEl.style.transform;
step(3);
check('悬停后滚动暂停（transform 不再变化）', nameEl.style.transform === before,
  { before, after: nameEl.style.transform });
nameEl._fire('mouseleave');
step(1);
check('移开恢复后 transform 继续变化', nameEl.style.transform !== before,
  { before, after: nameEl.style.transform });

// --- 场景 4：ResizeObserver 宽度变化重测不抛错 ---
err = null;
try {
  check('ResizeObserver 已实例化并观察 .fname', roInstances.length >= 1, roInstances.length);
  if (roInstances.length) roInstances[0].cb();
  step(3);
} catch (e) { err = e; }
check('ResizeObserver 回调重测不抛错', err === null, err && err.message);

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
