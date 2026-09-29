# SoftwareX submission materials

Working materials for the SoftwareX Original Software Publication describing this
package. **Nothing here has been submitted.**

| File | Contents |
|---|---|
| `manuscript_draft.docx` | **Editable** draft on Elsevier's template, with Figs. 1-2 embedded and `[AUTHOR]` markers highlighted. Rewrite here. |
| `manuscript_draft.pdf` | The same draft for reading. |
| `build_manuscript.py` | Rebuilds the .docx and .pdf from `manuscript_draft.md` (needs python-docx, reportlab, and the template downloaded next to it). |
| `manuscript_draft.md` | Draft in the SoftwareX template's section order, with `[AUTHOR: ...]` markers. Produced with generative AI (Claude, Anthropic) for the author to rewrite; see its AI declaration. |
| `SUBMISSION_CHECKLIST.md` | What must be done before submitting. |
| `cover_letter_draft.md` | Cover-letter points. |
| `figures/make_figures.py` | Regenerates Fig. 1 (architecture) and Fig. 2 (the package's own output for a DBS 3389 contact). Run with the package installed: `cd softwarex/figures && python make_figures.py`. |
| `figures/*.svg, *.pdf, *.tiff` | The figures (183 mm; TIFF at 600 dpi). |

The official template is Elsevier's:
https://legacyfileshare.elsevier.com/promis_misc/softwarex-osp-template.docx
