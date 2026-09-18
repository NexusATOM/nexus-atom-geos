# Changelog

## 0.1.0

Initial multi-repository Nexus ATOM implementation. See README for implemented contracts, verification and production integration boundaries.

## Unreleased

- Feed baseline profiler output and previous task failure details into local/NOOA
  optimization proposals. Command results retain bounded log excerpts while full
  logs remain in experiment artifacts.
- Verify a synthetic proposal/build-failure/repair cycle through a real local
  subprocess runtime and the shared controller.
- Profile the candidate after benchmarking, preserving its measured behavior for
  subsequent hypothesis revision; support baseline-only profiler configurations.
- Add configurable mandatory test and sanitizer stages for both phases, separate
  evaluator identities, and evidence requirements enforced by the software gate.
- Export each phase's benchmark samples and timing scope to a sealed CSV artifact.
- Add explicit plot field selection and automatic comparison artifacts during validation, including failed numerical/scientific comparisons.
