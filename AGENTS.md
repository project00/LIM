leggi docs/project-plan.md per il contesto architetturale, usa Python 3.11+/FastAPI per daemon e server, JS vanilla per il widget, segui il contratto messaggi in §6
# Python Development Guidelines for Jules
## In the spirit of Salvatore "antirez" Sanfilippo's engineering philosophy (Redis, Kilo, hping)

This document defines how code should be written in this repository. It follows the
engineering values Sanfilippo has documented publicly for over a decade: relentless
simplicity, explicit design decisions written down as comments, and code optimized to
be *read*, not just to run. If a rule below ever conflicts with simplicity, simplicity wins.

Read `docs/project-plan.md` before starting any task in this repo — it contains the
architecture, the WebSocket/REST message contract, and the list of known issues in the
original PoC. Don't re-derive decisions that are already made there.

---

## 0. Guiding Philosophy (read this first)

- **Simplicity is the only sustainable strategy.** Every abstraction, every dependency,
  every clever trick is a bet that has to keep paying off for years. Before writing a
  complex solution, spend real time looking for the simplest one that could work —
  most of the time it's enough.
- **Complexity is usually a choice, not a fate.** It tends to come from an unwillingness
  to make a design trade-off, not from the problem itself. If something feels complex,
  the fix is almost never "add another layer" — go back and simplify the core idea.
- **Code is read far more than it is written.** Optimize naming, structure, and comments
  for the next person trying to understand what happens and why — not for how fast the
  code was to type.
- **Ship, then refine.** Working code you can iterate on beats a perfect design that
  never lands. Chasing perfection out of fear of judgment slows a project down more
  than it improves it.

---

## 1. Environment & Dependency Management

- Use `poetry` for dependency management. Never use raw `pip` unless explicitly told to.
- Target Python version: 3.11+.
- **Before adding a dependency, ask: could this be 20–30 lines of our own code instead?**
  A new library is a permanent commitment — new failure modes, new versions to track,
  more surface area to reason about. Check `pyproject.toml` first, and prefer the
  standard library whenever it's genuinely enough for the job.

## 2. Code Style & Formatting

- Strict adherence to PEP 8.
- Explicit, descriptive names. Avoid single-letter variables except as tight loop counters.
- Formatting: `black`. Linting: `ruff`. Max line length: 88 (Black default).
- Write functions like well-written prose: a clear, linear sequence a reader can follow
  top to bottom. If understanding one function means jumping through five files, the
  design has failed — not the reader.

## 3. Type Hinting & Validation

- Static type hints (PEP 484) on every function signature and class attribute.
- `typing.Any` only as a genuine last resort — prefer a `Union` or a `Generic` that
  actually says what the code does.
- Use `Pydantic` (v2) for data validation, parsing, and settings management. It replaces
  a whole category of hand-written validation code — exactly the kind of dependency
  worth taking.

## 4. Architecture & Design

- **Composition over inheritance.** Prefer no hierarchy at all over a shallow one that
  exists only to look "object-oriented."
- **A function should do one coherent, nameable thing — but don't fragment code into a
  maze of one-line helpers just to satisfy a rule.** A slightly longer function that
  reads as one clear story beats ten tiny functions that force the reader to jump
  around to reconstruct the flow.
- **No DI frameworks or IoC containers.** Pass dependencies explicitly as constructor
  or function arguments. Explicit is simple; magic wiring is not — if you can't `grep`
  for where an object comes from, it's too clever.
- `asyncio` for I/O-bound work, plain sync code for CPU-bound work. Never block the
  event loop with synchronous I/O.
- **The first design of a new module deserves disproportionate care.** Don't commit to
  the first version that compiles — sketch two or three alternatives, even as throwaway
  code, before settling. The initial structure shapes everything that grows from it later.

## 5. Error Handling & Logging

- Never use a bare `except:`. Always catch specific exceptions.
- Never suppress an exception silently — log it or re-raise it, always with context.
- Use the standard `logging` library. No `print()` in production code.
- Structure log messages with contextual data (e.g. `request_id`, `action`) so a failure
  is diagnosable from the log line alone, without needing to reproduce it.

## 6. Testing Strategy

- Framework: `pytest`. Mocking: `pytest-mock`. Tests live in `tests/`, mirroring the
  app's structure.
- **Don't chase 100% coverage as a metric.** Put real effort into tests that actually
  catch bugs: edge cases, state transitions, async paths, malformed input — the code
  most likely to break in ways you wouldn't notice just by reading it. A trivial getter
  doesn't need a test; a router deciding between local and remote execution does.
- For anything stateful or with many input combinations (parsers, the Smart Router,
  data transforms), a handful of well-chosen edge-case tests beats one happy-path test —
  that's where real bugs hide.

## 7. Documentation & Comments

- Google-style docstrings for all public modules, classes, and functions: Description,
  Args, Returns, Raises.
- **Every non-trivial module or function opens with a short Design Note**: what problem
  it solves, which approach was chosen, and briefly what simpler alternative was
  rejected and why. This matters more than any inline comment — it lets the next reader
  trust that the simplicity they see was a decision, not an oversight.
- Inline comments explain **why**, never **what**. If a comment just restates what the
  next line does, delete it and make the code clearer instead.
- If you can't explain a piece of logic in two or three plain sentences, it isn't ready
  to commit — rewrite it until it is.

## 8. Working on This Codebase as an AI Agent

- Favor small, reviewable pull requests scoped to one user story at a time over broad
  multi-file rewrites — this mirrors how the project's backlog is structured in
  `docs/project-plan.md` §14.
- When a design choice isn't specified, pick the simplest option that satisfies the
  requirement and state that choice explicitly in the PR description, rather than
  introducing a new abstraction speculatively.
- Run `pytest` and `ruff check` before opening a PR. A PR that doesn't pass its own
  tests is not a draft to review — it's unfinished work.
