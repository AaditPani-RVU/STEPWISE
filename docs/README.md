# STEPWISE documentation

| Document | Markdown (source) | PDF (for reading) |
| --- | --- | --- |
| Project plan — problem, architecture, timeline, risks | [`STEPWISE_Project_Plan.md`](STEPWISE_Project_Plan.md) | `STEPWISE_Project_Plan.pdf` |
| Requirements specification — numbered, testable, traced to the plan | [`STEPWISE_Requirements.md`](STEPWISE_Requirements.md) | `STEPWISE_Requirements.pdf` |

The markdown is the source of truth. The PDFs are generated artifacts — never edit one
directly, and regenerate after any change to a document (requirements change control CC-4).

The plan takes precedence over the requirements spec: where the two disagree, the spec is the
one that is wrong.

## Regenerating the PDFs

`docs/build_pdf.py` renders every `*.md` in this directory to a sibling `*.pdf`.

```bash
uv venv /tmp/docsenv
uv pip install --python /tmp/docsenv/bin/python weasyprint markdown
/tmp/docsenv/bin/python docs/build_pdf.py            # all documents
/tmp/docsenv/bin/python docs/build_pdf.py docs/STEPWISE_Requirements.md   # just one
```

`weasyprint` and `markdown` are documentation-only dependencies and are deliberately kept out
of the project's own requirements — nothing in `stepwise/` imports them.

## Known gap

The plan's Mermaid architecture diagram renders as its source text in the PDF, not as a
diagram. Rendering it properly needs `mermaid-cli`, which pulls in a headless browser; not
worth the dependency until the diagram goes into the report.
