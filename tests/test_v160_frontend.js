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

// ================= 静态断言：查找与替换（1.6.0 需求三） =================
console.log('== 查找与替换（静态） ==');
const findBar = (html.match(/<div id="find-bar"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/) || [''])[0];
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
check('Esc 优先关闭查找栏（先于弹窗栈）',
  /if \(e\.key === 'Escape'\)\s*\{\s*\/\/ 1\.6\.0：查找栏是最 transient 的 UI，Esc 优先关它，再走弹窗栈\s*if \(findState\.open\)\s*\{\s*findClose\(\);/.test(code));
check('面板内 Enter/F3 跳转、Shift 反向',
  /if \(e\.key === 'Enter'\)\s*\{\s*e\.preventDefault\(\);\s*if \(e\.shiftKey\) findPrev\(\); else findNext\(\);/.test(code));
check('保存前强制清除高亮（doSave → findClearMarks，防 <mark> 混进正文）',
  /function doSave\(silent\)\s*\{\s*\/\/ 1\.6\.0：保存前强制清除查找高亮[\s\S]{0,120}findClearMarks\(\);/.test(code));
check('切文件 / 切渲染模式时关闭查找栏（防陈旧命中）',
  /if \(findState\.open\) findClose\(\);/.test(code)
  && (code.match(/if \(findState\.open\) findClose\(\);/g) || []).length >= 3);
check('清除高亮走「展开子节点 + removeChild + normalize」精确还原',
  /while \(mk\.firstChild\) parent\.insertBefore\(mk\.firstChild, mk\);[\s\S]{0,80}parent\.removeChild\(mk\);[\s\S]{0,60}parent\.normalize\(\)/.test(code));
check('高亮 <mark> 样式特异性高于 Vditor 自带 mark 规则',
  /\.vditor-reset mark\.vd-find\s*\{/.test(CSS)
  && /\.vditor-reset mark\.vd-find-current\s*\{/.test(CSS)
  && /html\[data-theme="dark"\] \.vditor-reset mark\.vd-find\s*\{/.test(CSS));
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
function mk(id) {
  const cls = new Set();
  const attrs = {};
  const el = {
    _id: id, id: '', textContent: '', title: '', value: '', innerHTML: '', disabled: false,
    style: {}, dataset: {}, children: [], hidden: false, className: '',
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
    _fire(t) { if (this._ls && this._ls[t]) this._ls[t](); },
    closest() { return null; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
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
function getEl(id) { return ids[id] || (ids[id] = mk(id)); }
const store = {};
// 可配置的 query 结果（供 findHighlightRoot 测试注入假渲染区）
let qsHost = null;
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
    querySelector: (sel) => (sel === '#vditor .vditor-reset' ? (qsHost || mk('qs')) : mk('qs')),
    querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
    body: mk('body'), documentElement: mk('html'), cookie: ''
  },
  navigator: { userAgent: 'node', platform: 'Win32' },
  location: { href: 'http://x/', search: '', hash: '', protocol: 'http:' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  setTimeout: (fn) => { timers.push(fn); return timers.length; },
  clearTimeout: () => {},
  setInterval() {}, clearInterval() {},
  fetch() { return Promise.reject(new Error('no-net')); },
  TextEncoder, TextDecoder, alert() {}, confirm() { return true; }, prompt() { return null; },
  btoa: s => Buffer.from(s).toString('base64'), atob: s => Buffer.from(s, 'base64').toString(),
  addEventListener() {}, removeEventListener() {}, history: {},
  performance: { now: () => Date.now() },
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
function step(n) { for (let i = 0; i < n && rafQueue.length; i++) rafQueue.shift()(); }
function flushTimers() { const t = timers.slice(); timers.length = 0; t.forEach(fn => fn()); }

nameEl.scrollWidth = 100; nameEl.clientWidth = 300;
let err = null;
try { ctx.setCurName('短名.md'); } catch (e) { err = e; }
check('setCurName 短名不抛错', err === null, err && err.message);
check('setCurName 写入 textContent', nameEl.textContent === '短名.md', nameEl.textContent);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(3);
check('不溢出时无滚动动画（transform 为空）', nameEl.style.transform === '', nameEl.style.transform);

nameEl.scrollWidth = 500; nameEl.clientWidth = 300;
err = null;
try { ctx.setCurName('一个非常长的文件名字段用来测试横向滚动行为.md'); } catch (e) { err = e; }
check('setCurName 长名不抛错', err === null, err && err.message);
rafQueue.length = 0; ctx.updateFilenameScroll();
step(1);
const transforms = [];
for (let i = 0; i < 5; i++) { step(1); transforms.push(nameEl.style.transform); }
check('溢出时启动滚动（transform 非空）', transforms[0] !== '', transforms[0]);
check('transform 逐步左移（translateX 负值递增）',
  /translateX\(-(\d+)px\)/.test(transforms[4])
  && parseInt(RegExp.$1, 10) > parseInt((/-(\d+)px\)/.exec(transforms[0]) || [0, 0])[1], 10),
  transforms);
nameEl._fire('mouseenter');
step(3);
const beforePause = nameEl.style.transform;
step(3);
check('悬停后滚动暂停（transform 不再变化）', nameEl.style.transform === beforePause,
  { before: beforePause, after: nameEl.style.transform });
nameEl._fire('mouseleave');
step(1);
check('移开恢复后 transform 继续变化', nameEl.style.transform !== beforePause);
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
err = null;
try { ctx.findClearMarks(); } catch (e) { err = e; }
check('findClearMarks 不抛错', err === null, err && err.message);
check('清除后还原为纯文本节点（无 mark 残留）',
  !para.children.some(c => c.className === 'vd-find')
  && para.children.filter(c => c.nodeType === 3).map(c => c.nodeValue).join('') === 'abc abc',
  para.children.map(c => c.nodeType === 3 ? '#' + c.nodeValue : (c.className || c._id)));

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
