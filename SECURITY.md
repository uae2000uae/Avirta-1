# Security Policy

This project is configured to prevent secrets from being committed, surfaced in pull requests, or deployed.

What is enabled in GitHub
- Secret scanning and Push Protection: repository is protected by GitHub. Pushes with detected secrets will be blocked and alerts raised.
- Partner alerting: for public repositories, GitHub notifies participating service providers when their keys are detected.
- Code scanning ingestion: CI uploads Gitleaks findings to the GitHub Security tab as SARIF.

What we added in this repository
- CI secret scanning (Gitleaks): A GitHub Actions workflow scans every push and pull request for secrets and fails the check if any are detected.
- Allowlist for placeholders: Common placeholders (e.g., SET_IN_ENV, redacted samples) are allowed to reduce false positives. See .gitleaks.toml.
- Secrets at runtime only: The application reads secrets (OpenAI key, GitHub token) from environment variables or Google Secret Manager on Cloud Run. Secrets are not stored in version control.

How to report a vulnerability
- Please open a private security advisory or email the repository owner. Do not open a public issue for sensitive reports.

Developer guidance (avoid leaks)
- Never commit plaintext secrets (API keys, tokens, passwords) to the repo.
- Use environment variables locally (e.g., AI_Token, GITHUB_TOKEN) and Google Secret Manager in production.
- Files likely to hold local secrets are git-ignored (.env, contents/admin_controls/*settings.json, IDE folders). Do not force-add them.
- If you accidentally commit a secret:
  1) Revoke/rotate it immediately at the provider.
  2) Remove it from the working tree and history (git filter-repo or BFG).
  3) Push with --force-with-lease only after coordinating with collaborators.

Local scanning (optional)
- You can run Gitleaks locally before committing:
  - With Docker: docker run --rm -v $PWD:/repo zricethezav/gitleaks:latest detect --source=/repo --no-banner --redact --config /repo/.gitleaks.toml
  - Or install gitleaks and run: gitleaks detect --source . --no-banner --redact --config .gitleaks.toml

Cloud Run/Google Cloud notes
- Provide AI_Token and GITHUB_TOKEN via Google Secret Manager and map them to environment variables during deployment (Cloud Build or gcloud run --set-secrets ..., e.g., GITHUB_TOKEN=GitHub_Token:latest).
- Ensure the Cloud Run service account has roles/secretmanager.secretAccessor.

Questions
- If you have questions about the security setup, open a discussion or contact the maintainer.
