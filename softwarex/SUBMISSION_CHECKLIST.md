# SoftwareX submission — neurostim-safety

Everything here is a draft or a checklist for **you** to act on. Nothing has been
submitted. Submission site: https://www.editorialmanager.com/softx
(article type: **Original Software Publication**).

## Files in this folder

| File | What it is |
|---|---|
| (not in the repo) | Official SoftwareX template, v6 (March 2026): https://legacyfileshare.elsevier.com/promis_misc/softwarex-osp-template.docx — the final manuscript **must** use it. |
| `manuscript_draft.md` | AI-produced draft in the template's section order, with `[AUTHOR: ...]` markers. Rewrite it; don't submit it as is. |
| `figures/figure1_architecture.{svg,pdf,tiff}` | Fig. 1, architecture schematic (183 mm, 600 dpi TIFF). |
| `figures/figure2_dbs3389_summary.{svg,pdf,tiff}` | Fig. 2, the package's own output for the DBS example. |
| `figures/make_figures.py` | Regenerates both figures from the package. |
| `cover_letter_draft.md` | Cover-letter points. |

## Before you submit — mandatory

- [ ] **Rewrite the manuscript in your own words and judgment.** Elsevier: AI may not
      generate sections without genuine author contribution. Check every number
      against the package (the draft's numbers were recomputed at commit 640deec; no number changed since c7032e0).
- [ ] **Fill every `[AUTHOR: ...]` marker**: especially **Impact**, the section
      reviewers weigh most, which must describe *real* use; **Related work**; Example 2
      (your own experiment); competing interests; acknowledgements.
- [ ] **AI declaration** (section before References): edit it to describe truthfully
      what the AI did and what you did. A false or incomplete declaration is an ethics
      breach. AI assistance with the **code** must also be described in detail
      (Elsevier asks for this in a methods-type section; the declaration in the draft
      covers it, so expand if needed).
- [x] **Tag the release**: done — https://github.com/kshtjkumar/neurostim-safety/releases/tag/v0.16.0
      (I can do this when you say so).
- [ ] **Archive on Zenodo** (recommended): connect the repo to Zenodo, publish the
      v0.16.0 release, and cite the DOI as reference [12].
- [ ] **Licence file**: the template asks for "Licence.txt". The repo has `LICENSE`
      (MIT). Usually accepted; if the editors object, add a copy named `LICENSE.txt`.
- [ ] **C8 support contact**: currently the GitHub Issues URL; SoftwareX may ask for an
      e-mail address.
- [ ] **Author line**: the template asks for postal address and e-mail.
- [ ] **Delete all template instructions** (italic text) and the draft's comment block.
- [ ] **Check the publication charge** on the SoftwareX site before you submit (it is an
      open-access journal; confirm the current APC and any waiver).

## Known issues

1. ~~Shannon detail "-> PASS" under a CAUTION check~~ — fixed (ledger 202).
2. ~~"INCOMPLETE" note on macro contacts~~ — fixed (ledger 203).
3. Open ledger items, stated in the repo: 182/188 (mutation score 85.6 % vs 90 %
   target), 197–199 (minor).

## After acceptance

- Keep the repository public and maintained (SoftwareX forks it).
- JOSS: dropped for this version (duplicate software paper).
