# Security policy

## Reporting a vulnerability

Report privately through GitHub's
[security advisory form](https://github.com/alpibrusl/content-kit/security/advisories/new),
or by email to **alfonso@alpibru.com** if you would rather not use GitHub.

Please do not open a public issue for a vulnerability. Expect an
acknowledgement within a week.

## What is in scope

This project reads files a user points it at and renders them.
The interesting attack surface is therefore what happens when those files are
hostile rather than merely malformed:

* Markdown or YAML that escapes its document — a book source that injects
  arbitrary HTML or script into a rendered EPUB or HTML build.
* Path handling in `book.yaml` — a `file:` entry that reads outside the book
  directory.
* Anything in the build that executes content rather than rendering it.

A crash on malformed input is a bug; report it as an issue. A crash that reads
or writes somewhere it should not is a vulnerability; report it privately.

## What is not

This is a small project maintained by one person in the open. There is no bug
bounty, no service-level agreement on fixes, and no embargo process beyond a
reasonable delay to prepare a patch. Fixes land on `main` and are described
plainly in the commit that carries them.

## Supported versions

`main` only. There are no maintained release branches.
