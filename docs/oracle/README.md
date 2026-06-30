# Oracle Reports

Compact oracle summaries can be tracked here when they are useful for review.
Generated JSONL labels, checkpoints, and large run outputs belong under
`data/oracle/`, which is ignored.

The oracle pipeline uses Stockfish only as an external teacher for tooling and
diagnostics. These labels and models are not part of LabZero's original engine
core claim unless that policy is explicitly revisited.

See `labzero_feedback_workflow.md` and `labzero_feedback_workflow.dot` for the
full play -> label -> train -> patch -> gate workflow.
