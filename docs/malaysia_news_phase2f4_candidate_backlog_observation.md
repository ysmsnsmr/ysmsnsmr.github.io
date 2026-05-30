# Phase 2F.4: RSS Candidate Backlog Observation Day1

Date: 2026-05-30
Status: Local-only backlog observation. Do not add these feeds to production or the Phase 2F.3A cleaned set.

## Summary

Phase 2F.4 observes additional RSS candidates before deciding whether any belong in a future cleaned candidate set. The goal is to check fetch stability, duplicates, life-impact fit, and noise using only RSS metadata:

- title
- description
- link
- published

No Groq, article body fetching, workflow changes, Pages changes, or production RSS changes are allowed.

## Backlog Candidates

| id | source | URL | initial concern |
| --- | --- | --- | --- |
| `malay_mail_world` | Malay Mail World | `https://www.malaymail.com/feed/rss/world` | likely world-news noise; may only matter when global events affect Malaysia daily life |
| `free_malaysia_today` | Free Malaysia Today | `https://www.freemalaysiatoday.com/feed/` | broad local-news candidate; may add politics and incident noise |
| `says_malaysia` | SAYS Malaysia | `https://says.com/my/rss` | possible lifestyle/public-interest value; may be soft-news heavy |
| `lowyat_net` | Lowyat.NET | `https://www.lowyat.net/feed/` | possible telco/device/payment value; likely gadget/review noise |
| `paul_tan` | Paul Tan | `https://paultan.org/feed/` | possible transport/vehicle-policy value; likely car-product noise |

## Manual Day1 Command

Run from the repository root:

```bash
python3.12 -B scripts/experiment_observe_rss_candidate_backlog.py --date 20260530
```

Default outputs:

- `/tmp/malaysia_rss_phase2f4/rss_candidate_backlog_20260530.json`
- `/tmp/malaysia_rss_phase2f4/rss_candidate_backlog_memo_20260530.md`
- `/tmp/malaysia_rss_phase2f4/observation_index.json`

The script also fetches the current cleaned `english_expansion_set` enabled feeds as a reference only, so it can count duplicate URLs against the cleaned set. It does not add backlog candidates to the cleaned set.

## What To Observe

Fetch stability:

- Does the feed parse as RSS?
- Are there bozo or error states?
- How many items are parsed under the per-feed limit?

Duplicates:

- Duplicate URLs within the backlog candidate set.
- Duplicate URLs against the cleaned set reference.

Life-impact fit:

- Weather, flood, road, transport, public services, MyKad, immigration, fuel, toll, payment, banking, scams, health, water, electricity, telco, or household cost signals.

Noise:

- World/geopolitics, politics-only, markets, generic gadget reviews, entertainment, sports, crime/court/incident, and product-catalogue content.

## Day1 Interpretation Rules

Do not promote any candidate after Day1 alone.

Possible follow-up directions:

- Keep for longer observation if it fetches cleanly and has repeated life-impact candidates.
- Keep as niche-only if it has a clear narrow value, such as transport or telco, but high general noise.
- Drop if it fails fetch/parse or mostly contributes noise.
- Re-test only with a narrower feed URL if the broad feed is too noisy.

## Not In Scope

- Editing `scripts/malaysia_rss_summary.py`.
- Editing `config/malaysia_news_feeds_phase2f.yml`.
- Editing GitHub Actions or Pages.
- Running Groq.
- Fetching article bodies.
- Storing daily snapshots in the repository.
