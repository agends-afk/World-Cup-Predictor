# Putting the dashboard online (one-time setup)

This publishes the dashboard to a public web address and makes it update
itself as results come in. You do it once. After that, nothing to run.

The plan: your code goes to GitHub, Vercel turns it into a website, and a
scheduled job on GitHub re-runs the model and pushes updates, which Vercel
redeploys automatically.

Everything is already committed and ready. You need to do three things.

---

## Step 1: Publish to GitHub (using GitHub Desktop, which you have)

1. Open the GitHub Desktop app.
2. In the menu bar choose File, then Add Local Repository.
3. Click Choose, and select this folder:
   `/Users/campbellhedley/Documents/Claude/Projects/World Cup Predictor`
4. Click Add Repository. (It is already a Git repository with one commit,
   so it will be recognised immediately.)
5. Near the top you will see a button labelled Publish repository. Click it.
6. In the dialog:
   - Name: `world-cup-predictor` (or any name you like).
   - Description: optional.
   - **Uncheck "Keep this code private."** Make it public. (There are no
     passwords or secrets in here, and a public repository gets unlimited
     free automated updates. A private one is capped and the every-30-minute
     updates would run out of free minutes partway through the month.)
7. Click Publish repository.

Your code is now on GitHub.

## Step 2: Turn on write access for the auto-updater

The scheduled job needs permission to save updated predictions back to the
repository.

1. On github.com, open your new `world-cup-predictor` repository.
2. Click Settings (top right of the repository), then in the left menu
   Actions, then General.
3. Scroll to Workflow permissions.
4. Select "Read and write permissions". Click Save.

## Step 3: Connect Vercel

1. Go to vercel.com and log in with your GitHub account.
2. Click Add New, then Project.
3. Find `world-cup-predictor` in the list and click Import. (If it is not
   listed, click "Adjust GitHub App Permissions" or "Configure" and grant
   Vercel access to the repository, then come back.)
4. Leave every setting as it is. The included `vercel.json` already tells
   Vercel this is a static site and where the files are. Do not set a
   framework or change the build command.
5. Click Deploy and wait about a minute.

You will get a public address like `world-cup-predictor.vercel.app`. That
is your live dashboard. Share it with anyone.

---

## How it stays up to date

- A job on GitHub re-runs the model every 30 minutes, applies any new
  results, and saves the refreshed predictions. Vercel redeploys within a
  minute or two whenever something actually changed. When nothing changed,
  it stays quiet, so the site is never stale for long during a match day.
- The first automatic run happens within about half an hour of publishing.
  To see it work immediately: on github.com open the repository, click the
  Actions tab, choose "Update predictions" on the left, click Run workflow,
  then Run workflow again to confirm.

## Updating squad news (injuries, suspensions)

1. On github.com, open the repository and go to `data/adjustments.json`.
2. Click the pencil icon to edit, make your change, and click Commit
   changes. The next scheduled run (or a manual one) picks it up.

Or edit `data/adjustments.json` locally, then in GitHub Desktop click
Commit and Push. Same result.

## Forcing a full rebuild

The 30-minute job is the fast kind: it adds new results to the saved
ratings. Occasionally (say weekly) it is worth a full rebuild that
re-downloads the entire match history and refits the model. On github.com:
Actions tab, "Update predictions", Run workflow, change the mode dropdown
to `full`, Run workflow.

## A custom web address (optional)

In Vercel, open the project, go to Settings, then Domains, and add a domain
you own. Vercel walks you through the DNS records.

## If something is not working

- The site shows but never updates: check Step 2 (write permissions) and
  that the repository is public (Step 1, point 6). Then trigger a manual
  run from the Actions tab and watch it for errors.
- Vercel did not deploy after an update: in Vercel, open the project,
  Settings, Git, and confirm it is connected to the repository and to the
  `main` branch.
- The Actions tab shows a red failed run: open it, read the last lines.
  The model falls back to the last saved fixtures if a data source is
  briefly unavailable, so most failures are transient and the next run
  recovers.
