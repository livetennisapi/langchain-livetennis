#!/bin/sh
# truthcheck: pin product facts so stale copy fails CI instead of shipping.
# POSIX sh, no dependencies beyond git and grep.
set -u
cd "$(dirname "$0")/.." || exit 1

# Tracked text files, minus this script and the CHANGELOG (whose entries may
# legitimately describe historical values).
FILES=$(git ls-files | grep -v -e '^CHANGELOG\.md$' -e '^scripts/truthcheck\.sh$')

STATUS=0

forbid() {
    # $1 = extended regex, $2 = reason
    HITS=$(echo "$FILES" | xargs grep -nEi "$1" 2>/dev/null)
    if [ -n "$HITS" ]; then
        echo "truthcheck FAIL ($2):"
        echo "$HITS"
        STATUS=1
    fi
}

# Stale quota copy: the old 100k/day free grid, or FREE paired with 1,000/day.
forbid '(100,000|100k)[^.]*(/ *day|per day|daily)' 'stale 100k/day quota'
forbid 'free[^.]*(1,000|1k) *(requests?|calls?)? *(/ *day|per day)' 'free tier is 100/day, not 1k'
# Wrong docs URL: docs live at docs.livetennisapi.com.
forbid 'livetennisapi\.com/docs' 'use docs.livetennisapi.com'
# Personal identity in machine-read or published copy.
forbid 'bensynapse' 'use the org identity'
# The daily reset is a local-midnight-derived instant, not midnight UTC.
forbid 'midnight UTC' 'daily reset is resets_at, not midnight UTC'

# If quota copy exists at all, the current FREE figure and docs URL must too.
if echo "$FILES" | xargs grep -lEi 'per day|/ *day|daily (quota|limit)' >/dev/null 2>&1; then
    if ! echo "$FILES" | xargs grep -lE '100 *(requests *)?/ *day|100 requests/day' >/dev/null 2>&1; then
        echo "truthcheck FAIL: quota copy exists but the FREE figure (100/day) is missing"
        STATUS=1
    fi
    if ! echo "$FILES" | xargs grep -l 'docs\.livetennisapi\.com' >/dev/null 2>&1; then
        echo "truthcheck FAIL: docs.livetennisapi.com missing"
        STATUS=1
    fi
fi

[ "$STATUS" -eq 0 ] && echo "truthcheck OK"
exit "$STATUS"
