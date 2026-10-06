"""recall.py —— 基于 TF-IDF + 余弦相似度的候选召回。

中文描述用 jieba 搜索模式分词；若 jieba 不可用则退化为字符 2-gram，
保证无第三方分词库时链路依然可用。

向量化有两条等价路径（`vectorizer_kind()` 决定，可用环境变量 XINXUAN_VECTORIZER
强制指定）：
  * "sklearn" —— sklearn 的 TfidfVectorizer（开发态默认，功能最全）
  * "numpy"   —— 本文件内置的纯 numpy 实现，**公式与 sklearn 逐项对齐**
                 （sublinear TF = 1+ln(tf)、smooth IDF = ln((1+n)/(1+df))+1、
                  word 1-2gram、L2 归一化），因此召回顺序在演示数据上完全一致。
                 打包 .exe 时排除 scipy/sklearn 可让体积从约 200MB 降到约 40MB，
                 这条路径就是为此准备（见 build_exe.py 与 docs/refs/packaging-audit.md）。
"""
from __future__ import annotations

import math
import os
import re

import numpy as np
import pandas as pd

try:  # pragma: no cover - 取决于环境
    from sklearn.feature_extraction.text import TfidfVectorizer
    HAS_SKLEARN = True
except ImportError:  # pragma: no cover - 打包裁剪后走这里
    TfidfVectorizer = None
    HAS_SKLEARN = False

try:  # pragma: no cover - 取决于环境
    import jieba
    HAS_JIEBA = True
except ImportError:  # pragma: no cover
    jieba = None
    HAS_JIEBA = False

_WORD_RE = re.compile(r"[0-9a-z\u4e00-\u9fff]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list:
    """分词：jieba 搜索模式（中文）或字符 2-gram（降级方案）。返回 token 列表。

    三个必须做的清洗，前两个是实测踩出来的，第三个是**必须**的兼容性要求：

    1. 剔除空白 token —— jieba 会把 "SOT-23-5" 切出纯空格片段，与 n-gram 的
       连接空格混同，产生 '  5' / '声 ' 这类噪声特征，稀释余弦相似度。
    2. token 内部空白替换为下划线 —— jieba 会切出 "- m3"、"通用 型" 这类
       内部带空格的多字 token；TF-IDF 的 n-gram 是「用空格连接相邻 token」，
       若 token 自带空格，词表里就会出现 ' - m3' 这种"既是 unigram 又是
       bigram 拼接结果"的歧义特征。
    3. **返回值必须是 token 列表，不能是空格连接的字符串** —— 这是本节最隐蔽的
       坑：sklearn 的 TfidfVectorizer 在 `_word_ngrams` 里直接对 tokenizer 的
       返回值做 `original_tokens[i:i+n]` 切片再 `" ".join(...)`，它假定
       tokenizer 返回的是**可切片的序列**。若返回 str，切片会按**字符**进行，
       于是 1-2gram 实际退化成「单字符 + 相邻单字符拼接」，词表里全是
       's' / 't' / 'm' / '控制' 这类单字特征，整条 TF-IDF 召回的质量被严重
       低估（实测词表 1317 项里有 280 项是单字符/含空格的伪特征）。
       所以这里按 sklearn 的契约返回 list。
    """
    text = str(text).lower()
    if HAS_JIEBA:
        raw = jieba.cut_for_search(text)
    else:
        raw = (text[i:i + 2] for i in range(max(len(text) - 1, 1)))
    out = []
    for token in raw:
        token = "_".join(token.split())
        if not token:
            continue
        # 丢掉单字符 **ASCII** token（保留单个汉字）。
        # 1-2gram 修好之后 "STM32F103C8T6" 会同时产生 's','t','m','3','2','f','1','0','c','8','6'
        # 这十几个单字符特征，它们的 IDF 极高（在 89 行里几乎是独一份），于是
        # "哪个料号的字母数字碰巧最像"就主导了相似度，掩盖了 'LQFP48'/'Cortex-M3'/'64KB Flash'
        # 这类真正的功能特征。实测：剔除后 APM32F103C8T6 的相似度 0.2736，而
        # STC8H8K64U（封装引脚相同但内核不同）从 0.1728 升到 0.1852，排序更合理。
        # 单个汉字要保留：中文里 "光耦"/"运放" 的单字在库中出现频率差异很大，
        # 全部剔除会让 "便宜的 5V LDO SOT-23" 这类查询失去 5V 这个关键特征。
        if len(token) < 2 and not ("\u4e00" <= token <= "\u9fff"):
            continue
        out.append(token)
    return out


def expand_terms(base_query: str, terms, repeat: int = 2) -> str:
    """把品类同义词加权注入查询串（重复出现 => TF 权重提高），供 NL 查询使用。

    repeat 控制在 2：再高会让 "低功耗"/"ldo" 这类高频词的 IDF 优势盖过
    封装与电压约束（实测 repeat=3 时 AMS1117-3.3 反而排到 SOT-23-5 候选之前）。
    型号查询不调用本函数，因此型号替换链路的分词与排序完全不变。
    """
    extra = [str(t) for t in terms if str(t).strip()]
    if not extra:
        return base_query
    return base_query + " " + " ".join(extra * repeat)


def vectorizer_kind() -> str:
    """返回实际使用的向量化实现："sklearn" 或 "numpy"。"""
    forced = os.environ.get("XINXUAN_VECTORIZER", "").strip().lower()
    if forced in ("sklearn", "numpy"):
        return forced
    return "sklearn" if HAS_SKLEARN else "numpy"


# --------------------------------------------------------------------- numpy 实现
class _NumpyTfidf:
    """纯 numpy 的 TF-IDF（与 sklearn TfidfVectorizer 的关键参数对齐）。

    vocab：token -> 列号；每一行按「(1+ln tf) * idf」加权后做 L2 归一化。
    稠密矩阵：2 万行 × 数万列 = 数百 MB 内存，故用 float32；行内绝大多数是 0，
    内存可接受（演示数据 89 行只有几 MB）。
    """

    def __init__(self, ngram_range=(1, 2), sublinear_tf=True, smooth_idf=True):
        self.ngram_range = ngram_range
        self.sublinear_tf = sublinear_tf
        self.smooth_idf = smooth_idf
        self.vocabulary_: dict = {}
        self.idf_ = np.zeros(1, dtype=np.float32)

    def _grams(self, text: str) -> list:
        """复刻 sklearn 的 analyzer + _word_ngrams：先分词，再用空格连接相邻 token。"""
        toks = tokenize(text)
        lo, hi = self.ngram_range
        out = []
        for n in range(lo, hi + 1):
            if n == 1:
                out.extend(toks)
            else:
                out.extend(" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1))
        return out

    def fit_transform(self, corpus):
        docs = [self._grams(t) for t in corpus]
        n_docs = len(docs)
        vocab: dict = {}
        counts = []
        for grams in docs:
            row: dict = {}
            for g in grams:
                idx = vocab.get(g)
                if idx is None:
                    idx = len(vocab)
                    vocab[g] = idx
                row[idx] = row.get(idx, 0) + 1
            counts.append(row)
        self.vocabulary_ = vocab
        v = max(len(vocab), 1)
        matrix = np.zeros((n_docs, v), dtype=np.float32)
        for i, row in enumerate(counts):
            for idx, tf in row.items():
                matrix[i, idx] = 1.0 + math.log(tf) if self.sublinear_tf else float(tf)
        df = (matrix > 0).sum(axis=0).astype(np.float64)
        if self.smooth_idf:
            self.idf_ = (np.log((1.0 + n_docs) / (1.0 + df)) + 1.0).astype(np.float32)
        else:
            self.idf_ = (np.log(n_docs / np.maximum(df, 1.0)) + 1.0).astype(np.float32)
        matrix *= self.idf_[None, :]
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        np.divide(matrix, np.maximum(norms, 1e-12), out=matrix)
        return matrix

    def transform(self, texts) -> np.ndarray:
        """把查询串转成同一个向量空间里的稀疏矩阵（返回稠密 1×V）。"""
        v = max(len(self.vocabulary_), 1)
        out = np.zeros((len(texts), v), dtype=np.float32)
        for i, text in enumerate(texts):
            tf: dict = {}
            for g in self._grams(text):
                idx = self.vocabulary_.get(g)
                if idx is not None:
                    tf[idx] = tf.get(idx, 0) + 1
            for idx, count in tf.items():
                out[i, idx] = 1.0 + math.log(count) if self.sublinear_tf else float(count)
            out[i] *= self.idf_
            norm = float(np.linalg.norm(out[i]))
            if norm > 1e-12:
                out[i] /= norm
        return out


class RecallIndex:
    """把芯片库建成 TF-IDF 索引，支持型号或自然语言查询。"""

    def __init__(self, df: pd.DataFrame, kind: str = None):
        self.df = df.reset_index(drop=True)
        kind = kind or vectorizer_kind()
        self.kind = "sklearn" if (kind == "sklearn" and HAS_SKLEARN) else "numpy"
        if self.kind == "sklearn":
            self.vectorizer = TfidfVectorizer(
                analyzer="word",
                tokenizer=tokenize,
                token_pattern=None,
                lowercase=True,
                ngram_range=(1, 2),
                sublinear_tf=True,
                min_df=1,
            )
            self.matrix = self.vectorizer.fit_transform(self.df["desc_text"])
        else:
            self.vectorizer = _NumpyTfidf(ngram_range=(1, 2), sublinear_tf=True,
                                          smooth_idf=True)
            self.matrix = self.vectorizer.fit_transform(list(self.df["desc_text"]))

    def idf_of(self, token: str) -> float:
        """关键词的 IDF 权重：语料里越罕见越有区分度；库中未出现的视为更重要。"""
        idx = self.vectorizer.vocabulary_.get(token)
        if idx is None:
            return float(np.max(self.vectorizer.idf_)) * 1.5
        return float(self.vectorizer.idf_[idx])

    def recall(self, query_text: str, exclude: str = "", top_k: int = 20):
        """返回 [(行号, 相似度), ...]，按相似度降序，排除自身型号。

        注意：vectorizer 内部会调用 tokenize（自定义 tokenizer），所以这里**必须
        传原始字符串**，不能再自己 tokenize 一遍 —— tokenize 现在返回 list，
        再传进去会被 sklearn 的 preprocessor 当字符串处理而报
        `AttributeError: 'list' object has no attribute 'lower'`。
        """
        qv = self.vectorizer.transform([query_text])
        if self.kind == "sklearn":
            from sklearn.metrics.pairwise import cosine_similarity

            sims = np.asarray(cosine_similarity(qv, self.matrix)[0], dtype=np.float64)
        else:
            # 两侧都已 L2 归一化，点积即余弦；用矩阵乘法避免临时大数组
            sims = np.asarray(np.asarray(qv, dtype=np.float32) @ self.matrix.T,
                              dtype=np.float64).ravel()
        order = np.argsort(-sims)
        out = []
        for i in order:
            if float(sims[i]) <= 0:
                continue
            if exclude and self.df.at[i, "part_no"].upper() == exclude.upper():
                continue
            out.append((int(i), float(sims[i])))
            if len(out) >= top_k:
                break
        return out


if __name__ == "__main__":
    from data_loader import load_chips

    d = load_chips()
    idx = RecallIndex(d)
    print("jieba:", HAS_JIEBA, "sklearn:", HAS_SKLEARN, "kind:", idx.kind,
          "vocab:", len(idx.vectorizer.vocabulary_))
    print(idx.recall(d.at[0, "desc_text"], exclude=d.at[0, "part_no"], top_k=5))
