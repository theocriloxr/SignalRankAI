# SECURITY

If you discover a security vulnerability, please follow these steps:

1. Rotate the affected credential immediately (database, API keys, tokens).
2. Notify the repository owner and your security contact.
3. If secrets were committed, remove them from history and re-deploy with rotated secrets.

Responsible disclosure/contact:
- Email: security@example.com

Steps to rotate credentials and remediate a leak:
- Invalidate the leaked key/token.
- Issue a new key/token from the provider dashboard.
- Update your deployment environment and CI secrets.
- Revoke any sessions related to leaked accounts.

Cleaning git history if secrets were committed:
- Use `git filter-repo` or recreate the repo to remove the secret from history.
- Create a sanitized branch `cleaned-share` containing the current clean tree.
- Do NOT push the original branch containing secrets.

Additional best-practices:
- Do not commit `.env` or other credential files to the repo.
- Use a secret manager (HashiCorp Vault, AWS Secrets Manager, Railway Secrets).
- Enforce pre-commit detect-secrets and CI checks.

Contact: security@example.com
