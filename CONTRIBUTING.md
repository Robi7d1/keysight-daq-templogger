# Contributing

Thanks for taking some time and looking through! This is a small project
that slowly spun out of the frustration of using unstable paid-license
software way too much

## Bugs and features

Open an issue. If it's a bug, a description of what happened and what
you expected to happen is enough — a stack trace or a screenshot is a
bonus but not required.

If it's a feature idea, describe the use case as well rather than just the
implementation. "I want to monitor N channels until they pass goal value"
is more useful than "add a dropdown to the settings dialog."

**A note on scope:** this tool does one thing — log temperatures from a
DAQ970A-family instrument — and I'd like to keep it that way. Larger
features that push it toward being a general measurement framework are
unlikely to land here, because that's what a separate project is for. I
intend to build that generalized version when time allows. Bug fixes,
performance improvements, and changes that make the existing tool more robust
or simpler to use are all welcome.

## Pull requests

For small fixes — a typo, a one-line bug, a doc clarification — just
send the PR. No need to open an issue first.

For anything larger — a new feature, a refactor, a change that touches
the instrument communication or the session log format — please open
an issue first so we can talk it through before you spend time on it.

Keep PRs focused on one change. It makes them a lot easier to review
(and presumably quicker to respond to on my end).

## Testing

The pure-logic parts of the code (session log parsing, the filter,
channel-address generation etc.) can be tested without an instrument
attached. If your change touches those, describe how you tested it in
the PR description.

The instrument communication path and real-time behavior can't be
tested without hardware. I no longer have day-to-day access to a
DAQ970A, which means verifying a change needs sending it to the lab it
was originally built for. Because of that, testing and fixing a change
can take a while between submission and merge, as it is also dependent 
not only on me but also the availability in the lab.

Any solutions that seem sensible but haven't yet been tested or
could be considered too specific to either device hardware or software 
will live separate from the main program as an opt-in patch for users
to decide on, rather than being merged into the main program.

## What to expect

This is a one-person project and I might take a while to respond. If
something's urgent for you, forking is always an option — the license
allows it, and you don't need to ask.

## License

Contributions come in under the same license as the rest of the
project: [GPL v3](LICENSE).
