#!/bin/bash

# Test runner script for dreame-mower project
# 
# This script runs comprehensive tests on the codebase:
# 1. pytest - Runs all unit tests (tests/ directory)
# 2. mypy (main) - Type checks main codebase (custom_components/)
#
# Usage: ./run_test.sh
# Requirements: Virtual environment with pytest and mypy installed at .venv/
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
if .venv/bin/pytest --tb=short; then
    # Get test count from last run (approximate)
    PYTEST_RESULT=0
    print_success "pytest"
else
    print_error "pytest"
    PYTEST_RESULT=1
fi

# 2. Run mypy on main codebase
print_header "Running mypy on main codebase"
if MYPY_MAIN_OUTPUT=$(.venv/bin/mypy custom_components/ 2>&1); then
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

echo "============================================================"

# Overall result
TOTAL_ERRORS=$((PYTEST_RESULT + MYPY_MAIN_RESULT))

if [ $TOTAL_ERRORS -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests PASSED!${NC}"
    exit 0
else
    echo -e "${RED}💥 $TOTAL_ERRORS test(s) FAILED!${NC}"
    exit 1
fi