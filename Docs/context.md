# Project Context

## Overview

This project is a **research data-retrieval system** built for the **Google Photos vague-memory retrieval** initiative. The goal is to collect real-world evidence of users struggling to find old photos, videos, screenshots, or documents in their libraries due to imprecise or incomplete memories.

## Problem

People often remember having a photo or visual memory but cannot locate it because they lack precise details — such as the exact date, location, person's name, event, or content. Understanding how users describe these situations is key to improving photo-retrieval experiences.

## What the System Does (V0)

V0 is purely a **data-collection stage** — a research assistant that gathers evidence without attempting any analysis.

### Workflow

1. **Search**: Uses a configurable set of search queries (e.g., *"can't find old photo"*, *"looking for an old screenshot"*, *"remember a photo but can't find it"*) to find relevant conversations on **Reddit**.
2. **Collect**: Retrieves the Reddit posts along with their publicly available context.
3. **Deduplicate**: Ensures the same post is not stored multiple times when it appears across different searches.
4. **Structure**: Organizes collected data into a clean, structured dataset where each record retains:
   - The original conversation text
   - Source subreddit / platform
   - Date of the post
   - Direct link back to the original conversation

### What V0 Does **Not** Do

- Root-cause analysis
- Sentiment analysis
- Product recommendations
- Relevance classification

Its sole purpose is to answer:

> *"What are real people saying when they struggle to find something they remember having in their photo library?"*

## Future Direction (V1)

The dataset produced by V0 serves as the raw evidence pool for **V1**, where LLMs served via **Groq** (high-speed inference API) will be used to:

- Analyze conversations for patterns
- Identify what users remember vs. what they forget
- Understand how users search for memories
- Pinpoint where photo-retrieval systems break down

### Why Groq?

Groq is the designated LLM inference provider for this project. It offers ultra-fast inference for models like **Llama 3.3 70B** and **Mixtral 8x7B**. It will power all V1 analysis modules — including pattern recognition, memory classification, and search-behavior modelling — via the **Groq API**. V0 lays the groundwork by including Groq API configuration and dependencies so the transition to V1 is seamless.

## Data Sources & AI

- **Reddit** — publicly available posts and conversations (supports Dual-Mode: Keyless Public RSS feeds by default, and authenticated PRAW OAuth when credentials are provided)
- **Groq** — fast LLM inference API for V1 analysis (API configured in V0)

## Key Design Principles

| Principle            | Detail                                                                 |
| -------------------- | ---------------------------------------------------------------------- |
| **Traceability**     | Every record links back to the original Reddit conversation            |
| **Deduplication**    | No duplicate posts across different search queries                     |
| **Configurability**  | Search queries are configurable, not hard-coded                        |
| **No early analysis**| V0 collects only; analysis is deferred to V1                          |
| **Broad collection** | Cast a wide net to build a reliable, comprehensive evidence pool       |
