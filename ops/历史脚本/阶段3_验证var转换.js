#!/usr/bin/env node
/**
 * 阶段 3 验证：逐节点比对「原文件」与「var 转换后文件」的 AST。
 * 唯一允许的差异：VariableDeclaration 的 kind（var -> let/const）。
 * 其它任何差异（运算符、字面量、标识符、结构）都报出来。
 *
 * 用法：node 阶段3_验证var转换.js <原.js> <转换后.js>
 */
const fs = require('fs');
const path = require('path');

const TOOLS = 'D:/项目/中节能/0911训练/_中间产物/.tools/node_modules';
const acorn = require(path.join(TOOLS, 'acorn'));

const [, , A, B] = process.argv;
const parse = (f) => acorn.parse(fs.readFileSync(f, 'utf8'), {
  ecmaVersion: 2022, sourceType: 'script', ranges: true, locations: true,
});
const ta = parse(A);
const tb = parse(B);

const SKIP = new Set(['loc', 'range', 'start', 'end', 'parent']);
const diffs = [];
let nodes = 0;

function cmp(a, b, p) {
  if (a === b) return;
  if (a === null || b === null || a === undefined || b === undefined) {
    diffs.push(`${p}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
    return;
  }
  if (typeof a !== 'object' || typeof b !== 'object') {
    diffs.push(`${p}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
    return;
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
      diffs.push(`${p}: 数组长度/类型不同`);
      return;
    }
    for (let i = 0; i < a.length; i++) cmp(a[i], b[i], `${p}[${i}]`);
    return;
  }
  nodes++;
  if (a.type !== b.type) {
    diffs.push(`${p}: 节点类型 ${a.type} != ${b.type}`);
    return;
  }
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    if (SKIP.has(k)) continue;
    // 唯一允许的变化
    if (k === 'kind' && a.type === 'VariableDeclaration') {
      if (!(a.kind === 'var' && (b.kind === 'let' || b.kind === 'const'))) {
        diffs.push(`${p}.kind: ${a.kind} -> ${b.kind}（非预期）`);
      }
      continue;
    }
    cmp(a[k], b[k], `${p}.${k}`);
  }
}

cmp(ta, tb, 'root');

console.log(`${path.basename(A)}  →  ${path.basename(B)}`);
console.log(`  比对节点 ${nodes} 个`);
if (diffs.length === 0) {
  console.log('  ★ AST 等价：唯一差异是 var 的 kind（转成 let/const）');
} else {
  console.log(`  ✗ 发现 ${diffs.length} 处非预期差异：`);
  for (const d of diffs.slice(0, 25)) console.log('    ' + d);
  process.exit(1);
}
