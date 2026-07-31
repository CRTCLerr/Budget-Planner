# Budget Planner

Budget Planner is a Windows desktop app for tracking income, expenses, debt, savings, categories, and budget limits in one place. It uses Tkinter for the UI, SQLite for storage, and an in-app update flow that can check GitHub Releases and apply updates without leaving the app.

## What You Get

- A dashboard with monthly totals, running balance, and recent activity.
- A transaction entry form that handles income, expense, savings transfers, and debt payments.
- A history screen with filters, editing, and report/print support.
- Budget planning tools with advisor recommendations, manual sliders, and category management.
- Debt tracking, savings forecasting, and visual charts.
- A built-in tutorial overlay that walks through every screen.

## Quick Start

### Run from source

1. Install Python 3.13 or newer.
2. Install the app dependencies for your environment:

```bash
python -m pip install pillow matplotlib numpy pywin32
```

3. Launch the app:

```bash
python main.py
```

### Build a distributable

The project includes PyInstaller support for Windows packaging.

- `Budget Planner.spec` is the main spec file.
- `tools/pyinstaller.py` contains the build helper.

If you already use PyInstaller in your environment, build with the spec file from the project root.

Current behavior:

- Local build output is a single executable file (one-file mode) in `dist/`.
- Windows local build output is `dist/Budget Planner.exe`.

## Releases and Downloads

Users should download the app from GitHub Releases, not from source ZIPs.

- Windows installer asset: `Budget-Planner-Setup-windows-x86_64.exe`
- Windows portable asset: `Budget-Planner-windows-x86_64.exe`
- Linux asset: `Budget-Planner-linux-x86_64`

Each release should include both assets so the in-app updater can select the correct platform package.

Recommended user flow:

- New Windows users: use the installer (`Budget-Planner-Setup-windows-x86_64.exe`).
- Existing portable Windows users: keep using the portable `.exe` update track.
- Linux users: use the Linux binary asset.

## Automated Windows + Linux Release Builds

This repository now includes a GitHub Actions workflow:

- Workflow file: `.github/workflows/release-build.yml`
- Trigger: push a version tag like `v1.04.01`
- Output:
	- Windows portable one-file binary
	- Windows installer with Program Files default and install-folder picker
	- Linux one-file binary
	- All published directly to the GitHub Release

There is also an automation workflow that creates the release tag from the version file:

- Workflow file: `.github/workflows/create-release-tag.yml`
- Trigger: push a change to `core/app_version.py` on `main`
- Behavior: reads `APP_VERSION`, creates `v<version>` if it does not already exist, and pushes that tag

That means the normal release flow is:

1. Test and merge the release commit to `main`.
2. Update `core/app_version.py` to the version you want to ship.
3. Push the version bump.
4. GitHub Actions creates the tag and then the build workflow publishes the release assets automatically.

Important:

- PyInstaller does not reliably cross-compile Windows and Linux binaries from one machine.
- The workflow builds each platform on its native runner (`windows-latest`, `ubuntu-latest`) and then publishes both assets to one release.

## Update Compatibility Notes

The updater supports both modern one-file and legacy one-dir style release assets.

- Portable `.exe` releases can replace the running app binary in place.
- Installer-style releases (`.msi` or setup `.exe`) are used for Program Files installations.
- `.zip` assets are supported as a fallback path for legacy one-dir update flows.

## Core Screens

### Dashboard

The dashboard is the home screen. It shows:

- Monthly income
- Monthly expenses
- Weekly spending
- Total debt
- Running total
- Total savings
- Budget alerts
- Recent transactions

Use the dashboard first when you want a fast financial summary.

### Add Transaction

Use this screen to record day-to-day activity.

- Income and expense entries
- Savings transfers
- Savings spending
- Debt payments tied to a debt record
- Date selection with the built-in calendar picker

The form changes based on the transaction type and category you choose.

### History

The history screen is the ledger view.

- Filter by category, vendor, type, month, and year
- Edit or delete selected rows
- Print or preview a report of the filtered results
- Review the exact transaction details stored in SQLite

### Budget Limits

Budget Limits is where planning happens.

- View advisor recommendations
- Set manual budget limits with sliders
- Switch history windows for the advisor
- Add, rename, archive, reactivate, or import categories
- Show archived categories when you need them

### Debt

The debt screen tracks balances and payment workflows.

- Add new debts with a type
- Apply a payment from Add Transaction
- Modify a selected debt
- Delete a selected debt

### Charts

Charts turn your activity into visuals.

- Spending by category for the current month
- Spending by vendor for the current month
- Income versus spending across the last six months

### Savings

Savings shows savings progress over time.

- Savings forecast
- Savings growth chart
- Savings transaction history

### Settings

Settings controls update behavior and tutorial behavior.

- Check for updates automatically at startup
- Auto-install updates after confirmation
- Check for updates manually
- Show the tutorial on startup
- Start the tutorial again any time
- Reset tutorial completion so it can show again later

## Built-In Tutorial

The app now includes a first-class tutorial overlay.

- It dims the whole window.
- It highlights one screen area at a time.
- It explains what each screen is for and how to use it.
- It can start automatically on first run.
- You can replay it from Settings whenever you want.

The tutorial covers:

1. Dashboard
2. Add Transaction
3. Debt
4. Budget Limits
5. History
6. Charts
7. Savings
8. Settings

If you want the walkthrough to appear again on startup, enable it in Settings and reset completion.

## Data Storage

Budget Planner stores data in SQLite.

- When running from source, the database lives in the project folder.
- When running as a packaged app, the database is stored under `%LOCALAPPDATA%\BudgetPlanner`.
- App settings are stored in the same AppData folder as `settings.json`.

This means your data and preferences persist between launches.

## Suggested Workflow

1. Open Dashboard to get the current snapshot.
2. Add income, expenses, savings moves, or debt payments in Add Transaction.
3. Review the ledger in History.
4. Tune budget limits and categories in Budget Limits.
5. Check Charts and Savings to see trends.
6. Use Settings to manage updates and replay the tutorial.

## Notes

- Historical transactions keep their original category labels even if category settings change later.
- The app uses default categories rather than template imports.
- Update checks use GitHub Releases and can restart the app after applying an update.

## Troubleshooting

- If the window opens with no data, make sure the database file exists in the expected location.
- If a packaged build cannot find assets, rebuild from the project root so the spec file can resolve paths correctly.
- On Windows, print/export features and update application use native shell integration, so they work best on the desktop version of the app.

## License

No license file is currently included in this repository.
