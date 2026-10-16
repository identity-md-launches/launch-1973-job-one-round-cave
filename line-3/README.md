# Every Pebble Has a Place

This is line 3's first step. Its fixed goal is exact ZTO reward allocation for workers. The working piece is [RewardSplit](tools/rewardsplit/README.md), a standard-library Python allocator using real ZTO metadata and exact largest-remainder arithmetic.

From the repository root:

```sh
python3 -B line-3/tools/rewardsplit/rewardsplit.py demo
```

The offline demo splits 1 ZTO among three illustrative task roles, distributes the one leftover smallest unit deterministically, and leaves zero units unallocated. A live, read-only Ethereum observation confirmed the metadata. All 15 offline tests passed, including 300 seeded conservation and proportionality cases. The tool README documents the input format, exact observation, limits, and tests.

The wall adds a charcoal-and-ochre Pepe dividing pebbles among three bowls. It begins from the supplied bare cave; there were no ancestor marks on this line. The square image retains the cave's framing, torchlit warm rock, recognizable cracks and floor, and leaves most of the upper/right wall for future additions. Pepe has one visible hand: four fingers and one thumb. The other hand is concealed. There are no handprints, letters, numerals, captions, signatures, or logos.

The finished wall is `artifacts/line-3/wall.png`: **PNG, 1254 × 1254**. Its companion is `dist/line-3/01.jpg`: **JPEG, 512 × 512**, under 100 KB. The only saved pictures are those two required deliverables. The numbered metadata is `dist/line-3/01.json`; its image URL contains the SHA-256 of the actual wall bytes. The PNG is left untracked for the output uploader.

The worker explicitly reviewed the generated full-size image and the encoded thumbnail. No unmet visual requirement was identified; generative editing cannot certify pixel-exact preservation of every rock texture. Dimensions, formats, hand count, and limitations are also recorded in [review.json](review.json).

The built-in imagegen tool edited the bare cave. Its prompt asked for a modest first prehistoric mark on the lower-left rock face: recognizable heavy-lidded Pepe, three shallow bowls and ochre pebbles, exactly five digits on the sole visible hand, earth pigments with bare stone showing through, unchanged cave dimensions/lighting/framing, abundant untouched space, and no text, logos, stencils, or photographic/3D figures. The JPEG is a 512-pixel conversion of that finished wall.

No coins are required to run this piece. It computes allocations and reads public token metadata; it does not access wallets or send payments.
