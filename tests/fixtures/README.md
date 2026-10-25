# Recorded fixtures

`<endpoint>/<case>.json`, written by `/record-fixture` through
`xippios.core.testing.record`, never by hand. Credentials are scrubbed on write; still
grep before committing:

```bash
grep -rniE 'api[_-]?key|token|secret' tests/fixtures
```
