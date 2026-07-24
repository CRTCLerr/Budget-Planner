# Release Signing Guide (Windows)

This document explains how to ship Budget Planner as a signed, professional Windows application.

## Why signing matters
- Signed executables show a publisher name instead of "Unknown publisher".
- Signing helps reduce SmartScreen warnings over time.
- Unsigned binaries are more likely to be flagged or blocked by enterprise policies.

## What you need
1. A code-signing certificate from a trusted CA.
2. Recommended for fastest reputation: EV Code Signing certificate.
3. Windows SDK installed (includes `signtool.exe`).

## Certificate options
1. Standard Code Signing
- Lower cost.
- Publisher identity is shown, but SmartScreen reputation builds gradually.

2. EV Code Signing (recommended)
- Higher verification level.
- Better initial trust posture for new publishers.

## Sign release assets
Sign each distributed executable/installer (e.g., `.exe`, `.msi`) before uploading to GitHub Releases.

Example command:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "dist\\Budget Planner\\Budget Planner.exe"
```

For MSI packages, sign the MSI output as well:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "dist\\BudgetPlannerInstaller.msi"
```

## Verify signature

```powershell
signtool verify /pa /v "dist\\Budget Planner\\Budget Planner.exe"
```

## Release checklist
1. Build artifact.
2. Sign artifact.
3. Verify signature.
4. Upload only signed files to GitHub Releases.
5. Use semantic version tags (example: `v0.2.0`).

## Security note
- Never publish private signing keys.
- Use hardware-backed key storage (required for EV; strongly recommended for all).
- Timestamp all signatures so they remain valid after certificate expiration.
