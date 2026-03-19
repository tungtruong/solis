#!/usr/bin/env python3
"""Chunk toan bo Thong tu 99 theo Cau truc Dieu/Khoan/Diem cho Hierarchical RAG.

Dau ra:
1) JSONL node phang de index vector
2) JSON tong hop cay cha-con + thong ke

Su dung:
    python scripts/chunk_tt99_hierarchical_rag.py
    python scripts/chunk_tt99_hierarchical_rag.py --input data/regulations/raw_tt99_full.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


CHAPTER_RE = re.compile(r"^\s*Chương\s+([IVXLC]+)\s*$", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^\s*Điều\s+(\d+[A-Za-z]?)\.\s*(.+?)\s*$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
POINT_RE = re.compile(r"^\s*([a-zđ])\)\s+(.+?)\s*$", re.IGNORECASE)
APPENDIX_START_RE = re.compile(r"^\s*(Phụ\s*lục|Phu\s*luc)\s+I\s*$", re.IGNORECASE)
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class Point:
    label: str
    text_lines: List[str] = field(default_factory=list)


@dataclass
class Clause:
    number: str
    head: str
    text_lines: List[str] = field(default_factory=list)
    points: List[Point] = field(default_factory=list)


@dataclass
class Article:
    number: str
    title: str
    chapter_code: Optional[str]
    chapter_title: Optional[str]
    lines: List[str] = field(default_factory=list)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_line(line: str) -> str:
    return line.strip().replace("\u00a0", " ")


def parse_articles(lines: Iterable[str]) -> List[Article]:
    current_chapter_code: Optional[str] = None
    current_chapter_title: Optional[str] = None
    current_article: Optional[Article] = None
    articles: List[Article] = []
    pending_chapter_title = False

    for raw in lines:
        line = clean_line(raw)
        if not line:
            continue

        m_ch = CHAPTER_RE.match(line)
        if m_ch:
            current_chapter_code = m_ch.group(1).upper()
            current_chapter_title = None
            pending_chapter_title = True
            continue

        if pending_chapter_title and current_chapter_code:
            # Dong ngay sau "Chuong ..." thuong la tieu de chuong.
            current_chapter_title = line
            pending_chapter_title = False
            continue

        m_article = ARTICLE_RE.match(line)
        if m_article:
            if current_article is not None:
                articles.append(current_article)
            current_article = Article(
                number=m_article.group(1),
                title=normalize_space(m_article.group(2)),
                chapter_code=current_chapter_code,
                chapter_title=current_chapter_title,
            )
            continue

        if current_article is not None:
            current_article.lines.append(line)

    if current_article is not None:
        articles.append(current_article)

    return articles


def trim_before_appendix(lines: List[str]) -> List[str]:
    """Lay phan than Thong tu, bo phan phu luc phia sau Dieu 31."""
    dieu_31_idx = -1
    for i, raw in enumerate(lines):
        if re.match(r"^\s*Điều\s+31\.\s*", clean_line(raw), re.IGNORECASE):
            dieu_31_idx = i
            break

    start_search = dieu_31_idx + 1 if dieu_31_idx >= 0 else 0
    for i in range(start_search, len(lines)):
        if APPENDIX_START_RE.match(clean_line(lines[i])):
            return lines[:i]

    return lines


def split_article_into_clauses(article_lines: List[str]) -> List[Clause]:
    clauses: List[Clause] = []
    current_clause: Optional[Clause] = None

    for line in article_lines:
        m_clause = CLAUSE_RE.match(line)
        if m_clause:
            if current_clause is not None:
                clauses.append(current_clause)
            current_clause = Clause(number=m_clause.group(1), head=normalize_space(m_clause.group(2)))
            continue

        if current_clause is None:
            # Truong hop dieu khong tach theo khoan: dua ve khoan mac dinh "0".
            current_clause = Clause(number="0", head="Nội dung điều")

        current_clause.text_lines.append(line)

    if current_clause is not None:
        clauses.append(current_clause)

    return clauses


def split_clause_into_points(clause: Clause) -> Clause:
    points: List[Point] = []
    current_point: Optional[Point] = None
    remaining_text: List[str] = []

    for line in clause.text_lines:
        m_point = POINT_RE.match(line)
        if m_point:
            if current_point is not None:
                points.append(current_point)
            current_point = Point(label=m_point.group(1).lower(), text_lines=[normalize_space(m_point.group(2))])
            continue

        if current_point is not None:
            current_point.text_lines.append(line)
        else:
            remaining_text.append(line)

    if current_point is not None:
        points.append(current_point)

    clause.text_lines = remaining_text
    clause.points = points
    return clause


def build_text_article(article: Article) -> str:
    header = f"Điều {article.number}. {article.title}"
    body = normalize_space(" ".join(article.lines))
    return normalize_space(f"{header} {body}")


def build_text_clause(article: Article, clause: Clause) -> str:
    head = f"Điều {article.number}. {article.title}"
    clause_head = f"Khoản {clause.number}. {clause.head}"
    body = normalize_space(" ".join(clause.text_lines))
    return normalize_space(f"{head} {clause_head} {body}")


def build_text_point(article: Article, clause: Clause, point: Point) -> str:
    head = f"Điều {article.number}. {article.title}"
    clause_head = f"Khoản {clause.number}. {clause.head}"
    point_head = f"Điểm {point.label}"
    body = normalize_space(" ".join(point.text_lines))
    return normalize_space(f"{head} {clause_head} {point_head}. {body}")


def attach_parent(node: TextNode, parent_id: Optional[str]) -> None:
    if not parent_id:
        return
    node.relationships[NodeRelationship.PARENT] = RelatedNodeInfo(node_id=parent_id)


def make_node(node_id: str, text: str, metadata: Dict[str, str], parent_id: Optional[str]) -> TextNode:
    node = TextNode(id_=node_id, text=text, metadata=metadata)
    attach_parent(node, parent_id)
    return node


def hash_embedding(text: str, dim: int) -> List[float]:
    """Tao embedding co dinh tu van ban de upsert Qdrant khong phu thuoc model ngoai."""
    vec = [0.0] * dim
    for tok in TOKEN_RE.findall(text.lower()):
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def upsert_nodes_to_qdrant(
    nodes: List[TextNode],
    collection_name: str,
    dim: int,
    batch_size: int,
    qdrant_path: Optional[str],
    qdrant_url: Optional[str],
    qdrant_api_key: Optional[str],
) -> str:
    if qdrant_path:
        client = QdrantClient(path=qdrant_path)
        destination = f"local:{qdrant_path}"
    else:
        client = QdrantClient(url=qdrant_url or "http://localhost:6333", api_key=qdrant_api_key)
        destination = qdrant_url or "http://localhost:6333"

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    points: List[PointStruct] = []
    for node in nodes:
        parent_id = (
            node.relationships.get(NodeRelationship.PARENT).node_id
            if NodeRelationship.PARENT in node.relationships
            else None
        )
        payload = {
            "node_id": node.node_id,
            "text": node.get_content(),
            "parent_id": parent_id,
            "metadata": node.metadata,
            "level": node.metadata.get("level"),
            "article": node.metadata.get("article"),
            "clause": node.metadata.get("clause"),
            "point": node.metadata.get("point"),
            "chapter": node.metadata.get("chapter"),
        }
        vector = hash_embedding(payload["text"], dim=dim)
        point_id = int.from_bytes(hashlib.md5(node.node_id.encode("utf-8")).digest()[:8], "little") & ((1 << 63) - 1)
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=collection_name, points=points[i : i + batch_size], wait=True)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk TT99 theo Điều/Khoản/Điểm bằng LlamaIndex")
    parser.add_argument(
        "--input",
        default="data/regulations/raw_tt99_full.txt",
        help="Đường dẫn file text TT99 nguồn",
    )
    parser.add_argument(
        "--out-jsonl",
        default="data/regulations/tt99_2025_hierarchical_rag_nodes.jsonl",
        help="Đường dẫn file JSONL node đầu ra",
    )
    parser.add_argument(
        "--out-index",
        default="data/regulations/tt99_2025_hierarchy_index.json",
        help="Đường dẫn file JSON cây chỉ mục đầu ra",
    )
    parser.add_argument(
        "--keep-appendix",
        action="store_true",
        help="Giữ lại phần phụ lục thay vì cắt sau Điều 31",
    )
    parser.add_argument(
        "--qdrant-collection",
        default="tt99_2025_hierarchical_rag",
        help="Tên collection Qdrant để upsert node",
    )
    parser.add_argument(
        "--qdrant-path",
        default="data/qdrant",
        help="Path Qdrant local mode (ưu tiên nếu có)",
    )
    parser.add_argument(
        "--qdrant-url",
        default="",
        help="URL Qdrant server nếu không dùng local mode, ví dụ http://localhost:6333",
    )
    parser.add_argument(
        "--qdrant-api-key",
        default="",
        help="API key Qdrant (nếu dùng server có xác thực)",
    )
    parser.add_argument(
        "--vector-size",
        type=int,
        default=384,
        help="Kích thước vector upsert vào Qdrant",
    )
    parser.add_argument(
        "--qdrant-batch-size",
        type=int,
        default=128,
        help="Kích thước batch upsert Qdrant",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Không upsert vào Qdrant",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    out_jsonl_path = Path(args.out_jsonl)
    out_index_path = Path(args.out_index)

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    raw_text = input_path.read_text(encoding="utf-8", errors="ignore")
    lines = raw_text.splitlines()
    if not args.keep_appendix:
        lines = trim_before_appendix(lines)

    articles = parse_articles(lines)
    if not articles:
        raise RuntimeError("Không parse được Điều nào từ file nguồn.")

    out_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    out_index_path.parent.mkdir(parents=True, exist_ok=True)

    nodes: List[TextNode] = []
    hierarchy: Dict[str, object] = {
        "document": "Thông tư 99/2025/TT-BTC",
        "source_file": str(input_path).replace("\\", "/"),
        "levels": ["article", "clause", "point"],
        "articles": [],
    }

    for article in articles:
        article_id = f"tt99_dieu_{article.number}"
        article_text = build_text_article(article)
        article_meta = {
            "document": "TT99/2025/TT-BTC",
            "level": "article",
            "article": article.number,
            "article_title": article.title,
            "chapter": article.chapter_code or "",
            "chapter_title": article.chapter_title or "",
        }
        article_node = make_node(article_id, article_text, article_meta, parent_id=None)
        nodes.append(article_node)

        clause_list = [split_clause_into_points(c) for c in split_article_into_clauses(article.lines)]
        article_item = {
            "article_id": article_id,
            "article": article.number,
            "title": article.title,
            "chapter": article.chapter_code,
            "chapter_title": article.chapter_title,
            "clauses": [],
        }

        for clause in clause_list:
            clause_id = f"{article_id}_khoan_{clause.number}"
            clause_text = build_text_clause(article, clause)
            clause_meta = {
                "document": "TT99/2025/TT-BTC",
                "level": "clause",
                "article": article.number,
                "article_title": article.title,
                "clause": clause.number,
                "clause_head": clause.head,
                "chapter": article.chapter_code or "",
                "chapter_title": article.chapter_title or "",
            }
            clause_node = make_node(clause_id, clause_text, clause_meta, parent_id=article_id)
            nodes.append(clause_node)

            clause_item = {
                "clause_id": clause_id,
                "clause": clause.number,
                "clause_head": clause.head,
                "points": [],
            }

            for point in clause.points:
                point_id = f"{clause_id}_diem_{point.label}"
                point_text = build_text_point(article, clause, point)
                point_meta = {
                    "document": "TT99/2025/TT-BTC",
                    "level": "point",
                    "article": article.number,
                    "article_title": article.title,
                    "clause": clause.number,
                    "clause_head": clause.head,
                    "point": point.label,
                    "chapter": article.chapter_code or "",
                    "chapter_title": article.chapter_title or "",
                }
                point_node = make_node(point_id, point_text, point_meta, parent_id=clause_id)
                nodes.append(point_node)
                clause_item["points"].append({"point_id": point_id, "point": point.label})

            article_item["clauses"].append(clause_item)

        hierarchy["articles"].append(article_item)

    with out_jsonl_path.open("w", encoding="utf-8") as f:
        for node in nodes:
            record = {
                "node_id": node.node_id,
                "text": node.get_content(),
                "metadata": node.metadata,
                "parent_id": node.relationships.get(NodeRelationship.PARENT).node_id
                if NodeRelationship.PARENT in node.relationships
                else None,
                "llamaindex": node.to_dict(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    hierarchy["stats"] = {
        "total_articles": len([n for n in nodes if n.metadata.get("level") == "article"]),
        "total_clauses": len([n for n in nodes if n.metadata.get("level") == "clause"]),
        "total_points": len([n for n in nodes if n.metadata.get("level") == "point"]),
        "total_nodes": len(nodes),
    }

    out_index_path.write_text(json.dumps(hierarchy, ensure_ascii=False, indent=2), encoding="utf-8")

    qdrant_destination = None
    if not args.skip_qdrant:
        qdrant_destination = upsert_nodes_to_qdrant(
            nodes=nodes,
            collection_name=args.qdrant_collection,
            dim=args.vector_size,
            batch_size=args.qdrant_batch_size,
            qdrant_path=args.qdrant_path.strip() or None,
            qdrant_url=args.qdrant_url.strip() or None,
            qdrant_api_key=args.qdrant_api_key.strip() or None,
        )

    print("Hoàn tất chunk TT99 cho Hierarchical RAG")
    print(f"- Input: {input_path}")
    print(f"- JSONL nodes: {out_jsonl_path}")
    print(f"- Hierarchy index: {out_index_path}")
    print(f"- Tổng node: {hierarchy['stats']['total_nodes']}")
    if qdrant_destination:
        print(f"- Qdrant destination: {qdrant_destination}")
        print(f"- Qdrant collection: {args.qdrant_collection}")


if __name__ == "__main__":
    main()
