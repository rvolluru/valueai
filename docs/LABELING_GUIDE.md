# Labeling Guide

## Scope

Fashion resale items with single-item photos on clean backgrounds:

- `clothes`
- `shoes`
- `handbag`

## Brand Evidence Detection (YOLO)

Label bounding boxes for:

- `tag_label`
- `logo_wordmark`
- `hardware_engraving`
- `monogram_pattern`
- `hangtag`

Guidelines:

- Tight boxes around readable text/logos.
- Separate boxes when multiple evidence regions exist.
- For repeated monograms, box a representative area with clear pattern visibility.
- Include partially visible tags if text is still inferable.
- Do not label decorative graphics with no brand evidence.

## Brand Classification / OCR Notes

- Canonical brand names must map to `packages/brand/src/brand/brands.json`.
- Preserve OCR-visible variants (e.g., `YSL`, `LV`) as aliases in `brands.json`.
- Use close-up shots whenever possible for tags/hardware engravings.

## Condition Labels

Grades:

- `New`
- `LikeNew`
- `Good`
- `Fair`
- `Poor`

Grade definitions:

- `New`: unused, no visible wear.
- `LikeNew`: minimal signs of handling, nearly pristine.
- `Good`: normal resale wear, presentable and functional.
- `Fair`: obvious wear/damage but usable.
- `Poor`: heavy wear or damage; repair likely needed.

Issue tags (MVP):

- Clothes: `stains`, `pilling`, `fading`, `holes_tears`, `fraying`
- Shoes: `scuffs`, `creasing`, `outsole_wear`, `missing_laces`
- Handbag: `corner_wear`, `hardware_scratches`, `handle_wear`, `lining_stain`, `shape_loss`

Issue annotation tips:

- Tag only visible issues in the submitted image set.
- Use `light|moderate|heavy` severity.
- Location may be `unknown` in MVP if exact localization is unavailable.
