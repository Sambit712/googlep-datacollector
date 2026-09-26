# Project Context

## Overview

This project is a **research data-retrieval system** built for the **Google Photos vague-memory retrieval** initiative. The goal is to collect real-world evidence of users struggling to find old photos, videos, screenshots, or documents in their libraries due to imprecise or incomplete memories.

## Problem

People often remember having a photo or visual memory but cannot locate it because they lack precise details — such as the exact date, location, person's name, event, or content. Understanding how users describe these situations is key to improving photo-retrieval experiences.

## What the System Does (V0 — Evidence Collection)

V0 is purely a **data-collection stage** — a research assistant that gathers raw evidence without attempting any analysis.

### Workflow

1. **Search**: Uses a configurable set of search queries (e.g., *"can't find old photo"*, *"looking for an old screenshot"*, *"remember a photo but can't find it"*) to find relevant conversations on **Reddit**.
2. **Collect**: Retrieves the Reddit posts along with their publicly available context (titles, bodies, timestamps, and contextual comments).
3. **Deduplicate**: Ensures the same post is not stored multiple times when it appears across different searches, maintaining persistent IDs in `seen_ids.json`.
4. **Structure**: Organizes collected data into a clean, structured dataset where each record retains:
   - A unique research identifier (`record_id`, e.g., `RD_000001`)
   - The original conversation text (`raw_text` and `cleaned_text`)
   - Source subreddit and platform metadata
   - Date of the post and retrieval timestamps
   - Direct permalink back to the original Reddit conversation
   - Matched search queries and contextual comments

### What V0 Does **Not** Do

- Root-cause analysis
- Sentiment analysis
- Product recommendations
- Relevance classification or filtering

Its sole purpose is to answer:

> *"What are real people saying when they struggle to find something they remember having in their photo library?"*

---

## AI-Powered Research Analysis Engine (V1 — Evidence Analysis)

V1 transforms the raw V0 evidence into structured, evidence-backed research insights using the existing Groq LLM infrastructure and a configurable taxonomy.

### The Central Research Question

> **"Why does photo retrieval fail when users remember a photo or its context, but cannot precisely describe it to the search system?"**

### V0 → V1 Relationship: Two Connected Research Layers

V0 and V1 function as two complementary, decoupled research layers:

| Layer | Research Role | Guiding Question |
| ----- | ------------- | ---------------- |
| **V0 (Collection)** | Evidence Gathering | *What are users saying?* |
| **V1 (Analysis)**   | Evidence Interpretation | *What does that evidence tell us about the retrieval problem?* |

#### Core Invariant: Untouched V0 Source Data & Strict Traceability

- **The original V0 dataset must remain untouched.** V1 reads from V0 outputs as read-only inputs.
- Every V1 analysis record retains the original V0 `record_id`.
- This ensures an unbroken chain of evidence verification:

$$\text{Research Insight} \longrightarrow \text{V1 Analysis} \longrightarrow \text{V0 Record} \longrightarrow \text{Original Reddit Evidence} \longrightarrow \text{Source URL}$$

Traceability is critical: every insight, metric, and failure mode must be directly verifiable against actual user quotes and URLs rather than unsupported AI hallucinations.

### What V1 Identifies

For every piece of evidence in the V0 dataset, V1 determines:

1. **Relevance Classification**: Whether the post is genuinely relevant to the vague-memory retrieval problem.
2. **Memory Cues Retained**: What the user actually remembers (e.g., person, place, event, time/epoch, object, visual details, text in image, activity, ambient context).
3. **Target Media**: What the user is trying to retrieve (photo, screenshot, video, scanned document, receipt, meme, etc.).
4. **Retrieval Failure Point**: Where the retrieval process breaks (e.g., vocabulary mismatch, temporal fuzziness, missing metadata, visual semantic gap, overwhelming gallery volume).
5. **Friction Experienced**: Frustration, time wasted, cognitive overload, anxiety over lost memories.
6. **User Workarounds**: What users resort to when search fails (e.g., endless manual scrolling, asking friends/family, reverse image search, external social media backups, keyword guessing).
7. **Desired Outcome**: What the user was ultimately attempting to accomplish.
8. **Recurring Patterns**: Which problems, cue gaps, and failure points recur across multiple users and demographics.

### Expected V1 Progression

V1 systematically moves research understanding through six progressive tiers:

```
Raw Conversation (V0)
   └── Relevant Evidence Filtered
         └── Memory Cues Extracted
               └── Retrieval Failure Classified
                     └── User Workarounds Identified
                           └── Recurring Patterns Synthesized
                                 └── Evidence-Backed Product Problem Defined
```

### What V1 Should NOT Build Yet (Strict Boundaries)

The objective of V1 is **not to design the solution or build an MVP**. Its objective is to convert unstructured user evidence into a reliable, quantitative understanding of the problem.

To avoid premature complexity, V1 explicitly does **not** include:
- Vector databases (Pinecone, Chroma, Qdrant, etc.)
- Embeddings generation
- Retrieval-Augmented Generation (RAG)
- Orchestration frameworks like LangChain or LangGraph
- Streamlit or web dashboards
- Google Photos API integration
- AI query expansion or search engine prototypes
- Product feature recommendations or solution MVPs

*Guiding Principle*: **V0 collects the evidence. V1 interprets the evidence. V2 uses those insights to build and test the product solution.**

---

## Data Sources & AI Infrastructure

- **Reddit**: Publicly available posts and conversations (supports Dual-Mode: Keyless Public RSS feeds by default, and authenticated PRAW OAuth when credentials are provided).
- **Groq API**: High-speed LLM inference provider (serving `llama-3.3-70b-versatile` and other models) configured via the official `groq` SDK for high-throughput, structured extraction and classification.
- **Configurable Taxonomy**: `config/taxonomy.yaml` externalizes research categories so classifications can evolve organically as empirical findings emerge.
- **Data Processing**: Pandas / Python standard data processing for statistical aggregation, pattern frequency tabulation, and cross-category comparisons.
- **File-Based Storage**:
  - `data/output/reddit_evidence.json` & `.csv` (V0 source evidence)
  - `data/output/collection_report.json` (V0 metrics)
  - `data/output/analyzed_evidence.json` & `.csv` (V1 analyzed records with V0 `record_id`)
  - `data/output/insight_report.json` (V1 aggregated research insights & patterns)

---

## Key Design Principles

| Principle | Scope | Detail |
| --------- | ----- | ------ |
| **Traceability** | V0 + V1 | Every insight and analysis record links back through `record_id` to the original Reddit post URL. |
| **Immutability of Source Data** | V1 | V0 evidence datasets are strictly read-only; V1 outputs are written to separate analysis artifacts. |
| **Deduplication** | V0 | No duplicate posts across queries or runs; tracked via `seen_ids.json`. |
| **Configurability** | V0 + V1 | Search queries (`queries.yaml`) and research categories (`taxonomy.yaml`) are fully externalized in YAML. |
| **Strict Scoping (No Solutioneering)** | V1 | V1 focuses solely on understanding user memory and retrieval breakdown, deferring solutions to V2. |
| **Lightweight Tooling** | V0 + V1 | Python, Groq, Pandas, PyYAML, and file-based JSON/CSV — zero unnecessary database or framework overhead. |
| **Broad Collection → Rigorous Analysis** | V0 → V1 | V0 casts a wide net; V1 applies LLM-driven filtering and structured multi-dimensional taxonomy extraction. |

