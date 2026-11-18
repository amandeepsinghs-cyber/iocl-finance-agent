"""Vertex AI Policy Search and Rulebooks RAG Engine for Yukti AI.
Queries Vertex AI Search engine 'hrfin-doc-search-engine' (location: global)
and falls back to rulebooks_clause_index.csv and hrfin_docs.silver_chunks.
"""

import csv
import logging
import os
import time
from typing import Any, Dict, List, Optional
from google.cloud import discoveryengine_v1 as discoveryengine

from app.config import (
    GCP_PROJECT,
    RULEBOOKS_CSV_PATH,
    VERTEX_SEARCH_ENGINE,
    VERTEX_SEARCH_LOCATION,
)

logger = logging.getLogger("yukti.tools.policy_search")


DOC_HUMAN_TITLES = {
    "IOCL-DOA": "IOCL Delegation of Financial Powers (DoA)",
    "IOCL-HEDGING": "IOCL Commodity & Forex Risk Management Policy",
    "IOCL-ACCT": "IOCL Ind AS Statutory Accounting Policies (Annual Report)",
    "IOCL-CAPALLOC": "IOCL Capital Allocation, Stage-Gate Capex & Dividend Policy",
    "IOCL-MOU": "IOCL Maharatna DPE / MoPNG MoU Governance Framework",
    "DOA": "IOCL Delegation of Financial Powers (DoA)",
    "HEDGING": "IOCL Commodity & Forex Risk Management Policy",
}


def get_human_doc_title(doc_id: str) -> str:
    clean = doc_id.strip()
    return DOC_HUMAN_TITLES.get(clean, DOC_HUMAN_TITLES.get(clean.upper(), clean))


class PolicySearchEngine:
    """Handles semantic retrieval of official IOCL finance, governance, hedging, and accounting policies."""

    def __init__(
        self,
        project_id: str = GCP_PROJECT,
        location: str = VERTEX_SEARCH_LOCATION,
        engine_id: str = VERTEX_SEARCH_ENGINE,
    ):
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self._search_client: Optional[discoveryengine.SearchServiceClient] = None
        self._local_index: Optional[List[Dict[str, Any]]] = None

    @property
    def client(self) -> discoveryengine.SearchServiceClient:
        if self._search_client is None:
            self._search_client = discoveryengine.SearchServiceClient()
        return self._search_client

    def _load_local_csv(self) -> List[Dict[str, Any]]:
        if self._local_index is not None:
            return self._local_index
        items = []
        if RULEBOOKS_CSV_PATH.exists():
            with open(RULEBOOKS_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    items.append({
                        "doc_id": row.get("doc_id", "IOCL Policy Rulebook"),
                        "clause_ref": row.get("clause_ref", ""),
                        "clause_title": row.get("clause_title", ""),
                        "clause_text": row.get("clause_text", ""),
                        "maps_to_question_ids": row.get("maps_to_question_ids", ""),
                        "source_basis": row.get("source_basis", ""),
                        # P0.7 (BUG-31, D-35): "illustrative" unless the CSV marks the row "real"
                        "provenance": "real" if (row.get("provenance") or "").strip() == "real" else "illustrative",
                    })
        from pathlib import Path
        import json
        _here = Path(__file__).resolve()
        _roots = [_here.parents[idx] for idx in (4, 3, 5) if len(_here.parents) > idx]
        fin_corpus = next((r / "financial_ssot" / "out" / "doc_chunks_ar.jsonl" for r in _roots if (r / "financial_ssot" / "out" / "doc_chunks_ar.jsonl").exists()), None)
        if fin_corpus is not None:
            with open(fin_corpus, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = json.loads(line)
                    items.append({
                        "doc_id": f"IOCL Annual Report ({c.get('fiscal_year', 'FY17–FY26')})",
                        "clause_ref": str(c.get("note_no") or c.get("citation") or "AR"),
                        "clause_title": c.get("heading") or "",
                        "clause_text": c.get("text") or "",
                        "maps_to_question_ids": ",".join(c.get("line_codes") or []),
                        "source_basis": c.get("source_doc") or "AR",
                        "provenance": "real",
                    })
        notes_corpus = next((r / "financial_build" / "data" / "financial_notes_corpus.jsonl" for r in _roots if (r / "financial_build" / "data" / "financial_notes_corpus.jsonl").exists()), None)
        if notes_corpus is not None:
            with open(notes_corpus, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = json.loads(line)
                    items.append({
                        "doc_id": f"IOCL Notes ({c.get('fy', 'FY17–FY26')})",
                        "clause_ref": str(c.get("note_ref") or "AR Note"),
                        "clause_title": c.get("title") or "",
                        "clause_text": c.get("content") or "",
                        "maps_to_question_ids": ",".join(c.get("line_codes") or []),
                        "source_basis": c.get("source_citation") or "AR",
                        "provenance": "real",
                    })
        self._local_index = items
        return items

    def search_local(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Performs keyword and semantic matching on local rulebooks clause index."""
        items = self._load_local_csv()
        if not items:
            return []

        import re
        q_lower = query.lower()
        q_terms = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2 and t not in ("how", "many", "are", "there", "what", "the", "about", "policy", "rules", "rule", "one", "year", "for", "and", "can", "you", "tell")]
        scored = []

        # High-precision topic boost rules so specific DoA / Treasury / Accounting / MoU inquiries hit exact clauses
        topic_boosts = [
            (["crude cargo", "spot crude", "vlcc", "aframax", "term crude", "crude oil procurement"], "iocl-doa", "2.1", 25),
            (["shipping", "charter", "vessel lease", "worldscale"], "iocl-doa", "2.2", 25),
            (["turnaround", "m&i", "maintenance shutdown", "catalyst"], "iocl-doa", "3.1", 25),
            (["maharatna", "brownfield", "5,000 cr", "5000 cr", "joint venture"], "iocl-doa", "3.2", 22),
            (["functional director", "cmd", "chairman", "emergency"], "iocl-doa", "4.0", 22),
            (["split", "associate finance", "concurrence", "technical sanction"], "iocl-doa", "5.0", 24),
            (["board finance", "audit committee", "ncd", "reserved"], "iocl-doa", "6.0", 22),
            (["confidential", "unpublished", "board draft", "draft pack", "bid tabulation"], "iocl-doa", "8.0", 25),
            (["cargo-in-transit", "unpriced crude", "put-spread"], "iocl-hedging", "2.0", 25),
            (["crack-spread", "crack spread", "gasoil", "gasoline", "crack", "25% to 35%"], "iocl-hedging", "3.0", 25),
            (["inventory price protection", "contango", "nrv write-down"], "iocl-hedging", "4.0", 25),
            (["usd/inr", "forex", "forward cover", "ecb", "ccirs", "buyer's credit"], "iocl-hedging", "5.0", 25),
            (["speculative", "naked derivative", "fema"], "iocl-hedging", "6.0", 25),
            (["isda", "counterparty credit", "counterparty exposure"], "iocl-hedging", "7.0", 25),
            (["ind as 109", "hedge accounting", "oci"], "iocl-hedging", "8.0", 22),
            (["excise duty", "gross revenue", "net revenue", "ind as 115", "note 28"], "iocl-acct", "note 1 & 28", 25),
            (["fifo", "nrv", "note 11"], "iocl-acct", "note 1 & 11", 22),
            (["ind as 116", "lease liability", "note 19a", "rou"], "iocl-acct", "note 1 & 19a", 25),
            (["115baa", "tax rate", "25.168", "note 35"], "iocl-acct", "note 35", 25),
            (["ind as 108", "operating segment"], "iocl-acct", "ind as 108", 25),
            (["consolidat", "cpcl", "lanka ioc", "hurl", "petronet"], "iocl-acct", "note 4 & 40", 22),
            (["lpg deposit", "security deposit", "lpg grant", "10,801"], "iocl-acct", "note 24-25", 25),
            (["hurdle rate", "equity irr", "12%", "stage-gate"], "iocl-capalloc", "1.0", 25),
            (["panipat p-25", "koyali", "barauni", "capex overrun"], "iocl-capalloc", "2.0", 22),
            (["dividend payout", "dipam", "30%", "bonus"], "iocl-capalloc", "3.0", 22),
            (["d/e", "debt-to-equity", "leverage", "aaa rating"], "iocl-capalloc", "4.0", 22),
            (["net-zero", "net zero", "2046", "green hydrogen", "solar"], "iocl-capalloc", "5.0", 22),
            (["dio", "working capital", "wcdl", "commercial paper"], "iocl-capalloc", "6.0", 22),
            (["mou", "maharatna mou", "dpe", "scorecard", "excellent"], "iocl-mou", "", 18),
            (["mbn", "energy intensity", "distillate yield", "fuel & loss"], "iocl-mou", "3.0", 22),
            (["gem", "msme", "mse", "treds"], "iocl-mou", "4.0", 24),
        ]

        for item in items:
            doc_l = item["doc_id"].lower()
            ref_l = item["clause_ref"].lower()
            title_l = item.get("clause_title", "").lower()
            text_l = item.get("clause_text", "").lower()
            haystack = f"{doc_l} {ref_l} {title_l} {text_l}"
            score = 0
            for term in q_terms:
                if term in title_l:
                    score += 4
                elif term in haystack:
                    score += 1

            for phrases, target_doc, target_ref, boost in topic_boosts:
                if any(p in q_lower for p in phrases):
                    if target_doc in doc_l and (not target_ref or target_ref in ref_l):
                        score += boost

            # Domain boosts
            if ("doa" in q_lower or "delegation" in q_lower or "sanction" in q_lower or "approval" in q_lower or "tender" in q_lower) and "iocl-doa" in doc_l:
                score += 6
            if ("hedg" in q_lower or "forex" in q_lower or "fx" in q_lower or "swap" in q_lower or "collar" in q_lower or "crack" in q_lower) and "iocl-hedging" in doc_l:
                score += 6
            if ("accounting" in q_lower or "ind as" in q_lower or "excise" in q_lower or "note" in q_lower) and "iocl-acct" in doc_l:
                score += 6
            if ("capex" in q_lower or "irr" in q_lower or "dividend" in q_lower or "leverage" in q_lower) and "iocl-capalloc" in doc_l:
                score += 6
            if ("mou" in q_lower or "scorecard" in q_lower) and "iocl-mou" in doc_l:
                score += 6

            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, item in scored[:top_k]:
            h_doc = get_human_doc_title(item["doc_id"])
            c_title = item.get("clause_title", "")
            full_title = f"{h_doc} — {item['clause_ref']}: {c_title}" if c_title else f"{h_doc} — {item['clause_ref']}"
            results.append({
                "doc_id": h_doc,
                "doc_title": full_title,
                "clause_ref": item["clause_ref"],
                "text": item["clause_text"],
                "highlight": item["clause_text"][:320] + ("..." if len(item["clause_text"]) > 320 else ""),
                "score": score,
                "provenance": item.get("provenance", "illustrative"),  # P0.7
            })
        return results

    def _search_bq_ar_and_notes(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Query BigQuery `hrfin_docs.doc_chunks_ar` and `hrfin_docs.financial_notes_chunks` / `rulebooks_clauses`."""
        clauses: List[Dict[str, Any]] = []
        try:
            from app.knowledge.ar_retriever import ARRetriever

            ar_rows = ARRetriever().retrieve(query, top_k=top_k)
            for r in ar_rows[:top_k]:
                fy = r.get("fiscal_year") or "FY26"
                pg = r.get("source_page_label") or r.get("source_page") or ""
                note_lbl = r.get("note_no") or (f"p.{pg}" if pg else "Annual Report")
                txt = str(r.get("text") or "").strip()
                clauses.append({
                    "doc_id": r.get("source_doc") or f"IOCL Annual Report {fy}",
                    "doc_title": f"IOCL Annual Report {fy} ({r.get('citation') or f'p.{pg}'}) — {r.get('heading') or note_lbl}",
                    "clause_ref": r.get("citation") or str(note_lbl),
                    "text": txt,
                    "highlight": txt[:320] + ("..." if len(txt) > 320 else ""),
                    "score": 8.0,
                    "provenance": "real",
                })
        except Exception as e:
            logger.info(f"BigQuery ARRetriever unavailable in policy_search ({type(e).__name__}: {e})")
        if clauses:
            return clauses

        try:
            import re as _re
            from google.cloud import bigquery
            from app.config import BQ_LOCATION, JOB_LABELS

            terms = [t.lower() for t in _re.findall(r"[a-zA-Z0-9]{3,}", query or "")][:6]
            if not terms:
                return []
            bq = bigquery.Client(project=self.project_id, location=BQ_LOCATION)
            sql = f"""
            SELECT doc_id, clause_ref, clause_title, clause_text, COALESCE(provenance, 'illustrative') AS provenance
            FROM `{self.project_id}.hrfin_docs.rulebooks_clauses`
            WHERE EXISTS(
              SELECT 1 FROM UNNEST(@terms) AS term
              WHERE LOWER(CONCAT(COALESCE(clause_title,''), ' ', COALESCE(clause_text,''))) LIKE CONCAT('%', term, '%')
            )
            LIMIT @lim
            """
            cfg = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("terms", "STRING", terms),
                    bigquery.ScalarQueryParameter("lim", "INT64", int(top_k)),
                ],
                labels=dict(JOB_LABELS),
            )
            for r in bq.query(sql, job_config=cfg).result():
                h_doc = get_human_doc_title(r["doc_id"])
                txt = str(r["clause_text"] or "")
                clauses.append({
                    "doc_id": h_doc,
                    "doc_title": f"{h_doc} — {r['clause_ref']}: {r['clause_title']}",
                    "clause_ref": r["clause_ref"],
                    "text": txt,
                    "highlight": txt[:320] + ("..." if len(txt) > 320 else ""),
                    "score": 6.0,
                    "provenance": r.get("provenance") or "illustrative",
                })
        except Exception as e:
            logger.info(f"BigQuery rulebooks_clauses query skipped ({type(e).__name__}: {e})")
        return clauses

    def search(self, query: str, top_k: int = 3, persona: str = "CMD") -> Dict[str, Any]:
        """Queries curated local IOCL rulebooks index, BigQuery AR chunks, and Vertex AI Search."""
        t0 = time.perf_counter()
        local_clauses = self.search_local(query, top_k=top_k)
        if local_clauses and local_clauses[0].get("score", 0) >= 6:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "status": "success",
                "source": "local_rulebooks_index",
                "query": query,
                "latency_ms": elapsed_ms,
                "clauses": local_clauses,
                "primary_clause": local_clauses[0],
            }

        source = "vertex_ai_search"
        clauses: List[Dict[str, Any]] = []

        try:
            serving_config = (
                f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/"
                f"engines/{self.engine_id}/servingConfigs/default_config"
            )
            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=top_k,
            )
            response = self.client.search(request)
            for res in response.results:
                doc = res.document
                struct = getattr(doc, "struct_data", {}) or {}
                clause_ref = struct.get("clause_ref", "Clause Reference")
                doc_title = struct.get("heading", struct.get("title", "IOCL Finance Policy"))
                doc_id = struct.get("doc_id", "IOCL-DOA")
                text = struct.get("text", struct.get("snippet", ""))

                if not text:
                    # Enrich from local if empty
                    local_match = self.search_local(f"{doc_id} {clause_ref}", top_k=1)
                    if local_match:
                        text = local_match[0]["text"]

                h_doc = get_human_doc_title(doc_id)
                full_title = f"{h_doc} — {clause_ref}: {doc_title}" if doc_title else f"{h_doc} — {clause_ref}"
                prov_match = self.search_local(f"{doc_id} {clause_ref}", top_k=1)
                clauses.append({
                    "doc_id": h_doc,
                    "doc_title": full_title,
                    "clause_ref": clause_ref,
                    "text": text,
                    "highlight": text[:300] + ("..." if len(text) > 300 else ""),
                    # P0.7: same provenance as the matching index row; unknown -> illustrative
                    "provenance": prov_match[0].get("provenance", "illustrative") if prov_match else "illustrative",
                })
        except Exception as e:
            logger.warning(f"Vertex AI Search failed ({e}); querying BigQuery AR & local rulebooks index.")
            clauses = self._search_bq_ar_and_notes(query, top_k=top_k)
            if clauses:
                source = "bigquery_ar_retriever"
            else:
                source = "local_rulebooks_index"
                clauses = local_clauses

        if not clauses:
            bq_clauses = self._search_bq_ar_and_notes(query, top_k=top_k)
            if bq_clauses:
                source = "bigquery_ar_retriever"
                clauses = bq_clauses
            elif local_clauses:
                source = "local_rulebooks_index"
                clauses = local_clauses

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        primary_clause = clauses[0] if clauses else None

        out = {
            "status": "success",
            "source": source,
            "query": query,
            "latency_ms": elapsed_ms,
            "clauses": clauses,
            "primary_clause": primary_clause,
        }
        from app.config import YUKTI_RESULT_CACHE
        from app.tool_cache import get_tool_cache
        if YUKTI_RESULT_CACHE:
            get_tool_cache().set_policy(query, persona, out)
        return out

    async def search_async(self, query: str, top_k: int = 3, persona: str = "CMD") -> Dict[str, Any]:
        """Non-blocking async wrapper for policy search (H1.1)."""
        import asyncio
        return await asyncio.to_thread(self.search, query=query, top_k=top_k, persona=persona)
