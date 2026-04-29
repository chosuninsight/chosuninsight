# RAG DB Restructure Notes

## Current Findings

- Total indexed chunks: 7,113
- Stores: origin 6,742, update 371
- Graduation-tagged chunks: 2,139
- Main graduation sources:
  - `졸업이수학점.json`: 307 chunks
  - `2026_1학기_수강가이드_추출.txt`: 87 chunks
  - `교내일반공지_2026.txt`: 87 chunks
  - `학사공지_2026.txt`: 86 chunks
  - `조선대학교학사안내.txt`: 61 chunks

The main failure mode was not prompt wording. Older graduation-credit chunks and newer policy chunks were mixed without structured recency metadata, so retrieval could surface stale cohorts such as `2018학년도 이후 입학생` ahead of the current policy.

## Target Metadata

Policy and time-sensitive documents should carry these fields:

- `source_type`: `academic_policy`, `notice`, `dynamic_info`, or `reference`
- `policy_type`: for policy records, for example `graduation_credits`
- `departments`: normalized department aliases found in the chunk
- `academic_year`: extracted academic year when present
- `effective_from`: display label such as `2025학년도`
- `admission_cohort`: cohort label such as `2025학년도 이후 입학생`
- `is_latest_candidate`: generated for policy chunks with current-year policy data
- `priority`: explicit ranking when a curated policy record exists

## Implemented Structure

- `backend/data/academic_policies.json` is the curated policy table for high-risk facts such as graduation credits.
- `backend/main.py` loads curated policy records and injects matching latest graduation-credit records ahead of legacy RAG chunks when no specific admission year is requested.
- `rag_pipeline.py` now derives `source_type`, `academic_year`, `effective_from`, `admission_cohort`, `departments`, and `is_latest_candidate` during chunking.
- `chosun_rag_data/academic_graduation_credits_2025.txt` stores the latest source text so rebuilds can index the 2025 graduation-credit policy.

## Rebuild Rule

After adding or changing structured source files, rebuild Chroma so the metadata lands in the DB:

```bash
docker compose run --rm backend python rebuild_chroma.py
docker compose restart backend
```

For production quality, the curated policy JSON should eventually be generated from a scraper/parser for the official academic guide page instead of being maintained by hand.
