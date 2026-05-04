---
name: plant-json-identifier
description: Return strict plant-identification JSON from one to three local plant photos. Use when Gemini CLI or another agent must identify a plant for AI-Plantgraphy-style observation intake and must avoid prose, Markdown, tool chatter, or alternate schemas such as common_name, plant_name, or free-form summaries.
---

# Plant JSON Identifier

## Overview

Return one JSON object only.
Use the attached local images as the only source of truth.

## Workflow

1. Read one to three local images of the same plant observation.
2. Identify the most likely plant name from visible evidence only.
3. Return exactly the schema in [references/output-contract.md](references/output-contract.md).

## Rules

- Do not write explanations, Markdown, headings, bullets, or code fences.
- Do not inspect repo files, prompts, scripts, or surrounding workspace content unless the caller explicitly asks for that instead of identification.
- Do not invent extra keys.
- Prefer `common_name_ja` over alternate keys such as `common_name` or `plant_name`.
- If uncertain, keep the best candidate but lower `confidence`.
- If the image is unreadable, still return the required JSON and explain briefly in `uncertainty_notes`.

## Reference

- Read [references/output-contract.md](references/output-contract.md) before answering so the exact keys, limits, and failure behavior stay consistent.
