# Phase 6 Step 4 — Opportunity Quality Design

Status: Read-only analysis implemented
SQLite schema: Version 3
Automatic email delivery: Disabled

## Objectives

Improve the identification and prioritization of technology
opportunities relevant to participants in the Philippines.

Target categories:

- Free professional certification exam vouchers
- Technology workshops, meetups, webinars, and events
- Hackathons and developer competitions

## Current Source Limitations

GitHub Blog and Python Insider provide general technology news.

They are not authoritative, dedicated directories of free
Philippine technology opportunities.

Adding sources requires validation of official ownership,
feed availability, access rules, relevance, and collection limits.

Do not enable unofficial scraping of protected websites.

## Current Quality Analysis

The analyzer:

- Produces explainable keyword hints
- Assigns low, medium, or high review priority
- Detects some equivalent HTTPS URLs
- Detects strongly similar titles across different sources
- Preserves all original SQLite records
- Does not verify price, deadlines, or Philippine eligibility
- Does not change review decisions or notification states

## Duplicate Detection Rules

Existing database uniqueness remains:

source_id + exact URL

Additional analysis may flag:

1. URLs differing only by selected tracking parameters
2. Strongly similar titles in the same category across sources

A duplicate finding is not sufficient to delete or merge rows.

Matching titles may refer to different events, cohorts,
locations, years, or registration periods.

URL canonicalization is a comparison heuristic, not proof
that URLs refer to the same real-world opportunity.

## Manual Verification Requirements

Before approval, a trusted reviewer must confirm:

- Official source and organizer identity
- Actual registration or application URL
- All fees and eligibility conditions
- Philippine participant eligibility
- Registration deadline in an explicit timezone
- Current availability
- Any quotas, restrictions, or geographic exclusions

Evidence must be linked to the relevant opportunity.

## Next Source Discovery Priorities

Evaluate official and permitted feeds or published APIs for:

- Certification provider promotions
- Philippine developer communities
- Philippine technology event organizers
- Official hackathon organizers
- Student and university developer programs

Each new source must be evaluated individually before being
added to the allowlist.

## Known Limitations

- Current RSS classification uses titles only
- Some relevant opportunities will be missed
- Some irrelevant announcements will still be flagged
- Quality hints do not establish verification
- Cross-source duplicate detection is advisory
- URL normalization can produce false matches
- Similarity thresholds require validation on real data
- No automatic canonical-ID assignment
- No automatic record merging
- No deadline extraction or expiry automation

## Preservation Rules

Do not modify existing opportunities during quality analysis.
Do not rewrite historical manual reviews.
Do not automatically requeue previously sent or uncertain jobs.
Do not enable scheduled reviewed-opportunity emails.

## Step 4 Boundary

This step adds a read-only analyzer and tests.

It does not change:

- SQLite schema
- Existing source configuration
- RSS collection behavior
- Opportunity storage behavior
- Review authorization
- Email delivery or GitHub Actions workflows