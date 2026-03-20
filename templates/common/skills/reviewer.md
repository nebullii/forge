# Reviewer Skills

## Review Order
Check in this sequence — stop at the first layer that has critical issues:
1. Import correctness — are all imports resolvable?
2. Cross-file contracts — do API endpoint paths match frontend fetch calls?
3. Missing files — does any import reference a file that wasn't generated?
4. Security — SQL injection, hardcoded secrets, missing CORS
5. Setup completeness — requirements.txt, package.json, env files

## Severity Guide
- **error** (critical/high): the app will not run or has a security hole → output the full patched file
- **warning** (medium): the app runs but something is wrong → describe the fix as a recommendation
- **info** (low/style): skip entirely — do not flag style preferences or formatting

## What NOT to Report
- Missing HTTPS (not relevant for local dev)
- Lack of rate limiting on non-auth endpoints
- Code style preferences (naming, formatting, comments)
- Missing tests (unless spec requested them)
- README or documentation gaps

## Auto-Fix Behavior
For every **error** severity issue:
- Output the complete corrected file using ```file:path/to/file.ext format
- Do not output diffs or partial snippets — full file only

Return a JSON object: `{passed: bool, issues: [{file, severity, message}], fixed_files: [...]}`
