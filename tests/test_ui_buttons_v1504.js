// 1.5.0.4 专项测试：按钮交互体系 + 列表体积悬停提示 + 10MB 门禁对话框
// 覆盖：.btn 基类与四变体、:focus-visible 焦点环、统一 disabled、
//       ghost hover 不改底色、二次确认反色设计保留、通用文本框类、
//       列表不再常驻显示体积、门禁对话框按钮顺序与配色。
// 另含 renderFiles 的 vm 真实调用（防跨作用域 ReferenceError 回归）。
// 1.5.0.4 验证：按钮体系 + renderFiles（移除体积标签）+ 门禁对话框
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('vditor-fpk/app/index.html', 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) { console.error('FAIL: 未找到主内联脚本'); process.exit(1); }
const code = m[1];

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS', name); }
  else { fail++; console.log('  FAIL', name, extra === undefined ? '' : JSON.stringify(extra)); }
}

// ---------- 静态断言：按钮体系 ----------
const CSS = (html.match(/<style>([\s\S]*?)<\/style>/)||['',''])[1];
console.log('== 按钮体系静态检查（查 CSS 段）==');
check('定义 .btn 基类', /\.btn,/.test(CSS) || /\.btn:focus-visible/.test(CSS));
check('定义 .btn--primary 变体', /\.btn--primary[,\s]/.test(CSS));
check('定义 .btn--ghost 变体', /\.btn--ghost[,\s]/.test(CSS));
check('定义 .btn--danger 变体', /\.btn--danger[,\s]/.test(CSS));
check('有 :focus-visible 焦点环', /:focus-visible/.test(CSS));
check('有统一 disabled 规则', /\.btn:disabled/.test(CSS));
check('ghost hover 不改底色（用 --c-btn-ghost-bg 而非 brand）',
  /\.btn--ghost:hover:not\(:disabled\)[\s\S]{0,400}--c-btn-ghost-bg/.test(CSS));
check('已移除 filter: brightness 的按钮 hover',
  !/bigdoc-ok:not\(:disabled\):hover\s*\{\s*filter/.test(html));
check('二次确认反色设计保留', /#confirm-mask #confirm-cancel/.test(CSS));
check('新增 --c-warn-hover 浅色令牌', /--c-warn-hover:\s*#92400e/.test(CSS));
check('新增 --c-warn-hover 深色令牌', /--c-warn-hover:\s*#f5b942/.test(CSS));
check('新增 --c-btn-ghost-bg 双主题', (CSS.match(/--c-btn-ghost-bg:/g) || []).length === 2);
check('移除 dark模式逐条 ghost 覆写',
  !/data-theme="dark"\] #topbar button\.ghost/.test(CSS));

// ---------- 静态断言：体积标注移除 ----------
console.log('== 列表体积标注 ==');
check('移除 .fsize 样式', !/#file-list li \.fsize/.test(code));
check('移除 .big-doc 样式', !/#file-list li\.big-doc/.test(code));
check('移除 li 的 flex 布局（不再分列）', !/#file-list li \{[^}]*display: flex/.test(code));
check('renderFiles 不再创建 fsize 元素', !/className = 'fsize'/.test(code));
check('renderFiles 不再添加 big-doc 类', !/classList\.add\('big-doc'\)/.test(code));
check('title 提示保留体积', /li\.title = f\.path/.test(code));

// ---------- 静态断言：门禁对话框 ----------
console.log('== 10MB 门禁对话框 ==');
const bigdocBlock = (html.match(/<div id="bigdoc-mask"[\s\S]*?<\/div>\s*<\/div>/) || [''])[0];
check('输入框复用 .set-input', /id="bigdoc-input"[^>]*class="set-input"/.test(html));
check('输入框已移除行内 style hack', !/id="bigdoc-input"[^>]*style=/.test(html));
check('取消=primary（蓝底）', /id="bigdoc-cancel"[^>]*btn--primary|btn--primary[^>]*id="bigdoc-cancel"/.test(bigdocBlock));
check('仍然打开=ghost（白底）', /class="btn btn--ghost" id="bigdoc-ok"/.test(bigdocBlock));
check('取消在左、仍然打开在右',
  bigdocBlock.indexOf('bigdoc-cancel') < bigdocBlock.indexOf('bigdoc-ok'));
check('仍然打开默认禁用', /id="bigdoc-ok"[^>]*disabled/.test(bigdocBlock));

// ---------- 运行时：renderFiles真调 ----------
console.log('== renderFiles 运行时 ==');
const ids = {};
function mk(id) {
  const cls = new Set();
  return {
    _id: id, id: '', textContent: '', title: '', value: '', innerHTML: '', disabled: false,
    style: {}, dataset: {}, children: [],
    classList: { add(c){cls.add(c);}, remove(c){cls.delete(c);},
                 toggle(c,f){ f?cls.add(c):cls.delete(c); }, contains(c){return cls.has(c);} },
    appendChild(c){ this.children.push(c); return c; },
    addEventListener(){}, removeEventListener(){}, remove(){}, contains(){return false;},
    getAttribute(){return null;}, setAttribute(){},
    querySelector(){return mk('q');}, querySelectorAll(){return[];},
    focus(){}, click(){}, closest(){return null;},
    getBoundingClientRect(){return {top:0,left:0,width:0,height:0};}
  };
}
function getEl(id){ return ids[id] || (ids[id] = mk(id)); }
const store = {};
const ctx = {
  console, document: {
    getElementById: getEl, createElement: () => mk('created'),
    querySelector: () => mk('qs'), querySelectorAll: () => [],
    addEventListener(){}, removeEventListener(){},
    body: mk('body'), documentElement: mk('html'), cookie: ''
  },
  navigator: { userAgent:'node', platform:'Win32' },
  location: { href:'http://x/', search:'', hash:'', protocol:'http:' },
  localStorage: { getItem:k=>(k in store?store[k]:null), setItem:(k,v)=>{store[k]=String(v);}, removeItem:k=>{delete store[k];} },
  setTimeout(){}, clearTimeout(){}, setInterval(){}, clearInterval(){},
  fetch(){ return Promise.reject(new Error('no-net')); },
  TextEncoder, TextDecoder, alert(){}, confirm(){return true;}, prompt(){return null;},
  btoa:s=>Buffer.from(s).toString('base64'), atob:s=>Buffer.from(s,'base64').toString(),
  addEventListener(){}, removeEventListener(){}, history:{},
  performance:{now:()=>Date.now()}, requestAnimationFrame(){},
  Vditor: function(){ throw new Error('no editor'); },
  JSON, Math, Date, RegExp, Promise, console,
  Uint8Array, ArrayBuffer, String, Number, Object, Array, Boolean, Map, Set,
  encodeURIComponent, decodeURIComponent, isNaN, parseInt, parseFloat
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx; ctx.top = ctx;
vm.createContext(ctx);
let boot = null;
try { vm.runInContext(code, ctx, { filename:'inline.js' }); }
catch (e) { boot = e; }
check('脚本可加载', boot === null, boot && boot.message);

function tryRender(label, roots) {
  ids['side-scroll'] = mk('side-scroll');
  let err = null;
  try { ctx.renderFiles(roots); } catch(e) { err = e; }
  return { err, boxes: ids['side-scroll'].children.length };
}

let r = tryRender('含 >10MB', [{ id:'r1', name:'我的文档', path:'/x', exists:true, files:[
  { name:'small.md', path:'/x/small.md', root:'r1', size:1200 },
  { name:'huge.md', path:'/x/huge.md', root:'r1', size:20*1024*1024 }
]}]);
check('renderFiles 不抛错（含 >10MB）', r.err === null, r.err && r.err.message);
check('侧边栏挂上分区块', r.boxes === 1, r.boxes);

r = tryRender('恰好 10MB', [{ id:'r1', name:'D', path:'/x', exists:true, files:[
  { name:'e.md', path:'/x/e.md', root:'r1', size:10*1024*1024 }]}]);
check('renderFiles 不抛错（恰好 10MB）', r.err === null, r.err && r.err.message);

r = tryRender('无 size', [{ id:'r1', name:'D', path:'/x', exists:true, files:[
  { name:'n.md', path:'/x/n.md', root:'r1' }]}]);
check('renderFiles 不抛错（无 size）', r.err === null, r.err && r.err.message);

r = tryRender('size=0/-1', [{ id:'r1', name:'D', path:'/x', exists:true, files:[
  { name:'z.md', path:'/x/z.md', root:'r1', size:0 },
  { name:'g.md', path:'/x/g.md', root:'r1', size:-1 }]}]);
check('renderFiles 不抛错（size=0/-1）', r.err === null, r.err && r.err.message);

r = tryRender('多分区', [
  { id:'r1', name:'A', path:'/a', exists:true, files:[] },
  { id:'r2', name:'B', path:'/b', exists:false, files:[] }
]);
check('renderFiles 不抛错（空分区/目录不存在/多分区）', r.err === null, r.err && r.err.message);
check('多分区均渲染', r.boxes === 2, r.boxes);

r = tryRender('空数组', []);
check('renderFiles 不抛错（空列表）', r.err === null, r.err && r.err.message);

// 体积提示文案
tryRender('提示检查', [{ id:'r1', name:'D', path:'/x', exists:true, files:[
  { name:'huge.md', path:'/x/huge.md', root:'r1', size:20*1024*1024 },
  { name:'n.md', path:'/x/n.md', root:'r1' }]}]);
const ul = ids['side-scroll'].children[0].children.find(c => c.id === 'file-list');
const items = ul ? ul.children : [];
check('列表项不再有 fsize 子元素',
  items.every(li => !li.children.some(c => c.className === 'fsize')), items.length);
check('超大文档 li.title 含体积与二次确认提示',
  items[0] && /20\.00 MB/.test(String(items[0].title || '')) && /超大文档/.test(String(items[0].title || '')),
  items[0] && String(items[0].title || ''));
check('无 size 的 li.title 不含体积',
  items[1] && String(items[1].title || '') === '/x/n.md',
  items[1] && String(items[1].title || ''));

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
