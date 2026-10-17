#!/bin/bash

# Test runner script for dreame-mower project
# 
# This script runs comprehensive tests on the codebase:
# 1. pytest - Runs all unit tests (tests/ directory)
# 2. mypy (main) - Type checks main codebase (custom_components/)
# 3. node --check - Syntax check of the map card's modules (skipped without node)
# 4. node --test - Tests of the map card (tests/frontend/, skipped without node)
#
# Usage: ./run_test.sh
# Requirements: Virtual environment with pytest and mypy installed at .venv/;
# for the card tests, node and its packages (npm ci)
#
# Each step stops after a time limit of a few times its usual duration, and
# counts as failed then; pytest and the card tests also stop a single test
# that hangs (pytest.ini, package.json).
#
# Exit codes:
# 0 - All tests passed
# 1 - One or more tests failed

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track results and counts
PYTEST_RESULT=0
MYPY_MAIN_RESULT=0
CARD_RESULT=0
CARD_TEST_RESULT=0
CARD_DIR="custom_components/dreame_mower/frontend"
TEST_COUNT=""
MAIN_FILE_COUNT=""

print_header() {
    echo
    echo "============================================================"
    echo -e "${BLUE}$1${NC}"
    echo "============================================================"
}

print_success() {
    echo -e "${GREEN}✅ $1 - PASSED${NC}"
}

print_error() {
    echo -e "${RED}❌ $1 - FAILED${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Time limits of the steps, in seconds; the environment can set others.
# Usually pytest takes about 20 s, mypy a few seconds without its cache and
# the card tests about 12 s.
PYTEST_LIMIT=${PYTEST_LIMIT:-90}
MYPY_LIMIT=${MYPY_LIMIT:-60}
CARD_TEST_LIMIT=${CARD_TEST_LIMIT:-60}

# The terminal's stderr, for the time limit's message even where a step's
# output is read into a variable.
exec 3>&2

# A process and everything it started, the youngest first.
process_tree() {
    local child
    for child in $(pgrep -P "$1"); do
        process_tree "$child"
    done
    echo "$1"
}

# Sends signal $1 to process $2 and everything it started.
signal_tree() {
    kill "-$1" $(process_tree "$2") 2>/dev/null || true
}

# Runs a command, and stops it with what it started once it takes longer
# than $1 seconds; its status then is 124. What does not stop within a few
# seconds is killed. An interrupt (Ctrl-C) stops it too: commands started
# from a script do not hear the interrupt themselves.
run_limited() {
    local limit=$1
    shift
    "$@" &
    local pid=$!
    (
        # Only a sleep that ran out stops the command, not one stopped below.
        sleep "$limit" || exit 0
        echo -e "${RED}⏱  $* took longer than ${limit} s; stopped${NC}" >&3
        touch "$TIMED_OUT"
        local pids
        pids=$(process_tree "$pid")
        kill -TERM $pids 2>/dev/null
        local tick pid_left
        for tick in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
            pid_left=""
            for pid_left in $pids; do
                kill -0 "$pid_left" 2>/dev/null && break
                pid_left=""
            done
            [ -z "$pid_left" ] && exit 0
            sleep 0.2
        done
        kill -KILL $pids 2>/dev/null
    ) >/dev/null 2>&1 &
    local watchdog=$!
    trap 'signal_tree TERM "$pid"; signal_tree TERM "$watchdog"; rm -f "$TIMED_OUT"; exit 130' INT TERM
    local status=0
    # The shell's own note of a stopped command is left out.
    wait "$pid" 2>/dev/null || status=$?
    if [ -e "$TIMED_OUT" ]; then
        # The watchdog finishes off what is left.
        wait "$watchdog" 2>/dev/null || true
        trap - INT TERM
        rm -f "$TIMED_OUT"
        return 124
    fi
    signal_tree TERM "$watchdog"
    wait "$watchdog" 2>/dev/null || true
    trap - INT TERM
    return $status
}
TIMED_OUT="$(mktemp -u "${TMPDIR:-/tmp}/run_test_timeout.XXXXXX")"

# Get to the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Project root: $SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -f ".venv/bin/pytest" ] || [ ! -f ".venv/bin/mypy" ]; then
    echo -e "${RED}❌ Virtual environment not found or missing pytest/mypy${NC}"
    echo "Please ensure .venv is set up with required dependencies"
    exit 1
fi

# 1. Run pytest
print_header "Running pytest"
if run_limited "$PYTEST_LIMIT" .venv/bin/pytest --tb=short; then
    # Get test count from last run (approximate)
    PYTEST_RESULT=0
    print_success "pytest"
else
    print_error "pytest"
    PYTEST_RESULT=1
fi

# 2. Run mypy on main codebase
print_header "Running mypy on main codebase"
if MYPY_MAIN_OUTPUT=$(run_limited "$MYPY_LIMIT" .venv/bin/mypy custom_components/ 2>&1); then
    # Extract file count from success message
    MAIN_FILE_COUNT=$(echo "$MYPY_MAIN_OUTPUT" | grep -o 'Success: no issues found in [0-9]\+ source files' | grep -o '[0-9]\+')
    if [ -n "$MAIN_FILE_COUNT" ]; then
        echo -e "${GREEN}✅ mypy main - $MAIN_FILE_COUNT files${NC}"
    else
        print_success "mypy main"
    fi
else
    print_error "mypy main"
    echo "$MYPY_MAIN_OUTPUT"
    MYPY_MAIN_RESULT=1
fi

# 3. Syntax check of the map card
print_header "Checking the map card"
if command -v node >/dev/null 2>&1; then
    for CARD_JS in "$CARD_DIR"/*.js; do
        if node --check "$CARD_JS"; then
            print_success "node --check $(basename "$CARD_JS")"
        else
            print_error "node --check $(basename "$CARD_JS")"
            CARD_RESULT=1
        fi
    done
else
    print_warning "node not found; skipping the syntax check of $CARD_DIR"
fi

# 4. Tests of the map card
print_header "Testing the map card"
if command -v node >/dev/null 2>&1; then
    if [ ! -d "node_modules/jsdom" ]; then
        print_error "card tests: their packages are missing; run npm ci"
        CARD_TEST_RESULT=1
    elif run_limited "$CARD_TEST_LIMIT" npm test --silent; then
        print_success "card tests"
    else
        print_error "card tests"
        CARD_TEST_RESULT=1
    fi
else
    print_warning "node not found; skipping the card tests"
fi

# Print summary
echo
echo "============================================================"
echo -e "${BLUE}SUMMARY${NC}"
echo "============================================================"

# Summary using stored results
if [ $PYTEST_RESULT -eq 0 ]; then
    print_success "pytest"
else
    print_error "pytest"
fi

if [ $MYPY_MAIN_RESULT -eq 0 ]; then
    if [ -n "$MAIN_FILE_COUNT" ]; then
        echo -e "${GREEN}✅ mypy (main codebase) - $MAIN_FILE_COUNT files PASSED${NC}"
    else
        print_success "mypy (main codebase)"
    fi
else
    print_error "mypy (main codebase)"
fi

if [ $CARD_RESULT -eq 0 ]; then
    print_success "map card syntax"
else
    print_error "map card syntax"
fi

if [ $CARD_TEST_RESULT -eq 0 ]; then
    print_success "map card tests"
else
    print_error "map card tests"
fi

echo "============================================================"

# Overall result
TOTAL_ERRORS=$((PYTEST_RESULT + MYPY_MAIN_RESULT + CARD_RESULT + CARD_TEST_RESULT))

if [ $TOTAL_ERRORS -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests PASSED!${NC}"
    exit 0
else
    echo -e "${RED}💥 $TOTAL_ERRORS test(s) FAILED!${NC}"
    exit 1
fi