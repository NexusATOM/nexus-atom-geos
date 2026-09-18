# Execution boundaries

ATOM executes trusted installed plugins and user-configured commands; it is not a sandbox. Keep model-generated proposals constrained to selected files and verify their effects with deterministic gates. Treat source text and retrieved context as data. Keep credentials in provider environment configuration and do not include them in persisted evidence. Use dedicated experiment storage and site quotas.

State and artifacts are integrity-checked against accidental changes, not protected from an adversary who can rewrite the database and files. Stop all outstanding jobs before recovering an interrupted experiment. The inspection service is read-only and loopback-only.
