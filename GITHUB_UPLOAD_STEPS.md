# GitHub Upload Commands

Create an empty repository on GitHub first, then run these commands from this
folder:

```bash
git init
git add .
git commit -m "Add Warframe market and mission Discord tracker"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

Before `git add .`, verify that `.env` is not being tracked:

```bash
git status
```

Your real Discord webhook should only exist in `.env`, which is excluded by
`.gitignore`.
