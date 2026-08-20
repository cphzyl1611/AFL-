# Secret Scanner Semantics

`scripts/secret_scan.py` is the release-gate scanner for repository, evidence,
delivery, and helper/test scopes. Reports contain locations, categories, and
reasons only; candidate values are never serialized.

## Serialization

Reports are serialized once with UTF-8 and `ensure_ascii=False`. The exact byte
string checked for candidate values is the byte string written to disk. A
candidate found in that canonical representation raises a serialization error
before the output file is created.

## Fail-closed report guard

`main()` collects the credential values held by the current process
environment via `runtime_secret_values()` and feeds them to the guard. Both the
stdout payload and the on-disk report are checked against those values before
anything is emitted, so a live credential can never reach either sink. Variable
names ending in `PASS`, `PASSWORD`, `PASSWD`, `SECRET`, `TOKEN`, `API_KEY`,
`AUTHORIZATION`, or `CREDENTIAL(S)` are treated as credential-bearing; `PWD` and
`OLDPWD` are shell state and are excluded. Blank, whitespace-only, and
placeholder values carry no secret and are dropped.

## File accounting and status precedence

Files larger than 10 MiB, containing NUL bytes, not decodable as UTF-8, or not
readable are recorded in `files_skipped` with `path` and a non-secret `reason`.
`files_scanned` counts only successfully inspected files.

Status is resolved in this order, and the order is deliberate:

| Condition | Status |
|---|---|
| `real_secret_findings > 0` | `FAIL` |
| otherwise, required scope with any skipped file | `INCOMPLETE` |
| otherwise | `PASS` |

`FAIL` outranks `INCOMPLETE`. A confirmed secret is a failure even when part of
the requested scope could not be inspected; `INCOMPLETE` only ever means "clean
so far, but coverage was not total". Optional scopes may report `PASS` when
skipped files are still listed and no finding is present.

## Classification

Credential-shaped values are classified as `REAL_SECRET` unless they are an
explicit placeholder or a known logger namespace such as
`alfresco.repo.admin`. Account/password context is checked independently, so
the logger suppression cannot hide a real value beside `account` or
`password`.

### Explicit credential contexts — no complexity heuristic

A value assigned to `password`, `passwd`, `pwd`, `secret`, `token`, or
`authorization` is sensitive regardless of length, case mix, digits, or
punctuation. A short all-lowercase dictionary word in a password field is a
real credential, not a weak one to be waved through. Detection must never
depend on how "complex" the value looks.

Suppression stays narrow and value-specific: `alfresco.repo.admin` is a logger
namespace, but the word `admin` is not globally suppressed — in a password
field it is a finding.

### What counts as a committed literal

Precision comes from requiring a *literal*, never from grading the value:

- The value must be **quoted**, or the file must be a config format
  (`.env`, `.ini`, `.cfg`, `.conf`, `.properties`, `.yaml`, `.yml`, `.toml`)
  where bare `key=value` is the norm. An unquoted value in a source file is an
  expression — `char *token = strtok(...)` is code, not a credential.
- The separator must be an assignment or mapping (`=`, `:=`, `:`), never a
  comparison. `if (secret == NULL)` is not a credential.
- A leading `$` or `%` marks a variable reference (`$PWD`, `%s`), not a value.
- Values shorter than 3 characters, containing whitespace, containing code
  punctuation (`()[]{}<>"'`+backslash+backtick+pipe), starting with `$`/`%`/an
  operator, containing `${...}`, or reading `null`/`none`/`true`/`false` are
  not literals.
- Runtime lookups (`os.getenv(...)`, `os.environ[...]`, `process.env`) are
  references, not committed values.
