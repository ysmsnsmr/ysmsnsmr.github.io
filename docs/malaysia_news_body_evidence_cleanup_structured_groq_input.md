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

- English dateline prefixes such as `KUALA LUMPUR, June 13 —` and `SHAH ALAM, June 15 —`;
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

For `health_or_education` focus, accepted Groq output must describe a concrete effect such as medical fees, treatment cost, subsidy eligibility, patient/target conditions, school, or education impact. A vague line that only says the item is background information for the medical system is rejected and falls back to RSS.

## Protected Scheme Names

Groq output now applies a narrow post-generation display cleanup for observed scheme-name drift.

When the source text contains `eCOSS` or the Cooking Oil Price Stabilisation/ Stablisation/ Stabilization Scheme, the renderer preserves the scheme as:

```text
eCOSS（食用油価格安定化制度）
```

This protects accepted summaries from malformed translations such as `食用石油価格格安定化制度(eCOSS)`.

The cleanup is intentionally scoped to eCOSS evidence and does not broaden Japanese normalization globally.

When the source text contains `Kita Selangor` and voucher evidence, the renderer also protects the scheme label as `Kita Selangor voucher`. This is a narrow typo guard for observed Groq output such as `Kita Selangor voucer`, not a broad translation rule for all voucher terms.

## Force-All Strict Gate

`force_all_groq=true` is treated as broad Groq exploration, not broad production acceptance.

When force-all mode is enabled, the renderer may request Groq summaries for a wider set of items, but an additional accepted gate runs after normal Groq validation and before the item is recorded as accepted.

The force-all gate accepts items only when concrete daily-life impact is evident from both the source metadata and the Groq summary, or when cleaned `body_evidence_focus` already supports a concrete `life_impact`.

Items that are only political background, market background, transport commentary without operational impact, KTM/Komuter political invitation context, individual scam/victim incidents, or Paul Tan automotive noise fall back to RSS-rendered output.

Force-all mode also uses a request cap and a pre-request skip layer before calling Groq. The default cap is `6` requests per run and can be overridden with `MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP`. Known low-value force-all candidates, such as KTM/Komuter political invitation context, individual scam incidents, market background, and Paul Tan noise, are skipped before the API request so HTTP 429 risk is reduced.

Merged candidate Markdown cleans non-accepted RSS fallback blocks after dateline cleanup. The generic fallback lines:

```text
何が起きた：RSS内のタイトルと説明をもとに整理しました。
生活への影響：生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。
```

are replaced with topic-aware RSS fallback text where possible, or a safer non-generic fallback when no topic can be inferred. The exact RSS fallback artifact remains unchanged.

## Boundary

This change does not alter RSS source selection, workflow flags, Pages index generation, or the guarded overwrite validator.

Body enrichment remains optional.

`force_all_groq=false` remains the recommended daily setting until strict-gate artifact observations prove that broad exploration improves quality without adding low-value accepted items.

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
