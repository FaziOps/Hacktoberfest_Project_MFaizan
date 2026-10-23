# Fabric defect guide

## Defect codes

| Code | English | Urdu | What it looks like |
|---|---|---|---|
| `hole` | Hole / cut | سوراخ | An opening where yarns are broken right through the fabric. Light shows through. |
| `stain` | Stain / oil spot | داغ | A discoloured patch: machine oil (dark, shiny edge), grease, dirt, rust (orange-brown) or a dye spot. |
| `slub` | Slub (thick yarn) | موٹا دھاگا | A short, thick, raised place in a single yarn. Common in cotton. |
| `broken_yarn` | Broken / missing yarn | ٹوٹا ہوا دھاگا | A warp end or weft pick is missing, leaving a thin straight line or gap across or along the fabric. |
| `misweave` | Mis-weave / float | بُنائی کا نقص | Yarns interlaced wrongly: a yarn floating over several others, a pattern error or a wrong-draw line. |
| `shade_variation` | Colour shading | رنگ کا فرق | A band or patch lighter or darker than the rest, often from uneven dyeing. |
| `crease` | Crease / crush mark | شکن کا نشان | A permanent fold line or crushed area that does not recover. |
| `other` | Other defect | دیگر نقص | Any other clearly visible flaw. |

**Not defects:** the normal weave texture, a printed or woven pattern, the selvedge edge, loose lint
that brushes off, and shadows from the lighting.

## Size codes

Use the defect's longest dimension.

| Code | Length | Points |
|---|---|---|
| `up_to_3in` | up to 3 in (7.5 cm) | 1 |
| `3_to_6in` | 3 to 6 in (7.5 to 15 cm) | 2 |
| `6_to_9in` | 6 to 9 in (15 to 23 cm) | 3 |
| `over_9in` | over 9 in (23 cm) | 4 |

Holes always score 4 points, whatever their size.

## 4-point system (ASTM D5430)

1. Give each defect penalty points by its size, using the table above.
2. Add up the points for the roll.
3. Normalise to points per 100 square yards:

   ```
   points per 100 sq yd = total points × 3600 / (width in inches × length inspected in yards)
   ```

4. Grade the roll:

   | Grade | Points per 100 sq yd | Action |
   |---|---|---|
   | A | 20 or less | Pass |
   | B | over 20, up to 40 | Pass. Mark the defects for the cutting table. |
   | C | over 40 | Reject. Re-inspect and repair before dispatch. |

40 points per 100 sq yd is the acceptance limit most export buyers use. Change `GRADE_LIMITS` in
`scripts/fabric_core.py` if a buyer sets a different one.
