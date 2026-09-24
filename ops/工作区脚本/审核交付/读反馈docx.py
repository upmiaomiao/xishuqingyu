# -*- coding: utf-8 -*-
"""把用户反馈的 docx 正文打印出来（含表格），按原文顺序。"""
import sys
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def walk(doc):
    """按文档顺序产出段落与表格（python-docx 的 doc.paragraphs 不含表格内文字）。"""
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            yield Paragraph(child, doc)
        elif tag == 'tbl':
            yield Table(child, doc)


def main(path):
    d = Document(path)
    n_p = n_t = 0
    for blk in walk(d):
        if isinstance(blk, Paragraph):
            t = blk.text.strip()
            if t:
                n_p += 1
                print('[%s] %s' % (blk.style.name if blk.style else '', t))
        else:
            n_t += 1
            print('---- 表格 %d（%d 行 × %d 列）----' % (n_t, len(blk.rows), len(blk.columns)))
            for r in blk.rows:
                cells = [c.text.strip().replace('\n', ' / ') for c in r.cells]
                print('   | ' + ' | '.join(cells))
            print('---- 表格 %d 结束 ----' % n_t)
    print('\n段落 %d、表格 %d' % (n_p, n_t))


if __name__ == '__main__':
    main(sys.argv[1])
