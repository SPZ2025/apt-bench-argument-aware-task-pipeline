# Executing generated semantic jobs

Use fresh-context native subagents for actual analysis, construction, revision
and audit assignments. Assign one issued job JSON per new agent. A worker reads
only that JSON, completely, including truncated parts, and writes the envelope
to its output_path. It must not browse, enumerate files, read sources outside
the packet, inspect previous reviews, delegate, or generate an essay. Programmatic
serialization is allowed; invented maps, fake model grades and heuristic approvals
are not. The coordinator calls next, then submit with the real actor and model
label, and repeats. Construction/revision must not inherit source context; auditing
must not inherit map, previous grades or generator context.

Use only existing MSAP Python with -B. No dependency installation, API setup or
model downloads. This project does not automatically upload or publish data.
