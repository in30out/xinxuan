"""recall.py —— 基于 TF-IDF + 余弦相似度的候选召回。

中文描述用 jieba 搜索模式分词；若 jieba 不可用则退化为字符 2-gram，
保证无第三方分词库时链路依然可用。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:  # pragma: no cover - 取决于环境
    import jieba
    HAS_JIEBA = True
except ImportError:  # pragma: no cover
    jieba = None
    HAS_JIEBA = False
def tokenize(text: str) -> str:
    """分词：jieba 搜索模式（中文）或字符 2-gram（降级方案）。

    空白片段（jieba 会把 "SOT-23-5" 切成 "sot" "-" "23" "-" "5" 之外的
    纯空格 token）会与 n-gram 的填充空格混同，产生 '  5' / '声 ' 这类
    噪声特征，稀释余弦相似度，故显式剔除。
    """
    text = str(text).lower()
    if HAS_JIEBA:
        return " ".join(t for t in jieba.cut_for_search(text) if t.strip())
    return " ".join(text[i:i + 2] for i in range(max(len(text) - 1, 1)))
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
class RecallIndex:
    """把芯片库建成 TF-IDF 索引，支持型号或自然语言查询。"""
    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True)
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
    def idf_of(self, token: str) -> float:
        """关键词的 IDF 权重：语料里越罕见越有区分度；库中未出现的视为更重要。"""
        idx = self.vectorizer.vocabulary_.get(token)
        if idx is None:
            return float(self.vectorizer.idf_.max()) * 1.5
        return float(self.vectorizer.idf_[idx])
    def recall(self, query_text: str, exclude: str = "", top_k: int = 20):
        """返回 [(行号, 相似度), ...]，按相似度降序，排除自身型号。"""
        qv = self.vectorizer.transform([tokenize(query_text)])
        sims = cosine_similarity(qv, self.matrix)[0]
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
    print("jieba:", HAS_JIEBA, "vocab:", len(idx.vectorizer.vocabulary_))
    print(idx.recall(d.at[0, "desc_text"], exclude=d.at[0, "part_no"], top_k=5))
