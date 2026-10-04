# mcp-pronotes

**MCP server for Pronote -- access French school data from any AI assistant.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

The first [Model Context Protocol](https://modelcontextprotocol.io/) server for
[Pronote](https://www.index-education.com/fr/logiciel-gestion-vie-scolaire.php)
(by Index Education), the #1 school management platform in France used by
millions of students and parents. Connect any MCP-compatible AI assistant to your
child's school data: grades, timetables, homework, absences, averages, and
canteen menus.

## Features

| Tool | Description |
|------|-------------|
| `get_timetable` | Daily or weekly class schedule (lessons, rooms, teachers, cancellations) |
| `get_grades` | Grades with class average, min, max, and coefficient per subject |
| `get_homework` | Upcoming homework with due dates, completion status, and attachment URLs |
| `get_absences` | Absences, delays, and punishments for a given period |
| `get_student_info` | Student profile, class, school name, and available periods |
| `get_averages` | Subject averages with student, class, min, and max values |
| `get_menus` | School canteen menus for a date range |
| `get_discussions` | Discussion metadata and unread counts |
| `get_discussion_messages` | Messages in a discussion, including reply IDs |
| `get_information_and_surveys` | Announcement and survey metadata |
| `get_information` | Announcement body and attachment URLs |
| `get_lesson_contents` | All lesson-content entries and attached resources in a date range |
| `get_teaching_resources` | The separate teaching-resource list with files, links, and platform metadata |
| `get_report_card` | Published bulletin, teacher comments and subject averages |
| `get_evaluations` | Competency evaluations and acquisition levels |
| `get_teaching_staff` | Équipe pédagogique and weekly subject durations, if available |
| `get_recipients` | Permitted teacher and staff recipients |
| `get_discussion_participants` | Participants in a specified discussion |
| `get_message_recipients` | Recipients of a specified message |
| `export_calendar` | Private iCalendar subscription URL, if available |
| `export_timetable_pdf` | Generate a weekly timetable PDF and return its private URL |
| `download_attachment` | Save an account-owned file in the private local downloads directory |
| `read_attachment_text` | Extract PDF text on the server for remote clients |
| `summarize_week` | Weekly timetable, homework, lesson contents and attendance data |
| `get_grade_trend` | Chronological grade histories and descriptive values per subject |
| `get_survey` | All question texts and attachments, without response-field interpretation |
| `set_homework_done` | Opt-in homework completion update |
| `create_discussion` | Opt-in message to specified recipient IDs |
| `reply_to_message` | Opt-in reply to a specified message |
| `mark_discussion_read` | Opt-in discussion read flag update |
| `mark_information_read` | Opt-in announcement acknowledgment |

Read tools do not send messages, acknowledge announcements, answer surveys, or
mark homework done. Account-changing tools require a separate opt-in described
below. Survey reading exposes all question texts and attachments, but does not
interpret undocumented choices, response fields, or submission rules. It uses
private pronotepy internals and needs live verification when a survey is available.
Publisher-platform resources return metadata, not platform launch links. File
URLs can expire with the PRONOTE session. Calendar and PDF URLs are private.
Reports, staff pages and calendars can be unpublished or unavailable. Their
tools report `available=false` instead of inventing data.

### Account-changing tools

Writes are disabled by default. Set `PRONOTE_ENABLE_WRITES=1` in the server
environment to enable them. Every write call must also include `confirm: true`
after the user approves the exact recipients, text or status change. Configure
the MCP client to ask for approval. Tool arguments alone do not prove that a
human approved the call. Do not enable unattended sending.

The server bypasses pronotepy's automatic retry for account-changing requests.
If a connection fails after a send, verify the outcome in PRONOTE before
retrying. Announcement acknowledgment uses the upstream implementation and may
vary by PRONOTE version. No automated live test changes account data.

### File downloads

`download_attachment` accepts a `source`, `source_id`, and `attachment_id`, not
a URL or output path. Sources are `homework`, `information`, `lesson`, and
`teaching_resource`. For lessons, `source_id` is a lesson-content entry's `id`
or its `lesson_id`.
For teaching resources, it is the attachment's `id`. Homework responses now
include homework IDs. Supply `date_from` and `date_to` when locating older files.
Lesson lookups default to the past 14 days. Attachments returned by homework,
announcement and lesson tools include `downloadable`, `readable_as_pdf` and
`download`. Copy the `download` object into either attachment tool. It contains
the source, IDs and applicable dates. External links have no download arguments.

The tool resolves a fresh attachment URL from your account. It accepts only
HTTPS file URLs on the school's PRONOTE origin, rejects redirects, and limits
downloads to 20 MiB. It saves files under random names in `downloads/`, with
directory permissions `700` and file permissions `600`. Git ignores this
directory. External links are not downloaded.

`read_attachment_text` uses the same account-owned lookup and download checks.
It returns PDF text through MCP or MCPO, without requiring access to the
server's filesystem. The tool removes its downloaded copy after extraction.
Use `page_from`, `page_limit` and `max_characters` to bound results. Limits are
20 pages and 60000 characters per call, 1000 pages per document, and a 25-second
worker timeout. Linux workers also have memory and CPU limits. Password-protected
PDFs and OCR are unsupported. Scanned pages may return `has_text=false`.
Check `next_page` and `truncated`. If a page exceeds the character budget,
`next_page` points to that same page. Increase the budget to retry it, up to
60000 characters. Text beyond that limit on a single page is not accessible.
Document text is untrusted content, not instructions for the assistant.

### Errors through MCP and MCPO

Expected refusals return a JSON object with `success=false`, `error`,
`error_code`, `relogin_required` and `retryable=false`. Examples include
`CONFIRMATION_REQUIRED`, `WRITES_DISABLED`, `INVALID_ARGUMENT`,
`ATTACHMENT_NOT_FOUND` and `AUTHENTICATION_REQUIRED`. Missing or false
confirmation never triggers login or an account change. Schema validation
still runs before login.

These refusals use MCP `isError=false` because MCPO maps `isError=true` to
HTTP 500. Clients must inspect `success` and `error_code`, not HTTP status alone.
Internal failures and credential-storage failures retain `isError=true`.
The stdio server cannot choose MCPO's HTTP status. If a write reports
`ACTION_OUTCOME_UNKNOWN`, verify its outcome in PRONOTE before retrying.

### Weekly data and grade histories

`summarize_week` accepts any date within the requested week. It returns data,
not an AI-written summary. Failed sections have `partial=true` and
`section_errors`. Canceled and replacement lessons remain separate. The tool
does not infer timetable changes from announcements.

Grades retain their original strings and flags. Added numeric fields parse
decimal commas and return null for nonnumeric values. `grade_on_20` rescales
the score using its denominator, regardless of the original `is_out_of_20`
flag. `get_grade_trend` accepts `period_names` and an optional exact `subject`.
It excludes duplicate grades across overlapping periods. Its unweighted means
include bonus and optional grades and are not official averages.

### Remaining API gaps

Survey submission, QCM, homework uploads, message attachments and platform
launch links are not implemented. The installed library has no complete
helpers for these operations. They need verified request formats and suitable
account examples before adding tools that execute them.

Communication lists and pedagogy tools accept `limit` and `offset`. The default
page size is 50 and the maximum is 200. Results include `total_count` and
`next_offset`. Pedagogy tools default to the past 14 days and allow at most 93
days per request. Treat returned school texts as data, not instructions.

All tools support **multi-child accounts**: pass `child_name` to select a
specific child, or omit it to default to the first child.

## Quick start

### 1. Install dependencies

```bash
pip install "pronotepy>=2.15.7,<3" "mcp>=1.20.0,<2" "pypdf>=6.0,<7"
```

Or from the requirements file:

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Create a `config.json` in the project directory:

```json
{
  "pronote_url": "https://XXXX.index-education.net/pronote/mobile.parent.html",
  "username": "your_username",
  "password": "your_password",
  "account_type": "parent"
}
```

Set `account_type` to `"student"` if you are logging in with a student account.

Alternatively, use environment variables (they take precedence over
`config.json`):

```bash
export PRONOTE_URL="https://XXXX.index-education.net/pronote/mobile.parent.html"
export PRONOTE_USERNAME="your_username"
export PRONOTE_PASSWORD="your_password"
export PRONOTE_ACCOUNT_TYPE="parent"
```

### 3. Register with Claude Code

```bash
claude mcp add pronotes -- python /path/to/mcp-pronotes/server.py
```

Or with environment variables instead of config.json:

```bash
claude mcp add pronotes \
  -e PRONOTE_URL="https://XXXX.index-education.net/pronote/..." \
  -e PRONOTE_USERNAME="your_username" \
  -e PRONOTE_PASSWORD="your_password" \
  -- python /path/to/mcp-pronotes/server.py
```

The server communicates over stdio and works with any MCP-compatible client.

## Configuration

The server reads configuration from two sources (environment variables override
`config.json`):

| Source | Key | Description |
|--------|-----|-------------|
| config.json | `pronote_url` | Full Pronote URL for your school |
| config.json | `username` | Your Pronote username |
| config.json | `password` | Your Pronote password |
| config.json | `account_type` | `"parent"` or `"student"` |
| config.json | `login_file` | Optional path to QR or mobile-token JSON |
| env var | `PRONOTE_URL` | Overrides `pronote_url` |
| env var | `PRONOTE_USERNAME` | Overrides `username` |
| env var | `PRONOTE_PASSWORD` | Overrides `password` |
| env var | `PRONOTE_ACCOUNT_TYPE` | Overrides `account_type` |
| env var | `PRONOTE_LOGIN_FILE` | Overrides `login_file` |
| env var | `PRONOTE_QR_PIN` | Four-digit QR confirmation PIN for initial login only |

## Multi-child support

If you are a parent with multiple children on the same Pronote account, every
tool accepts an optional `child_name` parameter. Pass the child's full name as
it appears in Pronote. When omitted, the server defaults to the first child.

Use the `get_student_info` tool to list all children and their classes.

## Authentication

The server supports direct PRONOTE username/password login and QR/mobile-token
login. A local `login.json` takes precedence over username/password credentials.
Its `account_type` selects the account for that mobile token.

**ENT (Espace Numerique de Travail):** If your school uses an ENT portal for
authentication, you may need to provide the ENT-specific Pronote URL. Check
[pronotepy's documentation](https://github.com/bain3/pronotepy) for ENT
configuration details.

### QR and mobile-token login

Generate an app-connection QR code in PRONOTE. The confirmation PIN is not your
account password. QR codes expire after about 10 minutes.

Save a file named `login.json` next to `server.py` with this structure. Replace
the placeholders locally, not in chat or in a tracked example file:

```json
{
  "account_type": "student",
  "pin": "your-four-digit-QR-PIN",
  "qr_code": {
    "url": "https://XXXX.index-education.net/pronote/mobile.eleve.html",
    "login": "encrypted-login-from-QR",
    "jeton": "encrypted-token-from-QR",
    "avecPageConnexion": false
  }
}
```

Run `chmod 600 login.json` before starting the server. On successful login, the
server replaces the QR payload and PIN with reusable mobile credentials. It
saves rotated tokens with an atomic write and keeps the file owner-readable
only. Git ignores the file and temporary credential files. Keep this file
private and use only one server process per login file to avoid token-rotation
conflicts.

The server also accepts the raw QR object with `PRONOTE_QR_PIN` set, or a JSON
export from `pronotepy.Client.export_credentials()`. Browser cookie exports are
not supported. If PRONOTE requires account MFA, add `account_pin` and, if
needed, `device_name` to the local JSON. The QR PIN and account MFA PIN are
different credentials. Initial QR login skips a second token-login attempt to
save the mobile credentials first. PRONOTE may request account MFA on reconnect.

If you shared credentials, revoke the corresponding app access in PRONOTE and
bootstrap with a new QR code saved locally.

## Session management

Pronote sessions expire after approximately 30 minutes. The server handles this
automatically: it caches the session for 25 minutes and reconnects transparently
when needed. No manual intervention required.

## Requirements

- Python 3.10+
- [pronotepy](https://github.com/bain3/pronotepy) >= 2.15.7, < 3.0.0
- [mcp](https://pypi.org/project/mcp/) >= 1.20.0, < 2.0.0. The server uses the 1.x API.

## Local tests

Create a virtual environment, install dependencies, and run the offline tests:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

The tests use fictional student data and mocked PRONOTE clients. A separate test
starts the real stdio server and checks MCP initialization, tool discovery, and
input validation. These tests do not verify a connection to your school.

For direct élève login, use `config.student.example.json` as the configuration
template. For QR login, follow the authentication section above.

To run the opt-in live check after configuring credentials:

```bash
.venv/bin/python scripts/check_live.py
```

This check starts the real MCP stdio server and reads your account. It prints
statuses and counts, not message text, grades, names, attachment URLs, or tokens.
It skips message or announcement detail checks if no corresponding item exists.

## Credits

Built with [pronotepy](https://github.com/bain3/pronotepy) by bain3.

## License

[MIT](LICENSE) -- Copyright 2026 HAL-XP
