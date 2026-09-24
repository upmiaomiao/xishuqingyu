# 索引构建溯源（meta 副本）

这里放的是各向量索引的 `meta.json` **副本**，只为留档"索引是怎么建出来的"：
构建时间、源索引、块数、嵌入配方、textclean 的 md5 等。

| 文件 | 对应线上路径 |
|---|---|
| `index.meta.json` | `/data/fagui_rag/index/meta.json`（主索引，356,018 块） |
| `index_v2.meta.json` | `/data/fagui_rag/index_v2/meta.json` |
| `index_stage.meta.json` | `/data/fagui_rag/index_stage/meta.json` |
| `index_eia_sample.meta.json` | `/data/fagui_rag/index_eia_sample/meta.json` |

**注意**：这些只是副本，别把它们拷回线上的索引目录 —— 索引本体（向量文件）不在仓库里，
体积太大（单个索引 2 GB 量级）。
