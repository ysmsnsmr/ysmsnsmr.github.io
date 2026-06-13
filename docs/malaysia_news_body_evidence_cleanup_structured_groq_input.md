# Body Evidence Cleanup And Structured Groq Input

Date: 2026-06-13
Status: Implemented for optional body enrichment and Groq input safety.

## Summary

This change improves the optional body enrichment path so article body text is not passed to Groq as raw excerpt text.

The body enrichment step now creates a cleaned body evidence layer. Groq receives that structured evidence only when the body policy is `use_body`.

RSS-rendered Markdown remains the fail-open fallback. Groq overwrite still depends on the existing guarded validator.

## Body Evidence Cleanup

For article-body candidates, the enrichment script now keeps the raw `body_excerpt` for diagnostics, but also writes:

```text
body_evidence_excerpt
body_evidence_focus
body_evidence_forbidden
```

The evidence excerpt strips common body noise before Groq input:

- English dateline prefixes such as `KUALA LUMPUR, June 13 —`;
- wire credits such as `— Bernama`;
- advertisement and related-link boilerplate;
- excess whitespace.

## Policy Strengthening

The body policy still uses:

```text
use_body
rss_only
rss_fallback
```

Policy is stricter around political-context body text. Political or party-context text is kept as `rss_only` unless it contains clear operational public-service evidence.

Procedure and public-service signals were expanded for items such as:

- `LHDN`;
- tax exemption;
- `e-Derma`;
- applications;
- permits;
- licence/license;
- renewal;
- deadline.

This keeps high-value body evidence for tax, application, subsidy, transport, public service, and similar life-impact items while reducing background political noise.

## Structured Groq Input

The Groq renderer no longer sends raw `body_excerpt` in the payload.

When body policy is `use_body`, it sends:

```json
{
  "body_evidence": {
    "excerpt": "...",
    "focus": ["procedure_or_public_service"],
    "forbidden": ["dateline", "wire_credit", "advertisement", "related_links", "unsupported_conditions"],
    "policy": "use_body",
    "reason": "allowed_public_service",
    "content_source": "article_body"
  }
}
```

The system prompt now tells Groq to use only `body_evidence`, and not to use forbidden elements such as datelines, wire credits, ads, related links, or unsupported conditions.

## Life Impact Focus

`body_evidence_focus` is now expected to guide `life_impact`, not only describe why body evidence was allowed.

When focus is present, Groq should avoid generic wording such as:

```text
生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります
```

Expected focus mapping:

- `procedure_or_public_service`: application, deadline, eligibility, counter, or procedure impact;
- `cost_or_subsidy`: household cost, price, subsidy, eligibility, or payment impact;
- `transport_or_infra`: service, road, commute, travel, or user impact;
- `consumer_or_payment`: payment, app, service access, fee, or method impact;
- `health_or_education`: healthcare, education, school, student, or target-group impact;
- `financial_service_access`: banking, financial-service access, counter, or customer-service impact.

If body evidence has focus but Groq still returns generic `life_impact`, validation rejects the Groq summary and the item falls back to RSS-rendered output.

## Boundary

This change does not alter RSS source selection, workflow flags, Pages index generation, or the guarded overwrite validator.

Body enrichment remains optional.

`force_all_groq=false` remains the recommended daily setting.

## Verification

Expected checks:

```bash
python3.12 -m py_compile scripts/enrich_malaysia_selected_items_with_body.py scripts/render_malaysia_news_with_groq.py
```

Fixture checks should confirm:

- dateline and wire-credit text are removed from `body_evidence_excerpt`;
- raw `body_excerpt` is not sent in the Groq payload;
- structured `body_evidence` is sent when policy is `use_body`;
- political-context transport text can be kept as `rss_only`;
- tax/application/public-service evidence can be kept as `use_body`.
- generic `life_impact` is rejected when `body_evidence_focus` is present;
- focus-specific `life_impact` is accepted when supported by body evidence.
