# Perfection Cycle #1
- Timestamp (UTC): 2026-04-18T13:58:40.306454+00:00
- Consecutive greens: 0
- Gates run: 6
| Gate | Status | Duration (s) | Summary |
|------|--------|--------------|---------|
| env_sanity | PASS | 0.02 | python>=3.11 + pip available |
| static_backend | PASS | 1.52 | ruff + format + mypy clean |
| static_frontend | PASS | 4.47 | tsc + eslint clean |
| unit_frontend | PASS | 6.44 | Duration  5.52s (transform 1.63s, setup 13.11s, collect 9.13s, tests 4.04s, environment 34.80s, prepare 4.59s) |
| a11y | PASS | 54.26 | [1A[2K  11 passed (53.1s) |
| visual | FAIL | 48.52 | visual diff |

## Failure details

### visual

- signature: `visual:rc=1`

```
ue to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:14112) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:9840) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:9840) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:30428) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:30428) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:27008) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:27008) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:41132) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:41132) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:26800) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
[1A[2K(node:26800) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.
(Use `node --trace-warnings ...` to show where the warning was created)
```
