# Plant Identification Prompt

3枚の写真は同じ植物を撮影したものです。庭木・草花の観察記録として、植物の種類を推定してください。

必ずJSONのみを返してください。Markdown、コードフェンス、JSON外の説明文は禁止です。

```json
{
  "common_name_ja": "標準和名またはnull",
  "scientific_name": "学名またはnull",
  "confidence": 0.0,
  "candidates": [
    {
      "common_name_ja": "候補名",
      "scientific_name": "候補学名またはnull",
      "confidence": 0.0,
      "reason": "候補理由"
    }
  ],
  "visible_features": ["見えている特徴"],
  "care_notes": "手入れや観察メモ",
  "uncertainty_notes": "不確実な点"
}
```

