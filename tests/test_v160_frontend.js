// 1.6.0 前端专项测试：顶栏长文件名自适应（②）+ 查找与替换（③）
// 覆盖：#topbar 禁滚动 / .fname 可收缩 / #cur-name 文本滚动 / 按钮不挤压；
//       查找栏 DOM 与按钮变体类、Ctrl+F/Ctrl+H/Esc 集成、保存前清除高亮；
//       setCurName→updateFilenameScroll→fnameTick、find* 全链路（输入防抖、
//       上/下一处、单/全替换、正则 $1、大小写/整词、非法正则、关闭清理）
//       的 vm 真实调用（防跨作用域 ReferenceError 与逻辑回归）。
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

// ================= 静态断言：顶栏文件名自适应（1.6.0 需求二） =================
console.log('== 顶栏文件名自适应（静态） ==');
check('#topbar 彻底禁止滚动（overflow:hidden，不再是 overflow-x:auto）',
  /#topbar\s*\{[^}]*overflow:\s*hidden/.test(CSS) && !/#topbar\s*\{[^}]*overflow-x:\s*auto/.test(CSS));
check('已移除 #topbar::-webkit-scrollbar 死规则', !/#topbar::-webkit-scrollbar/.test(CSS));
check('#topbar .fname 允许收缩（flex:1 1 auto）并裁剪（overflow:hidden）',
  /#topbar\s+\.fname\s*\{[^}]*flex:\s*1 1 auto[^}]*overflow:\s*hidden/.test(CSS));
check('#cur-name 用 flex:1 1 auto + min-width:0 + overflow:hidden（结构性防压盖前缀，1.6.0.2 重构）',
  /#cur-name\s*\{[^}]*flex:\s*1 1 auto[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*white-space:\s*nowrap/.test(CSS));
check('#cur-name 不再使用 max-width:100%（1.6.0.1「滚动压盖前缀」根因，已弃用）',
  !/#cur-name\s*\{[^}]*max-width/.test(CSS));
check('「当前文件：」前缀为独立 flex 子项（flex:0 0 auto 静止）',
  /#topbar\s+\.fname-prefix\s*\{[^}]*flex:\s*0 0 auto/.test(CSS));
check('按钮组不参与收缩（#topbar .top-actions > * flex:0 0 auto）',
  /#topbar\s+\.top-actions\s*>\s*\*\s*\{\s*flex:\s*0 0 auto/.test(CSS));
check('字数统计仍不收缩（flex:0 0 auto 保留）',
  /#topbar\s+\.word-counter\s*\{[^}]*flex:\s*0 0 auto/.test(CSS));
check('setCurName 处调用 updateFilenameScroll',
  /function setCurName\(name\)\s*\{\s*document\.getElementById\('cur-name'\)\.textContent = name \|\| '未选择';\s*updateFilenameScroll\(\);/.test(code));
check('updateFilenameScroll 用 rAF 延迟一帧测量（避免拿到旧 scrollWidth）',
  /function updateFilenameScroll\(\)[\s\S]{0,600}requestAnimationFrame/.test(code));
check('fnameTick(now) 用 scrollLeft 往返滚动（窗口固定、内容在窗内滚，时间戳归一化）',
  /function fnameTick\(now\)[\s\S]{0,1200}scrollLeft/.test(code));
check('fnameTick 不再用 transform 平移窗口本身（1.6.0.2 压盖前缀总根因，已弃用）',
  !/el\.style\.transform\s*=\s*'translateX/.test(code));
check('fnameTick 对缺省时间戳有防御（typeof now!==\'number\' 退化 performance.now）',
  /typeof now !== 'number'/.test(code));
check('fnameTick 速度/停顿为时间基常量（FNAME_SPEED/FNAME_PAUSE，非每帧 1px）',
  /FNAME_SPEED\s*=\s*\d+/.test(code) && /FNAME_PAUSE\s*=\s*\d+/.test(code));
check('悬停暂停 / 移开恢复已绑定（mouseenter/mouseleave）',
  /addEventListener\('mouseenter'[\s\S]{0,200}addEventListener\('mouseleave'/.test(code));
check('容器宽度变化经 ResizeObserver 重测（含 typeof 守卫）',
  /typeof ResizeObserver === 'undefined'/.test(code) && /new ResizeObserver/.test(code));

// ================= 静态断言：查找与替换（1.6.0 需求三） =================
console.log('== 查找与替换（静态） ==');
// 精确切取 find-bar 整块（从开标签到 <div id="vditor"> 之前）——
// 旧的「三个连续 </div>」正则会在 1.6.0.2 结构下越界捕获到登录/菜单按钮。
const fbStart = html.indexOf('<div id="find-bar"');
const fbEnd = html.indexOf('<div id="vditor">');
const findBar = (fbStart >= 0 && fbEnd > fbStart) ? html.slice(fbStart, fbEnd) : '';
check('查找栏 DOM 存在且默认隐藏（hidden 属性）', /<div id="find-bar" hidden>/.test(html));
check('查找栏 [hidden] 时强制 display:none（压过 display:flex）',
  /#find-bar\[hidden\]\s*\{\s*display:\s*none/.test(CSS));
check('查找/替换输入框复用 .set-input（无行内 width hack）',
  /id="find-input"[^>]*class="set-input"/.test(html)
  && /id="replace-input"[^>]*class="set-input"/.test(html)
  && !/id="find-input"[^>]*style=/.test(html) && !/id="replace-input"[^>]*style=/.test(html));
check('查找栏按钮全部挂 btn + btn--ghost 变体类',
  (findBar.match(/class="btn btn--ghost/g) || []).length >= 8
  && !/<button(?![^>]*class="btn )/.test(findBar));
check('选项开关有 aria-pressed 态与视觉样式',
  /aria-pressed="false"/.test(findBar) && /#find-bar\s+\.fb-opt\[aria-pressed="true"\]/.test(CSS));
check('Ctrl/Cmd+F 捕获阶段拦截并 preventDefault（优先于 Vditor 与原生查找）',
  /e\.key === 'f' \|\| e\.key === 'F'\)\)\s*\{\s*e\.preventDefault\(\);/.test(code));
check('Ctrl/Cmd+H 展开替换区', /e\.key === 'h' \|\| e\.key === 'H'\)\)\s*\{\s*e\.preventDefault\(\);/.test(code));
check('Esc 优先关闭下拉菜单（closeTransientMenus，比查找栏更 transient）',
  /if \(e\.key === 'Escape'\)\s*\{\s*\/\/ 1\.6\.0\.2：下拉菜单比查找栏更 transient[\s\S]{0,260}if \(closeTransientMenus\(\)\) return;/.test(code));
check('Esc 其次关闭查找栏（仍先于弹窗栈）',
  /if \(closeTransientMenus\(\)\) return;\s*\/\/ 1\.6\.0：查找栏是最 transient 的 UI，Esc 优先关它，再走弹窗栈\s*if \(findState\.open\)\s*\{\s*findClose\(\);/.test(code));
check('面板内 Enter/F3 跳转、Shift 反向',
  /if \(e\.key === 'Enter'\)\s*\{\s*e\.preventDefault\(\);\s*if \(e\.shiftKey\) findPrev\(\); else findNext\(\);/.test(code));
check('保存前强制清除高亮（doSave → findClearMarks，防 <mark> 混进正文）',
  /function doSave\(silent\)\s*\{\s*\/\/ 1\.6\.0：保存前强制清除查找高亮[\s\S]{0,120}findClearMarks\(\);/.test(code));
check('切文件 / 切渲染模式时关闭查找栏（防陈旧命中）',
  /if \(findState\.open\) findClose\(\);/.test(code)
  && (code.match(/if \(findState\.open\) findClose\(\);/g) || []).length >= 3);
check('清除高亮走「展开子节点 + removeChild + normalize」精确还原',
  /while \(mk\.firstChild\) parent\.insertBefore\(mk\.firstChild, mk\);[\s\S]{0,80}parent\.removeChild\(mk\);[\s\S]{0,60}parent\.normalize\(\)/.test(code));
check('高亮 <mark> 限定 .vditor-ir 渲染区（1.6.0.2：4 个 .vditor-reset 中唯 ir 可编辑）',
  /\.vditor-ir \.vditor-reset mark\.vd-find\s*\{/.test(CSS)
  && /\.vditor-ir \.vditor-reset mark\.vd-find-current\s*\{/.test(CSS)
  && /html\[data-theme="dark"\] \.vditor-ir \.vditor-reset mark\.vd-find\s*\{/.test(CSS));
check('findHighlightRoot 模式感知（1.6.0.5）：sv→null / wysiwyg→.vditor-wysiwyg / ir→限定 .vditor-ir 且要求可见',
  /function findHighlightRoot\(\)\s*\{\s*if \(rawMode\) return null;[\s\S]{0,900}mode === 'sv'\) return null;/.test(code)
  && /mode === 'wysiwyg'\)\s*\{[\s\S]{0,200}\.vditor-wysiwyg/.test(code)
  && /\.vditor-ir > \.vditor-reset'\)/.test(code)
  && /ir\.offsetParent === null\) return null;/.test(code));
check('正则非法有 try/catch 兜底（不抛错）',
  /try \{ return new RegExp\(src, flags\); \} catch \(e\) \{ return \{ error: e \}; \}/.test(code));
check('替换全部：正则走原生 replace（支持 $1），非正则从尾向前',
  /out = text\.replace\(re, repl\);/.test(code)
  && /for \(let i = findState\.matches\.length - 1; i >= 0; i--\)/.test(code));
check('编辑区 input 时清除高亮并重算（防 <mark> 残留进编辑器模型）',
  /vd\.addEventListener\('input'[\s\S]{0,200}findClearMarks\(\);/.test(code));

// ================= 运行时：vm 真调（防跨作用域 ReferenceError） =================
console.log('== vm 运行时 ==');
const ids = {};
const timers = [];
const rafQueue = [];
const roInstances = [];
const docLs = {};                       // document 级监听登记（供菜单测试派发click）
function mk(id) {
  const cls = new Set();
  const attrs = {};
  const el = {
    // id 必须回填真实值：closeTransientMenus 走 tbMenuClose(menus[i].id)，
    // 旧桩 id:'' 会让 getElementById('') 落到幻影元素上，真菜单永远关不掉
    _id: id, id: id, textContent: '', title: '', value: '', innerHTML: '', disabled: false,
    style: {}, dataset: {}, children: [], hidden: false, className: '',
    offsetWidth: 100, offsetHeight: 100, scrollWidth: 0, clientWidth: 0,
    get offsetTop() { return stubOffsetTop; },
    classList: { add(c) { cls.add(c); }, remove(c) { cls.delete(c); },
                 toggle(c, f) { f ? cls.add(c) : cls.delete(c); }, contains(c) { return cls.has(c); } },
    appendChild(c) { this.children.push(c); if (c && typeof c === 'object') c.parentNode = this; return c; },
    insertBefore(c, ref) {
      // 真实 DOM 语义：插入即「移动」——先从旧父级摘除，避免 clearMarks 的
      // while (firstChild) insertBefore(...) 在桩里退化成无限 push
      if (c && c.parentNode && c.parentNode !== this && c.parentNode.removeChild) {
        c.parentNode.removeChild(c);
      }
      const i = ref ? this.children.indexOf(ref) : -1;
      if (i >= 0) this.children.splice(i, 0, c); else this.children.push(c);
      if (c && typeof c === 'object') c.parentNode = this;
      return c;
    },
    replaceChild(nu, old) {
      const i = this.children.indexOf(old);
      if (i >= 0) this.children[i] = nu;
      if (nu && typeof nu === 'object') {
        nu.parentNode = this;
        (nu.children || []).forEach(c => { c.parentNode = this; });
      }
      return old;
    },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    normalize() {},
    addEventListener(t, fn) { (this._ls = this._ls || {})[t] = fn; },
    removeEventListener() {}, remove() {}, contains() { return false; },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = String(v); },
    querySelector() { return mk('q'); }, querySelectorAll() { return []; },
    focus() {}, select() {}, click() { if (this._ls && this._ls.click) this._ls.click(); },
    _fire(t, ev) { if (this._ls && this._ls[t]) this._ls[t](ev || { stopPropagation() {}, preventDefault() {} }); },
    // 简化 closest：类名命中即返回自身（覆盖 .tb-menu / .mi / .tb-trigger 判定）
    closest(sel) {
      const last = sel.split(' ').pop();
      if (last && last.charAt(0) === '.' && this.className &&
          this.className.split(/\s+/).indexOf(last.slice(1)) >= 0) return this;
      return null;
    },
    // 1.6.0.4：元素级 querySelector 也认 data-wc（refreshWcMenuItem 走
    // menu.querySelector('.mi[data-wc]')，不是 document 级）
    querySelector(sel) {
      if (typeof sel === 'string' && sel.indexOf('data-wc') >= 0) return qsWcItem;
      return mk('q');
    },
    getBoundingClientRect() { return { top: 0, left: 0, right: 100, bottom: 30, width: 100, height: 30 }; }
  };
  Object.defineProperty(el, 'firstChild', { get() { return this.children[0] || null; } });
  return el;
}
// 富桩：cur-name 可配置 scrollWidth/clientWidth
function mkName() {
  const el = mk('cur-name');
  el.scrollWidth = 500; el.clientWidth = 300;
  return el;
}
// 1.6.0.4：镜像量测桩——marker 的 offsetTop 可配置（scrollTaToIndex 读它）
let stubOffsetTop = 4242;
function getEl(id) { return ids[id] || (ids[id] = mk(id)); }
const store = {};
const ssStore = {};                     // 1.6.0.3：sessionStorage 存储（per-tab token）
const fetchCalls = [];                  // 1.6.0.3：fetch 记录器（验证 X-Vditor-Token 头注入）
// 可配置的 query 结果（供 findHighlightRoot 测试注入假渲染区）
let qsHost = null;
// 1.6.0.3：Vditor sv 源码模式的 textarea 桩（class="vditor-sv vditor-reset"）
let qsSv = null;
// 1.6.0.4：refreshWcMenuItem 走 menu.querySelector('.mi[data-wc]')，
// 桩需能返回真实信息项（否则摸到幻影元素，测了个寂寞）
let qsWcItem = null;
// 1.6.0.5：findClearMarks 清「所有高亮宿主」（ir + wysiwyg），
// 桩的 querySelectorAll 需能返回这些宿主
let qsHostList = [];
// 1.6.0.5：findMarkCurrent 的 marks 查询结果（含 mark 的选择器单独配置）
let qsMarksList = [];
// 1.6.0.5：wysiwyg 编辑区宿主桩
let qsWy = null;
const walkerNodes = [];
const ctx = {
  console, document: {
    getElementById: getEl, createElement: () => mk('created'),
    createTextNode: (t) => ({ nodeType: 3, nodeValue: t }),
    createDocumentFragment: () => mk('fragment'),
    createTreeWalker: () => {
      let cur = null;
      return {
        get currentNode() { return cur; },
        nextNode() { cur = walkerNodes.shift() || null; return cur; }
      };
    },
    querySelector: (sel) => {
      // ir 与 sv 互斥（真实 DOM 亦如此）：sv 模式激活时 .vditor-ir 不存在
      if (sel === '#vditor .vditor-ir > .vditor-reset') return qsSv ? null : (qsHost || mk('qs'));
      if (sel === '#vditor .vditor-sv') return qsSv;      // 1.6.0.3：sv textarea（null=不在 sv 模式）
      if (sel === '#vditor .vditor-wysiwyg') return qsWy; // 1.6.0.5：wysiwyg 编辑区
      if (sel.indexOf('data-wc') >= 0) return qsWcItem;  // 1.6.0.4：字数信息项
      return mk('qs');
    },
    querySelectorAll: (sel) => {
      if (sel === '.tb-menu') return [getEl('export-menu'), getEl('more-menu')];
      // 1.6.0.5：含 mark 的选择器 → 返回配置的 marks；否则返回高亮宿主
      if (sel.indexOf('mark.vd-find') >= 0) return qsMarksList;
      if (sel.indexOf('.vditor-ir') >= 0 || sel.indexOf('.vditor-wysiwyg') >= 0) return qsHostList;
      return [];
    },
    addEventListener(t, fn) { (docLs[t] = docLs[t] || []).push(fn); },
    removeEventListener() {},
    body: mk('body'), documentElement: mk('html'), cookie: ''
  },
  navigator: { userAgent: 'node', platform: 'Win32' },
  location: { href: 'http://x/', search: '', hash: '', protocol: 'http:' },
  innerWidth: 1024, innerHeight: 768,
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  sessionStorage: { getItem: k => (k in ssStore ? ssStore[k] : null), setItem: (k, v) => { ssStore[k] = String(v); }, removeItem: k => { delete ssStore[k]; } },
  setTimeout: (fn) => { timers.push(fn); return timers.length; },
  clearTimeout: () => {},
  setInterval() {}, clearInterval() {},
  fetch(input, init) { fetchCalls.push({ url: input, init: init }); return Promise.reject(new Error('no-net')); },
  TextEncoder, TextDecoder, alert() {}, confirm() { return true; }, prompt() { return null; },
  btoa: s => Buffer.from(s).toString('base64'), atob: s => Buffer.from(s, 'base64').toString(),
  addEventListener() {}, removeEventListener() {}, history: {},
  performance: { now: () => Date.now() },
  // 1.6.0.4：镜像量测需要 getComputedStyle（桩返回空属性集，
  // taMirrorOffsetTop 对 undefined 属性赋值不抛错）
  getComputedStyle: () => ({}),
  requestAnimationFrame: (fn) => { rafQueue.push(fn); return rafQueue.length; },
  cancelAnimationFrame: () => {},
  ResizeObserver: function (cb) { this.cb = cb; this.observe = function () { roInstances.push(this); }; },
  NodeFilter: { SHOW_TEXT: 4, SHOW_ELEMENT: 1 },
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

check('② updateFilenameScroll / fnameTick / fnameOverflow 已定义',
  typeof ctx.updateFilenameScroll === 'function'
  && typeof ctx.fnameTick === 'function'
  && typeof ctx.fnameOverflow === 'function');
check('③ findOpen / findClose / findCompute / findNext / findPrev / findReplaceOne / findReplaceAll / findClearMarks 已定义',
  ['findOpen', 'findClose', 'findCompute', 'findNext', 'findPrev',
   'findReplaceOne', 'findReplaceAll', 'findClearMarks'].every(f => typeof ctx[f] === 'function'));

// ---- ② 场景（有界步帧：tick 自排队，禁止无界排空） ----
const nameEl = ids['cur-name'];
// 1.6.0.2：fnameTick(now) 依赖 rAF 时间戳做时间归一化（dt = (now-last)/1000），
// 旧桩不传时间戳 → now 退化为 performance.now()（Date.now()），
// 同一毫秒内多帧 dt=0 → pos 恒 0 →「滚动不动」假象。故步帧必须传递增假时间。
let fakeNow = 0;
function step(n) { for (let i = 0; i < n && rafQueue.length; i++) { fakeNow += 16; rafQueue.shift()(fakeNow); } }
function flushTimers() { const t = timers.slice(); timers.length = 0; t.forEach(fn => fn()); }

nameEl.scrollWidth = 100; nameEl.clientWidth = 300;
nameEl.scrollLeft = 0;
let err = null;
try { ctx.setCurName('短名.md'); } catch (e) { err = e; }
check('setCurName 短名不抛错', err === null, err && err.message);
check('setCurName 写入 textContent', nameEl.textContent === '短名.md', nameEl.textContent);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(3);
check('不溢出时无滚动动画（scrollLeft 保持 0）', nameEl.scrollLeft === 0, nameEl.scrollLeft);

nameEl.scrollWidth = 500; nameEl.clientWidth = 300;
err = null;
try { ctx.setCurName('一个非常长的文件名字段用来测试横向滚动行为.md'); } catch (e) { err = e; }
check('setCurName 长名不抛错', err === null, err && err.message);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(1);                       // 测量帧：读 overflow 并挂 tick
step(1);                       // 首帧：初始化 last（dt=0），pos=0 触发左端 900ms 到端停顿
// 1.6.0.2 设计：起滚与到端均有 FNAME_PAUSE(900ms) 停顿（给用户读完开头的时间），
// 故必须跨过初始停顿后再采样，否则采到的全是停顿帧（scrollLeft 恒 0）。
for (let i = 0; i < 70; i++) step(1);
const t1 = nameEl.scrollLeft;
for (let i = 0; i < 20; i++) step(1);
const t2 = nameEl.scrollLeft;
check('溢出时启动滚动（scrollLeft > 0）', t1 > 0, t1);
check('scrollLeft 逐步增大（内容向窗内滚动，窗口本身不动）', t2 > t1, { t1: t1, t2: t2 });
nameEl._fire('mouseenter');
step(3);
const beforePause = nameEl.scrollLeft;
step(3);
check('悬停后滚动暂停（scrollLeft 不再变化）', nameEl.scrollLeft === beforePause,
  { before: beforePause, after: nameEl.scrollLeft });
nameEl._fire('mouseleave');
step(1);
check('移开恢复后 scrollLeft 继续变化', nameEl.scrollLeft !== beforePause);
err = null;
try {
  check('ResizeObserver 已实例化并观察 .fname', roInstances.length >= 1, roInstances.length);
  if (roInstances.length) roInstances[0].cb();
  step(3);
} catch (e) { err = e; }
check('ResizeObserver 回调重测不抛错', err === null, err && err.message);

// ---- ③ 场景：查找替换全链路 ----
console.log('== 查找替换（vm 运行时） ==');
let findContent = 'abc abc';                 // getContent 桩数据
const setContentCalls = [];
ctx.getContent = () => findContent;
ctx.setContent = (t) => { setContentCalls.push(t); };

const findInput = getEl('find-input');
const replaceInput = getEl('replace-input');
const countEl = getEl('find-count');
const barEl = getEl('find-bar');   // getEl 与脚本的 getElementById 同一 id 映射，先建先用

// 1) 打开 + 预填 + 计数
err = null;
try { ctx.findOpen('abc', false); } catch (e) { err = e; }
check('findOpen 不抛错', err === null, err && err.message);
check('findOpen 显示面板并写入输入框', barEl.hidden === false && findInput.value === 'abc',
  { hidden: barEl.hidden, value: findInput.value });
check('计数为 1/2（源串基准）', countEl.textContent === '1/2', countEl.textContent);

// 2) 上/下一处循环
ctx.findNext();
check('下一处 → 2/2', countEl.textContent === '2/2', countEl.textContent);
ctx.findNext();
check('循环回 1/2', countEl.textContent === '1/2', countEl.textContent);
ctx.findPrev();
check('上一处 → 2/2', countEl.textContent === '2/2', countEl.textContent);

// 3) 单处替换（index=1，第二处 abc → X）
replaceInput.value = 'X';
ctx.findReplaceOne();
check('单处替换调 setContent 且结果正确', setContentCalls[setContentCalls.length - 1] === 'abc X',
  setContentCalls[setContentCalls.length - 1]);
check('替换后脏标记生效路径存在（dirty 赋值）', /dirty = true;/.test(code));

// 4) 全部替换
findContent = 'abc abc';
ctx.findReplaceAll();
check('全部替换结果正确', setContentCalls[setContentCalls.length - 1] === 'X X',
  setContentCalls[setContentCalls.length - 1]);

// 5) 选项开关：整词 + 大小写（经按钮 click 处理器真实驱动）
findContent = 'abc abcx ABC';
findInput.value = 'abc';
findInput._fire('input'); flushTimers();
check('默认大小写不敏感：3 处命中', countEl.textContent === '1/3', countEl.textContent);
ids['find-opt-word']._fire('click');
check('整词开启后 aria-pressed=true 且只剩 2 处（abcx 被排除）',
  getEl('find-opt-word').getAttribute('aria-pressed') === 'true'
  && countEl.textContent === '1/2', countEl.textContent);
ids['find-opt-case']._fire('click');
check('再开大小写敏感后仅 1 处（ABC 被排除）', countEl.textContent === '1/1', countEl.textContent);

// 6) 正则 + $1 反向引用（全部替换）
findContent = 'xx123yy456';
ids['find-opt-case']._fire('click');           // 还原大小写不敏感
ids['find-opt-word']._fire('click');           // 还原整词关
ids['find-opt-regex']._fire('click');          // 正则开
findInput.value = '(\\d+)';
findInput._fire('input'); flushTimers();
check('正则模式命中 2 处', countEl.textContent === '1/2', countEl.textContent);
replaceInput.value = '[$1]';
ctx.findReplaceAll();
check('正则全部替换支持 $1', setContentCalls[setContentCalls.length - 1] === 'xx[123]yy[456]',
  setContentCalls[setContentCalls.length - 1]);

// 7) 非法正则不抛错、计数显示无效
findInput.value = '[';
findInput._fire('input'); flushTimers();
check('非法正则计数显示「无效」', countEl.textContent === '无效', countEl.textContent);
err = null;
try { ctx.findReplaceAll(); ctx.findNext(); ctx.findPrev(); } catch (e) { err = e; }
check('无效正则下替换/跳转不抛错', err === null, err && err.message);

// 8) 空词：0/0
ids['find-opt-regex']._fire('click');          // 正则关
findInput.value = '';
findInput._fire('input'); flushTimers();
check('空词计数 0/0', countEl.textContent === '0/0', countEl.textContent);

// 9) 关闭：面板隐藏 + 状态清空
ctx.findOpen('abc', false);
ctx.findClose();
check('findClose 后面板隐藏', barEl.hidden === true, barEl.hidden);
check('findClose 后输入框清空', findInput.value === '', findInput.value);

// 10) 渲染区高亮：TreeWalker 真调 + <mark> 包裹
console.log('== 查找替换：渲染区高亮 ==');
const host = mk('reset-host');
const para = mk('p');
const textNode = { nodeType: 3, nodeValue: 'abc abc', parentNode: para };
para.children = [textNode];                    // 真实结构：para > text
walkerNodes.push(textNode);
qsHost = host;
err = null;
try {
  findContent = 'abc abc';
  ctx.findOpen('abc', false);
  flushTimers();
} catch (e) { err = e; }
check('findOpen（含高亮）不抛错', err === null, err && err.message);
check('文本节点被 Fragment 替换（replaceChild 生效）', para.children.length === 1, para.children.length);
const frag = para.children[0];
check('Fragment 子节点 = mark/text/mark 三个', frag && frag.children.length === 3, frag && frag.children.length);
check('mark 类名为 vd-find 且文本正确',
  frag && frag.children[0].className === 'vd-find'
  && frag.children[0].children[0].nodeValue === 'abc'
  && frag.children[2].className === 'vd-find'
  && frag.children[2].children[0].nodeValue === 'abc',
  frag && [frag.children[0].className, frag.children[2].className]);

// 11) 清除高亮：模拟 replaceChild 后的真实挂载状态，验证精确展开还原
const markA = frag.children[0], spaceText = frag.children[1], markB = frag.children[2];
markA.parentNode = para; spaceText.parentNode = para; markB.parentNode = para;
para.children = [markA, spaceText, markB];
const marks = [markA, markB];
host.querySelectorAll = () => marks;
qsHostList = [host];                        // 1.6.0.5：findClearMarks 走 document.querySelectorAll 取宿主
err = null;
try { ctx.findClearMarks(); } catch (e) { err = e; }
check('findClearMarks 不抛错', err === null, err && err.message);
check('清除后还原为纯文本节点（无 mark 残留）',
  !para.children.some(c => c.className === 'vd-find')
  && para.children.filter(c => c.nodeType === 3).map(c => c.nodeValue).join('') === 'abc abc',
  para.children.map(c => c.nodeType === 3 ? '#' + c.nodeValue : (c.className || c._id)));

// ================= 1.6.0.2：顶栏下拉菜单（1.6.0.3：纯文字按钮 + 两档响应式） =================
console.log('== 顶栏下拉菜单（静态） ==');
check('导出按钮已合并（btn-export-md / btn-export-html 均已移除）',
  !/id="btn-export-md"/.test(html) && !/id="btn-export-html"/.test(html));
check('「导出」按钮为纯文字（1.6.0.3 去掉 ▾ 指示符）且挂 tb-trigger 契约类',
  /<button id="btn-export" class="btn btn--ghost tb-trigger"[^>]*>导出<\/button>/.test(html));
check('「查找」按钮为纯文字（1.6.0.3 去掉 🔍 图标）',
  /<button id="btn-find" class="btn btn--ghost"[^>]*>查找<\/button>/.test(html));
check('「⋯ 更多」按钮存在（默认隐藏纯 CSS 控制，不用 hidden 属性）',
  /<button id="btn-more" class="btn btn--ghost tb-trigger"/.test(html)
  && !/<button id="btn-more"[^>]*hidden/.test(html));
check('「⋯ 更多」置于保存左侧（保存恒为最右主操作）',
  html.indexOf('id="btn-more"') < html.indexOf('id="btn-save"'));
check('#export-menu 静态两项 + #more-menu 动态容器均存在',
  /<div id="export-menu" class="tb-menu" role="menu" hidden>/.test(html)
  && /<div id="more-menu" class="tb-menu" role="menu" hidden><\/div>/.test(html));
check('.tb-menu[hidden] 显式 display:none（防 flex 覆盖 hidden 属性，同 find-bar 教训）',
  /\.tb-menu\[hidden\]\s*\{\s*display:\s*none/.test(CSS));
check('.tb-menu z-index 显式声明 10015（10010 基础框与 10020 确认类之间，逐个显式）',
  /\.tb-menu\s*\{[^}]*z-index:\s*10015/.test(CSS));
check('菜单项四态齐全（hover 浅底 / focus-visible 品牌环 / active 下压 / disabled）',
  /\.tb-menu \.mi:hover:not\(:disabled\)/.test(CSS)
  && /\.tb-menu \.mi:focus-visible/.test(CSS)
  && /\.tb-menu \.mi:active:not\(:disabled\)/.test(CSS)
  && /\.tb-menu \.mi:disabled/.test(CSS));
check('#btn-more 默认 display:none（>=860px 不出现）',
  /#topbar #btn-more\s*\{\s*display:\s*none/.test(CSS));
check('<860px：只显示 保存 + ⋯更多——查找/导出/主题/退出/设置/信息/纯文本/用户名/字数全部退场（1.6.0.3 两档，删 519px 中间态）',
  /@media \(max-width: 859px\)[\s\S]{0,1200}#topbar #btn-find,\s*#topbar #btn-export,\s*#topbar #btn-theme,\s*#topbar #btn-logout,\s*#topbar #btn-settings,\s*#topbar #btn-doc-info,\s*#topbar #btn-raw-mode,\s*#topbar \.user,\s*#topbar \.word-counter\s*\{\s*display:\s*none/.test(CSS)
  && !/@media \(max-width: 519px\)/.test(CSS));
check('保存按钮不在 859px 收纳清单里（恒显最右）',
  !/@media \(max-width: 859px\)[\s\S]{0,1200}#topbar #btn-save\s*\{\s*display:\s*none/.test(CSS));
check('触发钮选中态：aria-expanded=true 时主色浅底+主色描边（对齐状态与日志四按钮 .on 语义）',
  /#topbar \.tb-trigger\[aria-expanded="true"\]\s*\{[^}]*background:\s*var\(--c-brand-soft\)/.test(CSS)
  && /#topbar \.tb-trigger\[aria-expanded="true"\]\s*\{[^}]*border-color:\s*var\(--c-brand\)/.test(CSS));
check('顶栏防塌缩：字数与用户名允许收缩裁剪（flex 0 1 auto + min-width:0 + overflow:hidden）',
  /#topbar \.word-counter\s*\{[^}]*flex:\s*0 1 auto/.test(CSS)
  && /#topbar \.word-counter\s*\{[^}]*min-width:\s*0/.test(CSS)
  && /#topbar \.user\s*\{[^}]*flex:\s*0 1 auto/.test(CSS)
  && /#topbar \.user\s*\{[^}]*min-width:\s*0/.test(CSS));
check('导出旧绑定已从 initEditorAndFiles 顶栏组移除（改由顶层 initTbMenus 绑定）',
  !/getElementById\('btn-export-md'\)/.test(code)
  && !/getElementById\('btn-export-html'\)/.test(code));
check('initTbMenus 为顶层 IIFE（菜单在登录前即完成绑定，行为一致）',
  /\(function initTbMenus\(\) \{/.test(code));
check('菜单过滤判据是 el.hidden 属性而非 offsetParent（媒体查询收纳的按钮仍入菜单）',
  /if \(!el \|\| el\.hidden\) continue;/.test(code)
  && !/buildMoreMenu[\s\S]{0,600}offsetParent/.test(code));
check('1.6.0.3：act 类型条目（导出两项）恒显，不走 fwd 存在性过滤（修复窄屏下无法导出）',
  /if \(it\.act\) \{[\s\S]{0,500}b\.dataset\.act = it\.act/.test(code));

console.log('== 顶栏下拉菜单（vm 运行时） ==');
check('菜单函数均为顶层可见（tbMenuOpen/tbMenuClose/tbMenuIsOpen/closeTransientMenus/buildMoreMenu/exportFromMenu）',
  ['tbMenuOpen', 'tbMenuClose', 'tbMenuIsOpen', 'closeTransientMenus', 'buildMoreMenu', 'exportFromMenu']
    .every(f => typeof ctx[f] === 'function'));

const exportBtn = getEl('btn-export');
const exportMenu = getEl('export-menu');
const moreBtn = getEl('btn-more');
const moreMenu = getEl('more-menu');
// 真实 HTML 中两个菜单面板均带 hidden 属性（默认关闭）；桩默认 hidden:false，
// 不显式初始化会把「从未打开」误判成「已打开」（触发钮点击走了关闭分支）。
// className 需回填真实类名：外部点击收口逻辑靠 closest('.tb-menu') 判定。
exportMenu.hidden = true;
exportMenu.className = 'tb-menu';
moreMenu.hidden = true;
moreMenu.className = 'tb-menu';

err = null;
try { exportBtn._fire('click'); } catch (e) { err = e; }
check('点「导出」不抛错', err === null, err && err.message);
check('导出菜单打开且触发钮 aria-expanded=true',
  exportMenu.hidden === false && exportBtn.getAttribute('aria-expanded') === 'true',
  { hidden: exportMenu.hidden, aria: exportBtn.getAttribute('aria-expanded') });
check('tbMenuIsOpen 反映打开态', ctx.tbMenuIsOpen('export-menu') === true);
// 1.6.0.3：菜单开着时再点触发钮 → 收回（用户反馈⑥；CDP 真实鼠标实证通过）
err = null;
try { exportBtn._fire('click'); } catch (e) { err = e; }
check('菜单开着时再点「导出」→ 收回（aria-expanded 复位 false）',
  exportMenu.hidden === true && exportBtn.getAttribute('aria-expanded') === 'false',
  { hidden: exportMenu.hidden, aria: exportBtn.getAttribute('aria-expanded') });
err = null;
try { exportBtn._fire('click'); } catch (e) { err = e; }
check('第三次点「导出」→ 重新打开（toggle 循环）', exportMenu.hidden === false);

err = null;
try { moreBtn._fire('click'); } catch (e) { err = e; }
check('同时只开一个：开「⋯ 更多」时导出菜单自动关闭',
  exportMenu.hidden === true && moreMenu.hidden === false,
  { export: exportMenu.hidden, more: moreMenu.hidden });
check('buildMoreMenu：act 条目（导出两项）恒显且带 data-act（1.6.0.3 修复：此前被 fwd 过滤误杀，窄屏无法导出）', (function () {
  const items = moreMenu.children.filter(c => c.className === 'mi');
  const acts = items.filter(c => c.dataset && c.dataset.act);
  return acts.length === 2
      && acts.some(c => c.dataset.act === 'export-md' && c.textContent.indexOf('Markdown') >= 0)
      && acts.some(c => c.dataset.act === 'export-html' && c.textContent.indexOf('HTML') >= 0);
})(), moreMenu.children.map(c => c.dataset && (c.dataset.act || c.dataset.fwd)));
check('buildMoreMenu：fwd 条目含被媒体查询收纳的查找/设置等（隐藏属性之外的按钮仍入菜单）', (function () {
  const items = moreMenu.children.filter(c => c.className === 'mi');
  return items.some(c => c.dataset.fwd === 'btn-find')
      && items.some(c => c.dataset.fwd === 'btn-logout');
})());
check('hidden 属性控制的条件按钮被过滤（raw-mode 隐藏时不出现在菜单）', (function () {
  getEl('btn-raw-mode').hidden = true;
  moreMenu.children.length = 0;          // 桩的 textContent='' 不清空 children，先手动重置
  ctx.buildMoreMenu();
  return !moreMenu.children.some(c => c.dataset && c.dataset.fwd === 'btn-raw-mode');
})());
check('raw-mode 恢复可见后重新入菜单', (function () {
  getEl('btn-raw-mode').hidden = false;
  moreMenu.children.length = 0;
  ctx.buildMoreMenu();
  return moreMenu.children.some(c => c.dataset && c.dataset.fwd === 'btn-raw-mode');
})());
check('全部 fwd 按钮均隐藏时导出两项仍在（收纳态的唯一导出入口）', (function () {
  ['btn-find', 'btn-doc-info', 'btn-raw-mode', 'btn-theme', 'btn-settings', 'btn-logout']
    .forEach(id => { getEl(id).hidden = true; });
  moreMenu.children.length = 0;
  ctx.buildMoreMenu();
  const items = moreMenu.children.filter(c => c.className === 'mi');
  const r = items.length === 2 && items.every(c => c.dataset.act);
  ['btn-find', 'btn-doc-info', 'btn-raw-mode', 'btn-theme', 'btn-settings', 'btn-logout']
    .forEach(id => { getEl(id).hidden = false; });
  return r;
})());
check('菜单项 data-act=export-md → exportDoc("md")', (function () {
  const calls = [];
  ctx.exportDoc = (k) => calls.push(k);
  const mi = mk('mi-md'); mi.className = 'mi'; mi.dataset = { act: 'export-md' };
  docLs.click[0]({ target: mi });
  return calls.length === 1 && calls[0] === 'md';
})());
check('菜单项 data-act=export-html → exportDoc("html")', (function () {
  const calls = [];
  ctx.exportDoc = (k) => calls.push(k);
  const mi = mk('mi-html'); mi.className = 'mi'; mi.dataset = { act: 'export-html' };
  docLs.click[0]({ target: mi });
  return calls.length === 1 && calls[0] === 'html';
})());
check('菜单项点击后菜单自动关闭', moreMenu.hidden === true, moreMenu.hidden);
check('菜单项 data-fwd 转发顶栏按钮 click（契约复用既有绑定）', (function () {
  let fired = 0;
  const tgt = getEl('btn-settings');
  tgt._ls = tgt._ls || {};
  tgt._ls.click = () => { fired++; };
  const mi = mk('mi-fwd'); mi.className = 'mi'; mi.dataset = { fwd: 'btn-settings' };
  docLs.click[0]({ target: mi });
  return fired === 1;
})());
check('点菜单外区域 → 外部点击处理器关闭菜单（capture 派发）', (function () {
  exportBtn._fire('click');                       // 先打开
  const outside = mk('outside');                  // closest 返回 null
  docLs.click[1]({ target: outside });
  return exportMenu.hidden === true;
})());
check('点触发钮/菜单内不触发外部关闭（closest 命中即跳过）', (function () {
  exportBtn._fire('click');                       // 打开
  docLs.click[1]({ target: exportMenu });         // exportMenu.className='tb-menu'
  return exportMenu.hidden === false;
})());
check('closeTransientMenus 返回值语义（关过 true / 无开 false）', (function () {
  if (!ctx.tbMenuIsOpen('export-menu')) exportBtn._fire('click');   // 先确保处于打开态
  const a = ctx.closeTransientMenus();
  const b = ctx.closeTransientMenus();
  return a === true && b === false;
})());
check('关闭后触发钮 aria-expanded 复位 false',
  exportBtn.getAttribute('aria-expanded') === 'false', exportBtn.getAttribute('aria-expanded'));
check('tbMenuOpen 定位写入内联 left/top（px 数值，非 NaN）', (function () {
  exportBtn._fire('click');
  return /^-?\d+(\.\d+)?px$/.test(exportMenu.style.left || '')
      && /^-?\d+(\.\d+)?px$/.test(exportMenu.style.top || '');
})(), { left: exportMenu.style.left, top: exportMenu.style.top });

// ================= 1.6.0.3：Vditor sv 源码模式查找（反馈②） =================
console.log('== 1.6.0.3 sv 源码模式查找 ==');
check('findSourceTextarea / findSelectionPrefill 已定义',
  typeof ctx.findSourceTextarea === 'function'
  && typeof ctx.findSelectionPrefill === 'function');
// sv textarea 桩（Vditor 的 sv 元素本身即 <textarea class="vditor-sv vditor-reset">）
const svTa = mk('sv-ta');
svTa.tagName = 'TEXTAREA';
svTa.offsetParent = {};                 // 可见 = sv 模式激活
svTa.value = 'abc abc';
svTa.selectionStart = 0; svTa.selectionEnd = 0;
svTa.setSelectionRange = function (s, e) { this.selectionStart = s; this.selectionEnd = e; };
svTa.focus = function () { this._focused = true; };
qsSv = svTa;
check('findSourceTextarea：sv 模式（rawMode=false + sv textarea 可见）返回该 textarea',
  ctx.findSourceTextarea() === svTa, ctx.findSourceTextarea() && ctx.findSourceTextarea()._id);
check('findHighlightRoot：sv 模式下 ir 选择器落空（无渲染 DOM 可包，高亮改走选区）',
  (function () { const r = ctx.findHighlightRoot(); return r === null; })());
check('findSelectionPrefill：优先读 textarea 内部选区（window.getSelection 取不到）', (function () {
  svTa.selectionStart = 4; svTa.selectionEnd = 7; svTa.value = 'abc abc';
  const p = ctx.findSelectionPrefill();
  svTa.selectionStart = 0; svTa.selectionEnd = 0;
  return p === 'abc';
})(), svTa.value);
// sv 模式跳转：findScrollToCurrent 把源串偏移翻译成 sv textarea 选区
findContent = 'abc abc';
ctx.findOpen('abc', false);
check('sv 模式 findScrollToCurrent：当前命中 → sv textarea 选区 0-3', (function () {
  ctx.findScrollToCurrent(true);
  return svTa.selectionStart === 0 && svTa.selectionEnd === 3;
})(), { s: svTa.selectionStart, e: svTa.selectionEnd });
ctx.findNext();
check('sv 模式 findNext → findScrollToCurrent：选区跳到第二处 4-7', (function () {
  return svTa.selectionStart === 4 && svTa.selectionEnd === 7;
})(), { s: svTa.selectionStart, e: svTa.selectionEnd });
check('sv 模式越界偏移钳位（陈旧 matches 不抛错、不跳到文末之外）', (function () {
  // findState 是 script 作用域的 const，须经 runInContext 在同一上下文内操作
  vm.runInContext('findState.matches = [{ start: 9999, end: 10002 }]; findState.index = 0;', ctx);
  let e2 = null;
  try { ctx.findScrollToCurrent(true); } catch (e) { e2 = e; }
  const ok = e2 === null && svTa.selectionStart <= 'abc abc'.length;
  vm.runInContext('findState.matches = [{ start: 0, end: 3 }, { start: 4, end: 7 }]; findState.index = 0;', ctx);
  return ok;
})());
qsSv = null;                             // 还原：非 sv 模式
check('非源码态时 findSourceTextarea 返回 null（rawMode=false 且无可见 sv textarea）',
  ctx.findSourceTextarea() === null);

// ================= 1.6.0.3：单活会话 per-tab token（反馈④） =================
console.log('== 1.6.0.3 per-tab token 头注入 ==');
check('tokenGet / tokenSet / tokenClear 已定义',
  typeof ctx.tokenGet === 'function'
  && typeof ctx.tokenSet === 'function'
  && typeof ctx.tokenClear === 'function');
fetchCalls.length = 0;
ctx.tokenSet('tok-abc123');
ctx.fetch('/api/files').catch(() => {});
check('登录后 token 入 sessionStorage，fetch 自动带 X-Vditor-Token 头', (function () {
  const c = fetchCalls[fetchCalls.length - 1];
  return !!c && c.init && c.init.headers && c.init.headers['X-Vditor-Token'] === 'tok-abc123';
})(), fetchCalls[fetchCalls.length - 1] && fetchCalls[fetchCalls.length - 1].init);
check('已带头信息的请求不重复注入（调用方显式设置优先）', (function () {
  fetchCalls.length = 0;
  ctx.fetch('/api/files', { headers: { 'X-Vditor-Token': 'caller-set' } }).catch(() => {});
  const c = fetchCalls[fetchCalls.length - 1];
  return c.init.headers['X-Vditor-Token'] === 'caller-set';
})());
ctx.tokenClear();
fetchCalls.length = 0;
ctx.fetch('/api/files').catch(() => {});
check('登出清 token 后不再带头（退回纯 Cookie 行为）', (function () {
  const c = fetchCalls[fetchCalls.length - 1];
  return !!c && (!c.init.headers || !('X-Vditor-Token' in c.init.headers));
})());
check('sessionStorage 不可用时 tokenGet 静默返回 null（隐私模式降级）', (function () {
  const orig = ctx.sessionStorage;
  ctx.sessionStorage = { getItem() { throw new Error('denied'); } };
  const v = ctx.tokenGet();
  ctx.sessionStorage = orig;
  return v === null;
})());

// ================= 1.6.0.4：源码态查找跳转（反馈③） =================
console.log('== 1.6.0.4 源码态查找跳转 ==');
check('scrollTaToIndex / taMirrorOffsetTop 已定义',
  typeof ctx.scrollTaToIndex === 'function'
  && typeof ctx.taMirrorOffsetTop === 'function');
check('findScrollToCurrent 源码态分支显式调用 scrollTaToIndex（setSelectionRange 不滚动，实证）',
  /function findScrollToCurrent\(doScroll\)[\s\S]{0,1600}scrollTaToIndex\(ta, s\)/.test(code));
check('scrollTaToIndex 镜像/比例双路径（FIND_MIRROR_MAX_CHARS 分档，超大文档不卡布局）',
  /FIND_MIRROR_MAX_CHARS\s*=\s*\d+/.test(code)
  && /taMirrorOffsetTop\(ta, index\)/.test(code)
  && /\(index \/ len\)/.test(code));
check('查找栏窄屏换行（640px 断点：fb-row wrap + 输入框 140px 保底，反馈②）',
  /@media \(max-width: 640px\)[\s\S]{0,300}#find-bar \.fb-row\s*\{\s*flex-wrap:\s*wrap/.test(CSS)
  && /@media \(max-width: 640px\)[\s\S]{0,500}#find-bar \.set-input\s*\{\s*flex:\s*1 1 140px/.test(CSS));
check('更多菜单信息项样式（mi-info：可换行、无悬停态）',
  /\.tb-menu \.mi-info\s*\{[^}]*white-space:\s*normal/.test(CSS)
  && /\.tb-menu \.mi-info:hover\s*\{\s*background:\s*transparent/.test(CSS));
check('菜单项处理器排除 data-wc 信息项（点击不关菜单，反馈①）',
  /mi\.dataset && mi\.dataset\.wc/.test(code));
check('buildMoreMenu 末尾追加 data-wc 信息项',
  /info\.className = 'mi mi-info'/.test(code) && /info\.dataset\.wc = '1'/.test(code));
check('updateCounter 末尾调用 refreshWcMenuItem（菜单保持打开时实时刷新）',
  /function updateCounter\(\)[\s\S]{0,1800}refreshWcMenuItem\(\);/.test(code));
check('wcMenuText / refreshWcMenuItem 已定义',
  typeof ctx.wcMenuText === 'function' && typeof ctx.refreshWcMenuItem === 'function');

// sv textarea 桩（Vditor sv 元素本身即 textarea）
const svTa2 = mk('sv-ta2');
svTa2.tagName = 'TEXTAREA';
svTa2.offsetParent = {};
svTa2.value = 'abc abc';
svTa2.scrollHeight = 20000; svTa2.clientHeight = 600;
svTa2.scrollTop = 0;
svTa2.setSelectionRange = function (s, e) { this.selectionStart = s; this.selectionEnd = e; };
svTa2.focus = function () { this._focused = true; };
qsSv = svTa2;
findContent = 'abc abc';
ctx.findOpen('abc', false);
err = null;
try { ctx.findScrollToCurrent(true); } catch (e) { err = e; }
check('sv 模式：findScrollToCurrent 设选区不抛错', err === null, err && err.message);
check('sv 模式：选中当前命中（0-3）', svTa2.selectionStart === 0 && svTa2.selectionEnd === 3,
  { s: svTa2.selectionStart, e: svTa2.selectionEnd });
check('sv 模式：显式滚动到镜像量测位置（stubOffsetTop - clientHeight/3 = 4042）',
  svTa2.scrollTop === 4242 - 200, svTa2.scrollTop);
// 已设过 scrollTop 后再跳一处：滚动量应更新而非停留
stubOffsetTop = 9000;
ctx.findNext();
check('sv 模式：连续跳转滚动量随新命中更新（9000-200=8800）',
  svTa2.scrollTop === 8800 && svTa2.selectionStart === 4, { sl: svTa2.scrollTop, s: svTa2.selectionStart });
// 超大文档：比例估算路径（不触发镜像，len > FIND_MIRROR_MAX_CHARS）
stubOffsetTop = 999999;                     // 若误走镜像会得到 999999-200，借此区分路径
svTa2.value = 'x'.repeat(600001);
svTa2.scrollHeight = 1200000;
ctx.scrollTaToIndex(svTa2, 300000);
check('超大文档走比例估算（300000/600001×1200000-200≈599799，非镜像值）',
  Math.abs(svTa2.scrollTop - 599799) <= 2, svTa2.scrollTop);
// 越界偏移不抛错（matches 陈旧）
err = null;
try { ctx.scrollTaToIndex(svTa2, 99999999); } catch (e) { err = e; }
check('scrollTaToIndex 越界 index 不抛错（比例仍有效）', err === null, err && err.message);
qsSv = null;

// ================= 1.6.0.4：字数统计入「⋯ 更多」（反馈①） =================
console.log('== 1.6.0.4 字数统计菜单项 ==');
moreMenu.hidden = false;
moreMenu.children.length = 0;
ctx.buildMoreMenu();
const wcItem = moreMenu.children.find(c => c.dataset && c.dataset.wc);
check('buildMoreMenu 末尾追加字数统计信息项（class=mi mi-info + data-wc）',
  !!wcItem && wcItem.className === 'mi mi-info', wcItem && wcItem.className);
check('信息项文案含三项口径（正文/含语法/阅读）',
  !!wcItem && wcItem.textContent.indexOf('字数：正文 ') === 0
  && wcItem.textContent.indexOf('含语法') > 0, wcItem && wcItem.textContent);
// 点击信息项：菜单项处理器应直接返回（不关菜单）
err = null;
try { docLs.click[0]({ target: wcItem }); } catch (e) { err = e; }
check('点击字数信息项不抛错且不关闭菜单', err === null && moreMenu.hidden === false,
  { err: err && err.message, hidden: moreMenu.hidden });
// 实时刷新：菜单开着 + 顶栏计数变化 → 信息项文案更新
getEl('wc-text').textContent = '1234';
getEl('wc-md').textContent = '2345';
getEl('wc-read').textContent = '约 3 分钟';
qsWcItem = wcItem;                            // 让桩的 querySelector 返回真实信息项
ctx.refreshWcMenuItem();
check('refreshWcMenuItem 菜单打开时实时刷新文案',
  !!wcItem && wcItem.textContent === '字数：正文 1234 · 含语法 2345 · 约 3 分钟',
  wcItem && wcItem.textContent);
// 菜单关闭时刷新为空操作（不抛错）
moreMenu.hidden = true;
err = null;
try { ctx.refreshWcMenuItem(); } catch (e) { err = e; }
check('refreshWcMenuItem 菜单关闭时静默跳过', err === null, err && err.message);

// ================= 1.6.0.5：wysiwyg 查找 + 切模式自动恢复 + 查找钮 toggle =================
console.log('== 1.6.0.5 wysiwyg / 模式切换 / 查找钮 ==');
check('wysiwyg 高亮 CSS（浅色 + 深色，与 ir 同语言）',
  /\.vditor-wysiwyg mark\.vd-find\s*\{/.test(CSS)
  && /\.vditor-wysiwyg mark\.vd-find-current\s*\{/.test(CSS)
  && /html\[data-theme="dark"\] \.vditor-wysiwyg mark\.vd-find\s*\{/.test(CSS));
check('findMarkCurrent 独立函数 + findCompute / findScrollToCurrent 均调用（自动重算不丢当前命中）',
  /function findMarkCurrent\(\)/.test(code)
  && /function findCompute\(\)[\s\S]{0,1400}findMarkCurrent\(\);/.test(code)
  && /function findScrollToCurrent\(doScroll\)[\s\S]{0,1600}findMarkCurrent\(\);/.test(code));
check('findClearMarks 清 ir + wysiwyg 两个宿主（切换模式后旧宿主不残留）',
  /function findClearMarks\(\)[\s\S]{0,700}#vditor \.vditor-ir > \.vditor-reset, #vditor \.vditor-wysiwyg/.test(code));
check('模式切换观察者（MutationObserver + findSeq 自触发守卫）',
  /initFindModeWatch/.test(code) && /new MutationObserver/.test(code)
  && /findSeq\+\+/.test(code) && /findSeq !== lastSeq/.test(code));
check('顶栏查找按钮为 toggle（已开再点调用 findClose）',
  /btnFind\.addEventListener\('click', \(\) => \{[\s\S]{0,200}findState\.open\) \{ findClose\(\); return; \}/.test(code));

// —— vm：findHighlightRoot 模式感知 ——
const wyHost = mk('wy-host');
wyHost.className = 'vditor-wysiwyg';
qsWy = wyHost;
vm.runInContext("vditor = { vditor: { currentMode: 'wysiwyg' } };", ctx);
check('findHighlightRoot：wysiwyg 模式返回 .vditor-wysiwyg 宿主',
  ctx.findHighlightRoot() === wyHost, (ctx.findHighlightRoot() || {})._id);
vm.runInContext("vditor = { vditor: { currentMode: 'sv' } };", ctx);
check('findHighlightRoot：sv 模式返回 null（textarea 无渲染 DOM）',
  ctx.findHighlightRoot() === null);
vm.runInContext("vditor = null;", ctx);
check('findHighlightRoot：mode 取不到时回落 ir 选择器（qsHost）',
  ctx.findHighlightRoot() === qsHost, (ctx.findHighlightRoot() || {})._id);

// —— vm：findMarkCurrent 标记当前命中（跨宿主） ——
const mkA = mk('mkA'); mkA.className = 'vd-find';
const mkB = mk('mkB'); mkB.className = 'vd-find';
qsMarksList = [mkA, mkB];
vm.runInContext("findState.index = 1; findState.matches = [{start:0,end:1},{start:2,end:3}];", ctx);
ctx.findMarkCurrent();
check('findMarkCurrent：只给当前索引的 mark 挂 vd-find-current',
  !mkA.classList.contains('vd-find-current') && mkB.classList.contains('vd-find-current'));
vm.runInContext("findState.index = 0;", ctx);
ctx.findMarkCurrent();
check('findMarkCurrent：索引变化后 current 随之转移',
  mkA.classList.contains('vd-find-current') && !mkB.classList.contains('vd-find-current'));
qsMarksList = [];

// —— vm：顶栏查找按钮 toggle ——
const barForToggle = getEl('find-bar');
ctx.findClose();                                    // 先确保关闭态
barForToggle.hidden = true;
const btnF = getEl('btn-find');
err = null;
try { btnF._fire('click'); } catch (e) { err = e; }
check('点查找钮：关闭态 → 打开', err === null && barForToggle.hidden === false, { err: err && err.message, hidden: barForToggle.hidden });
err = null;
try { btnF._fire('click'); } catch (e) { err = e; }
check('再点查找钮：已开 → 收回（1.6.0.5 反馈②）', err === null && barForToggle.hidden === true, { err: err && err.message, hidden: barForToggle.hidden });
err = null;
try { btnF._fire('click'); } catch (e) { err = e; }
check('第三次点查找钮：重新打开（toggle 循环）', err === null && barForToggle.hidden === false);

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);;