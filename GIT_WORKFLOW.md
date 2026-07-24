# Budget Planner Git Workflow

This repository uses a simple branch + pull request workflow.

## One-time setup
1. Initialize repository (already done).
2. Create the GitHub repository (already done): `Budget-Planner`.
3. Ensure `.gitignore` exists before first commit.
4. Set your Git identity:

```powershell
git config user.name "Michael LaRoche"
git config user.email "michaellaroche2010@gmail.com"
```

5. Add your GitHub remote and publish:

```powershell
git remote add origin https://github.com/<your-github-username>/Budget-Planner.git
git push -u origin main
```

## First commit
1. Stage files in Source Control.
2. Confirm no generated/local data files are staged.
3. Commit with message: `chore: initial project import`.

## Daily workflow
1. Pull latest `main`.
2. Create a feature branch.
3. Commit small logical changes.
4. Push branch and open a PR.
5. Complete checklist in PR template.
6. Merge PR and delete branch.

## Naming convention
- Branches: `feature/<short-topic>`, `fix/<short-topic>`, `chore/<short-topic>`
- Commits: `feat: ...`, `fix: ...`, `chore: ...`

## Never commit
- `build/`, `dist/`
- local database files (`*.db`, `*.sqlite`, `*.sqlite3`)
- caches (`__pycache__/`)
