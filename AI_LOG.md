# AI Use Log

A running record of how AI tools were used in this project, to support the AI
reflection required by the project brief (Section 7). One entry per working
session.

**AI tool used:** Claude (Anthropic), via the Claude app, with access to the
project folders on my computer.

**Columns:**
- *Task / prompt*: what I asked the AI to do.
- *AI output*: what it produced (files, explanations, suggestions).
- *How I verified it*: tests run, documents checked, reasoning I did myself.
- *What I changed / rejected*: edits I made, suggestions I didn't take, errors found.

---

## 2026-10-05 – Repository set-up

| Task / prompt | AI output | How I verified it | What I changed / rejected |
|---|---|---|---|

| Asked to assist with setting up GitHub repo, given the project brief and Week 1 notes (1.2–1.5, Workshop 1). Needed clarification on how to work best in VSCODE as had only set up Github in Colab Notebooks.| Read the brief and notes; recommended a `src/` package layout, keeping the ~2 GB dataset out of Git, pytest + pdoc, branching, and this log. | Cross checked Claude's suggested practices with content given in notebooks and practical exercises to ensure it made practical sense. Researched common accepted practice for using github and VSCODE with large datasets | Very little was changed/ rejected as it this stage the tasks is just basic code and software setup, no engineering decisions. Did however mandate the addition of an explicit AI log alongside the AI statement at the end. |

| Asked for explanation of how to clone repo into VSCODE specifically | Gave step-by-step set-up instructions. | Followed the steps myself: created the repo, configured Git, cloned it in VS Code. Checked in files to ensurue all included files had been cloned from the repository. | Nothing was changed, this was just a basic step giving assistance and reminders on how to clone a Github repository |

| Asked Claude to create an example code skeleton to structure where I would work and save elements of the project. | Created `pyproject.toml`, `.gitattributes`, project rules in `.gitignore`, `src/mma3001/paths.py` + tests, `data/README.md`, README outline, `CLAUDE.md`, this log. | read each file, ran `pytest`._ | Largely re-wrote the README file and AI declaration |



**Reflection notes:** _TODO (Sam) – anything learned, or anything the AI got wrong or unhelpful._
