# Contributing

## Reporting a problem

Open an issue with:

- your mower's model and the integration's version;
- what you did, what you expected and what happened instead;
- the integration's debug log around the problem. To get it, add this to
  `configuration.yaml` and restart Home Assistant:

  ```yaml
  logger:
    logs:
      custom_components.dreame_mower: debug
  ```

  Then reproduce the problem and copy the lines from **Settings → System →
  Logs** (or `home-assistant.log`). Remove your account name and device IDs
  before you attach them.

## Changing the code

You need Python 3.14, Node.js 22 or newer, and Git. Earlier Python versions
cannot install the Home Assistant release the tests run against; Node.js runs
the map card's tests.

```bash
git clone https://github.com/antondaubert/dreame-mower.git
cd dreame-mower
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
npm ci
```

Run all checks before you open a pull request:

```bash
./run_test.sh
```

It runs the tests with pytest, type checks the integration with mypy, and
runs the map card's tests. Add
tests for what you change: a test should fail without your change and pass
with it.

Keep a pull request to one change, and describe what it changes and why.
