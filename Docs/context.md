# Project Context

## Overview

This project is a **research data-retrieval system** built for the **Google Photos vague-memory retrieval** initiative. The goal is to collect real-world evidence of users struggling to find old photos, videos, screenshots, or documents in their libraries due to imprecise or incomplete memories.

## Problem & Cognitive-System Gap

People often remember a photograph through **fragments of context rather than precise searchable metadata**.

For example, a user may remember:
> *"There was a picture from my Goa trip, probably at a small café, and my friend was wearing a red shirt."*

The user retains multiple meaningful episodic attributes:
* Approximate location (e.g., Goa, beach, café)
* Person & relationship (e.g., "my friend", "my mother", "college roommate")
* Event (e.g., vacation trip, wedding, birthday)
* Visual appearance (e.g., red shirt, sunset, night scene)
* Activity (e.g., travelling, eating, celebration)
* Approximate time / epoch (e.g., summer 2022, during college)

However, these memories do not map directly to the metadata fields or interaction models available in conventional photo-search experiences. This creates a critical breakdown chain:

```text
How the user remembers the photo (human episodic memory fragments)
                ↓
How the user describes the photo (verbalization into search query)
                ↓
How the system interprets the description (natural language & intent matching)
                ↓
How the system retrieves candidates (narrowing the candidate library)
                ↓
How the user recognizes the correct photo (visual scanning & confirmation)
```

The system must investigate **where this chain breaks and why**.

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

> **"Why do users fail to retrieve a photo when they remember meaningful details about it but cannot precisely describe or search for it?"**

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

1. **Relevance Classification (Tri-State)**:
   - Classifies evidence as: **Relevant**, **Possibly Relevant**, or **Irrelevant**.
   - Filters out non-retrieval complaints (e.g., *"Google Photos keeps crashing"* is classified as **Irrelevant**; whereas *"I know I took this picture during my trip but I can't remember when, and I can't find it"* is directly **Relevant**).
2. **Memory Cue Extraction (Structure of Human Visual Memory)**:
   - Focuses on understanding the cognitive structure of human visual memory relevant to retrieval, rather than keyword extraction.
   - Categories extracted:
     - **Person**: Who appears in or is associated with the photo.
     - **Place**: Location context (e.g., Goa, beach, restaurant, college, home).
     - **Time**: Temporal epoch / lifecycle context (e.g., last year, during college, around Diwali, sometime in 2022, before moving).
     - **Event**: Occasion (e.g., vacation trip, birthday, wedding, concert, college event).
     - **Object**: Physical objects (e.g., car, document, medicine, food, product).
     - **Visual Details**: Perceptual features (e.g., red shirt, sunset, blue building, group photo, night lighting).
     - **Textual Details**: Information remembered from visible text in images (e.g., signboard, receipt, document, medicine name, restaurant name).
     - **Activity**: Actions / verbs (e.g., eating, travelling, studying, attending an event).
     - **Relationship**: Social bonds (e.g., "my friend", "my mother", "my old roommate").
3. **Retrieval Failure Classification (The 5-Stage Cognitive Breakdown)**:
   - Maps every relevant failure to the exact stage where retrieval breaks:
     - **Stage 1: Memory → Query** (`memory_to_query`): User remembers the photo but cannot convert that memory into useful search terms (*"I know what the picture looked like but I don't know what words to search"*). Research question: *Can users translate their memory into a searchable representation?*
     - **Stage 2: Query → System** (`query_to_system`): User provides a reasonable description, but the system fails to understand the natural contextual description (semantic gap, vocabulary mismatch). Research question: *Does the system understand the user's natural description?*
     - **Stage 3: System → Candidate** (`system_to_candidate`): System understands the query but cannot narrow the candidate space effectively (returns hundreds of unrelated images or zero results; volume overload). Research question: *Can the system narrow the search space effectively?*
     - **Stage 4: Candidate → Recognition** (`candidate_to_recognition`): Candidates are presented, but user struggles to recognize or distinguish the correct photo (flat chronological galleries, thumbnail overload, visual fatigue). Research question: *Does the result presentation help users identify the remembered item?*
     - **Stage 5: Search Refinement** (`search_refinement`): Initial search fails and the user lacks feedback or interaction controls to steer the search, resulting in abandonment or endless scrolling. Research question: *Can users iteratively steer retrieval when the initial attempt fails?*
4. **Target Media**: What the user is trying to retrieve (personal photo, screenshot, video clip, scanned document, receipt, meme, etc.).
5. **Friction Experienced**: Frustration, time wasted, cognitive overload, anxiety over lost memories, device storage anxiety.
6. **User Workarounds**: Coping behaviors (endless manual scrolling, asking friends/family, reverse image search, external social media backups, keyword guessing, abandonment).
7. **Desired Outcome**: What the user was ultimately attempting to accomplish (e.g., show photo to friend, reminisce, find a receipt for return).
8. **Recurring Patterns**: Which breakdown stages, cue gaps, and failure points recur across users.

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

