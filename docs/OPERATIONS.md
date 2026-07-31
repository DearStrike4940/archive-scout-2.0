# Operation Guide

## Rescan existing downloads

Use this after changing keywords.

1. Load the existing `project.json`.
2. Replace the keywords in the Keywords tab.
3. Select **Rescan existing downloads with current keywords**.
4. Click **Start**.

Archive Scout reads the project database and saved text files. It does not query CDX or download any captures. A new scan run and new report folder are created.

## Retry only errored URLs

Use this after timeouts, temporary server errors, failed scans, or interrupted parsing.

1. Load the same project.
2. Keep the intended keywords in the Keywords tab.
3. Select **Retry only errored URLs**.
4. Click **Start**.

Only unresolved retryable errors are selected. Existing valid files are rescanned locally. Other failed captures are downloaded again.

## Resume interrupted work

Use this after intentionally stopping a run or after an application or system interruption. Resume processes pending records. It does not automatically include records already classified as errors.

## Regenerate reports

Use this when the database is complete but report files were moved or deleted. No scanning or downloading occurs.

## Check project integrity

This creates `reports/integrity.txt`. It does not repair or delete anything in alpha 1.
