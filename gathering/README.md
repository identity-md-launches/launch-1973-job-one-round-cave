# Gathering 01 — Four Paths, One Basket

This round checked all four line tools, joined SafeZip and ApiDelta into the independently runnable `shared/api_bundle/`, and built the first gathering gallery. See `REPORT.md` for the checks, results, scope and future work, and `COINS.md` for the decision to request no new coin. No line folder was modified.

Try the shared working piece:

```sh
python3 -B shared/api_bundle/selftest.py
```

Result: ten integration tests passed. All dependencies are ordinary standard-library Python files in this repository. Scratch is disposable and not required at startup.

Rebuild the gallery after updating numbered records:

```sh
python3 -B gathering/build_gallery.py
```

The first run used `--placeholders` to create only missing slots 02–21. The page embeds its styling and static content; images use local JPEG previews and content-addressed full-wall links. Serve `dist/` using any static server or open `dist/index.html` locally. Future slots link to their exact records. The gallery build reads the four goals and numbered records, and writes only `dist/`.

## Wall and review

Output: `artifacts/gathering/wall.png`, PNG, 1254 × 1254, the same dimensions as the supplied bare cave. Preview: `dist/gathering/01.jpg`, JPEG, 512 × 512, below 100 KB. Metadata: `dist/gathering/01.json`, with the PNG's actual SHA-256 artifact URL. `review.json` records dimensions, formats, digest, limitations and visual inspection.

The built-in imagegen tool edited the original bare cave. No prior gathering painting existed. The mark shows Pepe bringing four trails into one basket, in worn earth pigments. Inspection found a recognizable Pepe face, five digits on each visible hand (four fingers and a thumb), no handprints, and no text or prohibited marks. Cave size, framing, torchlight and major cracks are visually retained. Generative editing may change fine rock texture; no pixel-perfect preservation claim is made. There are no observed unmet visual requirements. Visual review is one worker's inspection and has no independent authority.

Final image prompt (built-in mode, one edit):

> Use case: precise-object-edit. Edit this bare cave wall by ADDING a prehistoric gathering painting, preserving exactly its square dimensions, warm rock, every crack, torch lighting and framing. Main figure: recognizable Pepe the frog drawn primitively in charcoal, wide mouth and big heavy-lidded eyes, ochre and chalk accents. Pepe sits in the middle lower part of the broad wall, bringing together four winding ochre trails into a simple woven basket holding four irregular stones. This symbolizes four workers sharing useful tools. Both hands visible, each with exactly FIVE digits: four fingers and one thumb, clearly separated, count them carefully. No other hands or handprints. Small handmade painting with abundant untouched stone showing through pigment, uneven worn burnt-stick lines, red ochre, yellow ochre, charcoal black and chalk white only. Lascaux cave pigment, not a polished cartoon. Keep entire cave background and shape unchanged. NO letters, numbers, captions, signatures, logos, watermarks, borders or frames. No photographs of figures, no 3D figures, no real people, no political or hateful symbols.

ImageMagick was used only to resize/convert the required JPEG, not for painting, and is not a dependency of the delivered Python tools or gallery builder. Only the finished wall PNG and its JPEG were saved as new pictures in the workspace.
