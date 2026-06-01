# Phase 2F.6: Paul Tan Source-Specific Filter Design

## Summary

Phase 2F.6 records a design-only decision for a possible future Paul Tan RSS addition. Paul Tan may be considered for the main Malaysia RSS line only behind a high-precision source-specific filter focused on practical transport and driver impact.

Lowyat.NET is not promoted to the main cleaned RSS set. It remains a separate `digital_life_watch` candidate for low-priority or continued local-only observation.

This phase does not change production RSS, workflow, Pages, Groq, body fetching, `scripts/malaysia_rss_summary.py`, Phase 2F.3A cleaned-set config, or Phase 2F.5 helper behavior.

## Decision

Paul Tan is a possible future addition, but only if the future implementation can filter it before selection using RSS metadata only:

- title;
- description;
- link;
- published date.

It should not rely on article body fetching or Groq to discover whether a Paul Tan item is eligible.

Lowyat.NET should not be added to the main RSS path at this stage. It can continue as `digital_life_watch`, separate from Paul Tan adoption.

## Future Feed Candidate Shape

If Paul Tan is added in a later adoption phase, the candidate metadata should use this shape:

```yaml
id: paul_tan
name: Paul Tan
url: https://paultan.org/feed/
language: en
source_type: automotive_transport
role: transport_driver_impact_candidate
priority: medium
enabled: true
```

`enabled: true` is for a future adoption phase only. Phase 2F.6 does not enable or add this feed to any production or cleaned-set config.

## Paul Tan Positive Signals

Paul Tan should be treated as useful only when the RSS title or description clearly indicates practical Malaysia mobility impact.

Positive signals:

- public transport: `LRT`, `MRT`, `Rapid KL`, `KTMB`, rail, bus, service disruption;
- road and toll impact: road closure, highway, toll, RFID, SmartTAG, traffic enforcement;
- driver obligations: `JPJ`, licence, summons, road tax, insurance, vehicle inspection;
- fuel and subsidy: petrol, diesel, RON95, fuel subsidy, `Budi Madani`;
- safety and recalls: vehicle recall, safety defect, enforcement affecting owners.

Eligible examples would include public transport disruptions, JPJ process changes, toll or fuel-subsidy changes, road closures, and safety recalls affecting Malaysia drivers or commuters.

## Paul Tan Likely Noise

Ordinary automotive coverage should be rejected unless a clear public-service, regulatory, transport, fuel, toll, JPJ, or safety angle is present.

Likely noise:

- car launches;
- previews and reviews;
- spyshots;
- showroom or sales events;
- model pricing, variants, and specs without public-service impact;
- EV product launches without a transport-policy or user-obligation angle;
- motorsport;
- brand, plant, or industry-capacity stories with no direct user impact.

## Future Selection Rule

A future Paul Tan implementation should apply this gate before normal selection:

- keep only if at least one positive signal is present;
- reject if only noise signals are present;
- for mixed positive and noise signals, keep only when the RSS title or description clearly includes public-service, regulatory, transport disruption, fuel/subsidy, toll, JPJ, or safety/recall impact;
- reject items that require article body context to determine relevance.

Accepted Paul Tan items should map into existing transport, JPJ, fuel/cost, or safety categories. They should not create a new broad automotive category.

Recommended source cap: at most `1` Paul Tan item per daily output, unless duplicate coverage proves the item is essential.

## Lowyat.NET Decision

Lowyat.NET is not added to the main cleaned RSS set.

Keep it as a separate `digital_life_watch` observation candidate for:

- telco or public internet access;
- MyKad or government digital services;
- e-wallet and payment systems;
- Touch 'n Go;
- fuel subsidy technology;
- public transport technology.

Treat these as likely noise:

- gadgets;
- phones;
- laptops;
- gaming;
- product launches;
- product reviews;
- overseas tech with no Malaysia daily-life impact.

Any future Lowyat.NET work should be separate from Paul Tan adoption and should not block Paul Tan's transport-specific path.

## Implementation Notes For A Future Phase

If this design is later implemented, prefer a source-specific gate near RSS item evaluation or exclusion rather than broadening global keywords. This keeps Paul Tan's automotive noise from affecting Malay Mail, iMoney, or other general sources.

The gate should be tested with hand-built RSS item fixtures covering:

- positive-only Paul Tan transport item;
- noise-only vehicle launch item;
- mixed JPJ or recall item that also names a vehicle model;
- mixed model-pricing item with no public-service angle;
- Lowyat.NET item kept out of the main path.

## Non-Changes

Phase 2F.6 does not change:

- production RSS source selection;
- GitHub Actions workflows;
- Pages output;
- Groq prompts or model behavior;
- article body fetching;
- `scripts/malaysia_rss_summary.py`;
- `config/malaysia_news_feeds_phase2f.yml`;
- Phase 2F.3A or Phase 2F.5 helper scripts.

