#!/usr/bin/env node
/**
 * 阶段 3：基于 AST 的 var -> let/const 转换（准确，不猜）。
 *
 * 为什么不用正则：var 是函数作用域、let/const 是块作用域，且 var 会提升。
 *   if (x) { var a = 1; } use(a);   // var 能用，let 会 ReferenceError
 *   use(b); var b = 2;              // var 得到 undefined，let 会 TDZ 报错
 * 我第一版用正则 + 全文件作用域判断，结果把跨函数的同名变量（d / box / f / n）
 * 全误判成"不安全"，还把声明自身的 = 算成了重新赋值 —— 所以 const 数为 0，
 * 明显不可信。改用 acorn + eslint-scope 拿真实作用域。
 *
 * 用法：node 阶段3_var转换.js <输入.js> <输出.js>
 */
const fs = require('fs');
const path = require('path');

const TOOLS = 'D:/项目/中节能/0911训练/_中间产物/.tools/node_modules';
const acorn = require(path.join(TOOLS, 'acorn'));
const eslintScope = require(path.join(TOOLS, 'eslint-scope'));

const [, , IN, OUT] = process.argv;
if (!IN || !OUT) {
  console.error('用法: node 阶段3_var转换.js <输入.js> <输出.js>');
  process.exit(2);
}

const src = fs.readFileSync(IN, 'utf8');
const ast = acorn.parse(src, {
  ecmaVersion: 2022,
  sourceType: 'script',
  ranges: true,
  locations: true,
});

// acorn 不挂 parent，自己补
(function addParents(node, parent) {
  node.parent = parent;
  for (const key of Object.keys(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range') continue;
    const v = node[key];
    if (Array.isArray(v)) {
      for (const c of v) if (c && typeof c.type === 'string') addParents(c, node);
    } else if (v && typeof v.type === 'string') {
      addParents(v, node);
    }
  }
})(ast, null);

const scopeManager = eslintScope.analyze(ast, {
  ecmaVersion: 2022,
  sourceType: 'script',
  optimistic: false,
  ignoreEval: true,
});

function nearestBlock(node) {
  let n = node.parent;
  while (n && n.type !== 'BlockStatement' && n.type !== 'Program' &&
         n.type !== 'FunctionDeclaration' && n.type !== 'FunctionExpression' &&
         n.type !== 'ArrowFunctionExpression') {
    n = n.parent;
  }
  return n;
}

/** 声明的作用域边界：for 的 init 里声明时，边界是整条 for 语句（let 也活到循环结束）。 */
function boundaryOf(decl) {
  const p = decl.parent;
  if (p && (p.type === 'ForStatement' || p.type === 'ForInStatement' ||
            p.type === 'ForOfStatement')) {
    return p;
  }
  return nearestBlock(decl);
}

function enclosingFunction(node) {
  let n = node.parent;
  while (n) {
    if (n.type === 'FunctionDeclaration' || n.type === 'FunctionExpression' ||
        n.type === 'ArrowFunctionExpression') {
      return n;
    }
    n = n.parent;
  }
  return null;
}

function functionBodyOf(node) {
  let n = node.parent;
  while (n) {
    if (n.type === 'FunctionDeclaration' || n.type === 'FunctionExpression' ||
        n.type === 'ArrowFunctionExpression') {
      return n.body && n.body.type === 'BlockStatement' ? n.body : null;
    }
    n = n.parent;
  }
  return null;
}

const stats = { const: 0, let: 0, unsafe: 0, mixed: 0, already: 0 };
const edits = [];   // {start, end, text}
const details = [];

const seenDecls = new Set();
for (const scope of scopeManager.scopes) {
  for (const variable of scope.variables) {
    for (const def of variable.defs) {
      if (def.type !== 'Variable' || !def.parent || def.parent.kind !== 'var') continue;
      const decl = def.parent;
      if (seenDecls.has(decl)) continue;
      seenDecls.add(decl);

      const boundary = boundaryOf(decl);
      const declFn = enclosingFunction(decl);
      const loopDecl = decl.parent &&
        (decl.parent.type === 'ForStatement' || decl.parent.type === 'ForInStatement' ||
         decl.parent.type === 'ForOfStatement');
      const declLine = decl.loc.start.line;

      // 引用是否都落在边界内 / 是否在声明前被引用 / 是否被闭包捕获
      let escaped = false;
      let beforeDecl = false;
      let closureRef = false;
      for (const ref of variable.references) {
        const id = ref.identifier;
        if (ref.init) continue;                       // 声明自身的初始化，不算
        if (id.range[0] < decl.range[0]) beforeDecl = true;
        if (boundary && boundary.type !== 'Program' &&
            (id.range[0] < boundary.range[0] || id.range[1] > boundary.range[1])) {
          escaped = true;
        }
        if (enclosingFunction(id) !== declFn) closureRef = true;
      }

      const names = decl.declarations.map((d) => src.slice(d.id.range[0], d.id.range[1]));

      // ★ 语义陷阱：for 的循环变量若被闭包捕获，var 与 let 行为不同 ——
      //     for (var i=0;i<3;i++) setTimeout(()=>log(i));  // 3,3,3
      //     for (let i=0;i<3;i++) setTimeout(()=>log(i));  // 0,1,2
      //   这种情况**必须保留 var**，否则静默改变行为。
      let why = '';
      if (beforeDecl) why = '声明前被引用（var 会提升）';
      else if (escaped) why = '有引用逃出该块';
      else if (loopDecl && closureRef) why = '循环变量被闭包捕获（var/let 语义不同）';

      if (why) {
        stats.unsafe++;
        details.push(['保留 var', names.join(','), declLine, why]);
        continue;
      }
      // 同一 var 语句里若各 declarator 需求不一致，统一用 let（永远正确）
      const wants = decl.declarations.map((d) => {
        let w = false;
        for (const ref of variable.references) {
          if (!ref.init && ref.isWrite()) w = true;
        }
        return w;
      });
      let kind;
      if (wants.every((w) => !w)) kind = 'const';
      else kind = 'let';
      if (new Set(wants).size > 1) stats.mixed++;
      stats[kind]++;
      details.push([kind, names.join(','), declLine, '']);
      edits.push({ start: decl.range[0], end: decl.range[0] + 3, text: kind });
    }
  }
}

// 从后往前替换，避免位移
edits.sort((a, b) => b.start - a.start);
let out = src;
for (const e of edits) {
  if (out.slice(e.start, e.end) !== 'var') {
    console.error('位置校验失败 @' + e.start + '：' + JSON.stringify(out.slice(e.start, e.end)));
    process.exit(1);
  }
  out = out.slice(0, e.start) + e.text + out.slice(e.end);
}

fs.writeFileSync(OUT, out, 'utf8');

const total = stats.const + stats.let + stats.unsafe;
console.log(`${path.basename(IN)}：var 声明 ${total} 个`);
console.log(`  → const ${stats.const} 个，let ${stats.let} 个，保留 var ${stats.unsafe} 个`
  + (stats.mixed ? `（其中 ${stats.mixed} 条混合声明统一降级为 let）` : ''));
console.log(`  输出 ${OUT}（${Buffer.byteLength(out)} 字节，原 ${Buffer.byteLength(src)} 字节）`);
const remain = (out.match(/(?<![.\w$])var\s+[\w$]/g) || []).length;
console.log(`  转换后残留 var：${remain} 个`);
if (stats.unsafe) {
  console.log('  保留 var 的（需人工看，不是错，只是块作用域下不安全）：');
  for (const [k, nm, ln, why] of details.filter((d) => d[0] === '保留 var')) {
    console.log(`    行 ${ln}  ${nm}  —— ${why}`);
  }
}
