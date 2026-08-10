# Data card

## Dataset name

GBI BoundaryBench v0.1 synthetic public-dev data.

## Summary

The released data is a small synthetic benchmark development split for legacy-EHR boundary validation. It contains canonical immutable source facts, RPMS-shaped clean and corrupted projections, corruption event manifests, task records, oracle result records, baseline artifacts, and verifier outputs.

The data is synthetic. It is not clinical truth and must not be described as clinical truth. Expected answers are generator truth and benchmark references.

## Source lineage

The Stage 1 source population is an official Synthea FHIR R4 sample-data alternative documented in:

- `data/external/synthea_sample_data/PROVENANCE.md`
- `data/external/synthea_sample_data/manifests/fhir_r4_sep2019_310_files.txt`

The local bulk source ZIP and extracted upstream FHIR bundle directory are ignored and excluded from the release archive. The committed release includes provenance, subset manifest, generated Stage 1 artifacts, task artifacts, and checksums.

Important lineage limitation: this official Synthea sample-data alternative is not the exact missing Pine Ridge source for the legacy sibling RPMS files audited during Stage 0. The legacy clean/noisy RPMS files remain non-gold fixtures and are not the source of benchmark references.

## Included committed data artifacts

- `data/stage1/official_synthea_sample_310/canonical/*.jsonl`
- `data/stage1/official_synthea_sample_310/corruptions/events.jsonl`
- `data/stage1/official_synthea_sample_310/views/rpms_clean/*.txt`
- `data/stage1/official_synthea_sample_310/views/rpms_corrupt/*.txt`
- `data/stage1/official_synthea_sample_310/normalized/fhir_expected.jsonl`
- `data/stage1/official_synthea_sample_310/metadata/*`
- `data/tasks/public_dev/*.jsonl`
- `data/tasks/public_dev/manifest.json`

## Excluded local artifacts

The following are not part of the release source archive:

- upstream Synthea ZIP downloads;
- extracted upstream FHIR bundles;
- scratch regenerated data under `data/generated/`;
- private credentials or local `.env` files;
- prompt/bootstrap materials not cleared for redistribution.

## Synthetic status and privacy

The data was derived from Synthea synthetic sample data and project-authored deterministic transformations. No real PHI/PII is intended or permitted. If any source appears non-synthetic, stop use and open a release-blocking issue.

This statement is not a legal or privacy certification.

## Generation and corruption

Stage 1 fixes the clean/noisy pairing flaw identified in the initial audit:

- source facts are canonical immutable records;
- legitimate stochastic fields are sampled once;
- corrupted views are produced by pure deterministic corruption transforms;
- every observable cell change is represented by a manifest event;
- every manifest event corresponds to an observable cell change;
- regeneration is seedable and replayable.

## Recommended use

Use this data to test:

- parsing and structured output under legacy flat-file constraints;
- abstention versus unsupported confident completion;
- evidence and provenance grounding;
- deterministic verifier behavior;
- local baseline and adapter integration.

Do not use this data for patient care, clinical performance claims, certified crosswalk validation, or production EHR write-back.

## License boundary

Project-authored synthetic benchmark data is covered by `DATA_LICENSE.md` to the extent project contributors hold rights. Upstream Synthea notices and provenance are preserved in `THIRD_PARTY_NOTICES.md` and `data/external/synthea_sample_data/PROVENANCE.md`.
