# Output Contract

Return exactly one JSON object with these keys:

```json
{
  "common_name_ja": null,
  "scientific_name": null,
  "confidence": 0.0,
  "candidates": [
    {
      "common_name_ja": "候補名",
      "scientific_name": "候補学名またはnull",
      "confidence": 0.0,
      "reason": "候補理由"
    }
  ],
  "visible_features": [
    "見えている特徴"
  ],
  "uncertainty_notes": ""
}
```

## Limits

- `common_name_ja`, `scientific_name`: use `null` if unknown
- `confidence`: number from `0.0` to `1.0`
- `candidates`: max 3 items
- `candidates[].reason`: max 120 Japanese characters
- `visible_features`: max 5 items
- `visible_features[]`: short fact only, max 25 Japanese characters
- `uncertainty_notes`: max 120 Japanese characters

## Allowed Behavior

- Use only what is visible in the provided images.
- Mention uncertainty instead of forcing a precise species or cultivar.
- Keep a single best candidate even when uncertain.

## Forbidden Behavior

- No prose before or after the JSON
- No Markdown
- No code fences
- No alternate top-level keys such as `common_name`, `plant_name`, `observation_summary`, `characteristics`, `care_advice`, or `status`
- No care guide, profile article, or long observation report
