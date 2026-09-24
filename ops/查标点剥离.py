#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 normalize_question 的标点剥离**真的按预期工作**。

为什么单独测这个：上一版 _PUNCT 的字符串字面量被 ASCII 双引号截断了，
编译期只报一个 SyntaxWarning（很容易被忽略），但字符类的实际内容
和写的人以为的不一样。所以这里不看源码"像不像对的"，直接喂输入看输出：
每个用例都写清「输入 → 期望输出」，并配反向断言。
"""
import sys

sys.path.insert(0, "_中间产物/重构工作区")

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("error")           # 有任何 SyntaxWarning 就当场失败
    from xishu_pipeline.resilience import normalize_question

ok = 0
bad = []


def check(name, got, want):
    global ok
    if got == want:
        print("  OK   %s" % name)
        ok += 1
    else:
        print("  ★    %s\n        得到 %r\n        期望 %r" % (name, got, want))
        bad.append(name)


print("=== 1. 该剥掉的标点，逐个类型验证 ===")
cases = [
    ("ASCII 双引号", '危险"废物"怎么管', "危险废物怎么管"),
    ("ASCII 单引号", "危险'废物'怎么管", "危险废物怎么管"),
    ("中文全角括号", "危险（废物）怎么管", "危险废物怎么管"),
    ("中文方括号", "危险【废物】怎么管", "危险废物怎么管"),
    ("书名号", "《固废法》怎么规定", "固废法怎么规定"),
    ("中文逗号句号", "危险，废物。怎么管", "危险废物怎么管"),
    ("中文问号叹号", "危险废物？怎么管！", "危险废物怎么管"),
    ("中文顿号分号冒号", "危险、废物；怎么：管", "危险废物怎么管"),
    ("满角空格 U+3000", "危险　废物", "危险废物"),
    ("ASCII 空白", "危险 \t\n 废物", "危险废物"),
    ("反引号", "危险`废物`", "危险废物"),
    ("波浪号", "危险~废物", "危险废物"),
    ("at 井号美元", "危险@废物#怎么$管", "危险废物怎么管"),
    ("百分号脱字符", "危险%废物^怎么&管", "危险废物怎么管"),
    ("星号加号等号", "危险*废物+怎么=管", "危险废物怎么管"),
    ("竖线斜杠", "危险|废物/怎么管", "危险废物怎么管"),
    ("破折号", "危险—废物", "危险废物"),
    ("中划线", "危险-废物", "危险废物"),
    ("ASCII 问号", "危险?废物", "危险废物"),
    ("ASCII 感叹号", "危险!废物", "危险废物"),
    ("ASCII 点", "危险.废物", "危险废物"),
    ("ASCII 逗号", "危险,废物", "危险废物"),
    ("ASCII 分号冒号", "危险;废物:管", "危险废物管"),
    ("单书名号", "危险〈废物〉", "危险〈废物〉"),   # 未收录，应保留
]
for name, src, want in cases:
    check(name, normalize_question(src), want)

print()
print("=== 2. 反斜杠：这是上一版真正出错的地方 ===")
# 上一版里 \\ 因为截断变成了单个反斜杠，字符类含义变了。
# 现在 r'...\\...' 是"两个字符"，regex 里表示"一个反斜杠"。
check("反斜杠被剥掉", normalize_question("危险\\废物"), "危险废物")
check("正斜杠被剥掉", normalize_question("危险/废物"), "危险废物")
check("连续反斜杠", normalize_question("危险\\\\废物"), "危险废物")

print()
print("=== 3. 不该动的东西（反向断言：剥太狠就是坏的）===")
check("中文汉字保留", normalize_question("危险废物"), "危险废物")
check("英文保留", normalize_question("GB18597"), "gb18597")          # 小写归一
check("数字保留", normalize_question("2020年标准"), "2020年标准")
check("标准号里的连字符……", normalize_question("HJ 169-2018"), "hj1692018")
check("下划线保留", normalize_question("a_b"), "a_b")
check("百分号被剥", normalize_question("50%的去除率"), "50的去除率")

print()
print("=== 4. 全角数字/字母不该被误伤 ===")
check("全角字母保留", normalize_question("ＧＢ标准"), "ｇｂ标准")
check("全角数字保留", normalize_question("１２３"), "１２３")

print()
print("=== 5. 归一化的两个核心用途：去重与大小写 ===")
check("大小写归一", normalize_question("ABC"), normalize_question("abc"))
check("标点差异归一",
      normalize_question("危险废物？怎么管"),
      normalize_question("危险废物,怎么管"))
check("空白差异归一",
      normalize_question("危险 废物"),
      normalize_question(" 危险废物 "))
# 反向：内容不同的**不能**归一成一样（否则缓存会串味）
check("反向：不同问题不能归一相同",
      normalize_question("危险废物怎么管") == normalize_question("一般废物怎么管"),
      False)

print()
print("=== 6. 没有 SyntaxWarning（回归上一版的毛病）===")
import importlib
import py_compile
import tempfile
import os

p = os.path.join("_中间产物", "重构工作区", "xishu_pipeline", "resilience.py")
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    py_compile.compile(p, cfile=os.path.join(tempfile.gettempdir(), "chk.pyc"),
                       doraise=True)
    syn = [x for x in w if "SyntaxWarning" in str(x.category)]
if syn:
    print("  ★   编译 resilience.py 仍有 SyntaxWarning：")
    for x in syn:
        print("        ", x.message)
    bad.append("SyntaxWarning")
else:
    print("  OK   编译无 SyntaxWarning")
    ok += 1

print()
print("==== 通过 %d / 失败 %d ====" % (ok, len(bad)))
if bad:
    for b in bad:
        print("  失败：" + b)
    sys.exit(1)
