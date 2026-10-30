# Consilium · Консилиум

**English** | [Русский](https://github.com/hayrat9/consilium/blob/main/README.ru.md)

**A multidisciplinary AI council for Claude Code and Codex.** Generate ideas,
compare options, and examine a difficult question from different professional perspectives.
The skill instructions are currently in Russian. You can request an English response;
see the examples below. This is an English README, not a full translation of the skill.

Use it to choose a product strategy, design a learning experience, assess application
architecture, explore a research question, or challenge a proposal before launch.
The disciplines are selected for your task rather than fixed in advance.

## How it works

1. The facilitator clarifies the goal and proposes useful disciplines, their questions,
   an output format, and an estimate of resources.
2. **You approve the scope.** Named roles and discussion rounds do not start before approval.
3. The agent selects AI perspectives based on relevant work. Full depth checks sources
   from the last 30 days; light depth checks the changing facts relevant to the question.
   Missing evidence and inaccessible sources are reported explicitly.
4. Three rounds: independent positions or ideas → critique and development → review of the conclusion.
5. You receive options, supporting evidence, key disagreements, limitations, and a validation plan.

There are two modes. **Expert review** evaluates existing options. **Brainstorming**
generates ideas without early scoring, then develops and tests the strongest candidates.
The council is not a fixed cast of famous names and has no nine-role cap;
a larger approved council can run in waves.

Participants are **AI simulations of professional perspectives**, not invited human experts.
Agreement does not establish truth, and scores are not probabilities of success.
Sources, objections, and uncertainty matter more than a recognizable name.

## New in 1.2

- **Explicit outcomes:** a candidate for testing, support for an action within stated
  limits, no option passed the threshold, or insufficient evidence. Research can finish
  with an analysis without selecting an option.
- **Key claims:** distinguish claim type, supporting evidence and limits. A checked
  price is not evidence of purchases; choosing a cheap test does not establish demand.
- **Attempted refutation:** examine a key assumption, a simpler/no-action alternative
  and the strongest objection. No mandatory extra Red Team role is added.
- **R2 completion:** new sessions marked `protocol_version: "1.2"` cross-check the
  mapping, raw assessments and joined result. A complete flag alone is insufficient.
  No-eligible exceptions and stopping before R2 are separate cases. Legacy sessions
  remain readable with a warning and are not rewritten.

See the [outcome and verification contract](references/decision-checks.md) (Russian).
It checks recorded consistency, not authentic AI execution or decision quality.
Benefits over strong single-agent analysis and cost savings have not been measured.

Example outcomes:

> Insufficient evidence: published prices are available, but purchase evidence is missing.

> A candidate is selected for a cheap test; demand has not been established.

## Features from 1.1

- **Anonymous review in round 2:** a local helper creates separately shuffled packets,
  hides author/model metadata, and excludes self-authored and co-authored answers.
  Fresh reviewer contexts are needed for independent blind review; the helper cannot
  remove every identity clue in the text. Sequential review is labelled metadata-only.
- **Round viewer:** generate a standalone offline HTML report with positions side by
  side, amendments, disagreement, and unfinished cards. No AI calls are made.
- **Optional multi-model execution:** explicitly chosen by you, using models actually
  available in your environment. No model switching, paid fallback, or API setup happens
  automatically. This package contains a protocol, not a network orchestrator.
- **Light depth:** short substantive rounds and targeted checks of changing facts.
  Full depth retains the shared last-30-days scan. Scope approval and final review
  remain required in both. No measured quality or cost improvement is claimed.

Use `depth: light` in your request, or ask for multi-model execution with an estimate.
Review/brainstorm and full/light are independent choices. Existing 1.0 sessions remain
readable; do not rewrite completed rounds to make them appear anonymously reviewed.

```bash
python3 scripts/blind_review.py prepare /path/to/submissions.json --output-dir /path/to/review-packets
python3 scripts/blind_review.py join /path/to/review-packets/mapping.json /path/to/reviews.json --output /path/to/review-results.json
python3 scripts/render_rounds.py /path/to/session.json --output /path/to/rounds.html
```

See [anonymous review](references/blind-review.md) for input formats and
[execution modes](references/execution-modes.md) for the depth/model contract.
The author mapping stays with the facilitator until reviews close; do not send the
HTML viewer or full session to blind reviewers. Helpers do not call any model API.

## Installation

Download this repository using **Code → Download ZIP**, extract it, and open a terminal
in the directory containing `SKILL.md`. The same package supports both environments.
The commands below require Python 3.10+. On Windows, you can use `py -3` instead of `python3`.

### Claude Code

```bash
python3 scripts/install.py --platform claude
```

Installs to `~/.claude/skills/consilium/`. Invoke it inside Claude Code:

```text
/consilium Suggest new learning formats for a small online course. Respond in English.
```

### Codex CLI / IDE

```bash
python3 scripts/install.py --platform codex
```

Installs to `~/.agents/skills/consilium/`. Invoke it inside Codex:

```text
$consilium Compare three application architectures, considering maintenance and budget. Respond in English.
```

If the skill does not appear, restart your session. Where a skill selector is available,
select `consilium`. This is a local installation; availability in cloud sessions depends
on the product and its configuration.

### Install for a single project

```bash
python3 scripts/install.py --platform claude --project /path/to/project
python3 scripts/install.py --platform codex --project /path/to/project
```

These install to `.claude/skills/consilium/` or `.agents/skills/consilium/` within that project.
The installer makes no network requests, does not change model settings, and refuses
to overwrite an existing destination. Before updating, back up the previous installation
and move it aside yourself. Add `--dry-run` to preview the destination without writing files.

Without Python, manually copy the package directory to one of these locations under the
name `consilium`, preserving `SKILL.md`, `references/`, `assets/`, `scripts/`, and `agents/`.
The Python helpers still require Python to run.

## Example prompts

```text
Use Consilium to choose an approach for launching an educational project.
First propose the disciplines and explain what each contributes. Respond in English.

Use Consilium in brainstorming mode to find ways to reduce mistakes when handing
work between teams. Constraint: no new paid services. Respond in English.

Use Consilium to review these two hypotheses. Show the strongest objections
and an experiment that could distinguish between them. Respond in English.
```

`#council` can serve as a textual alias when the agent has access to the skill.
The hashtag does not install it or register a command in Telegram or another chat.

## Requirements and included tools

- An environment that reads Agent Skills. The protocol and helper code are not tied
  to a single model provider.
- Available search tools for recent sources. [last30days](https://github.com/mvanhorn/last30days-skill)
  is optional; when unavailable, the agent uses explicitly identified public search.
- Subagents are optional. When running sequentially, the agent reports the limited
  independence of the simulated perspectives. It does not automatically switch models.
- The Python helpers use only the standard library and work offline: session structure
  validation, scenario-based resource estimates, and comparison against weighted criteria.

```bash
python3 -B scripts/self_test.py
python3 -B scripts/test_review_tools.py
python3 -B scripts/test_install.py
python3 -B scripts/test_protocol.py
python3 scripts/session_check.py assets/session.template.json
python3 scripts/estimate_resources.py assets/estimate.example.json
```

The session template intentionally starts before scope approval. The estimate example
uses illustrative numbers, not measured costs for a real session. The validator checks
structure, not the authenticity of approval, the truth of sources, or the quality of ideas.

Model and tool usage depend on your plan. The skill does not grant access to other
people's accounts, install paid APIs, or publish results without an instruction to do so.
Keep your working sessions outside the skill repository.

## Try it and help improve it

Try Consilium on your own tasks and share what helped, what failed, and what could work better.
Contributions are welcome: clearer instructions, better evidence checks, more useful
formats, translations, examples, and improvements to the helpers.

- Use [Issues](https://github.com/hayrat9/consilium/issues) for feedback and reproducible problems.
  Include the environment, a non-sensitive example prompt, expected behavior, and actual behavior.
- Submit improvements as a pull request, or publish your own fork under the [MIT license](LICENSE).
  For code changes, run the relevant checks and describe what changed and how you verified it.
- If you publish an improved version or a more capable tool built on this approach,
  please share the link in the community thread where you found Consilium.
  You can also link it in a repository issue so others can discover it.

Keep disagreement, evidence, and uncertainty visible when improving the protocol.
Please remove personal information and credentials from shared examples.
Sharing a link back is a community request, not an additional license condition.

## Compatibility and validation

Installation paths and invocation syntax were checked on 2026-10-30 against the official
[Claude Code documentation](https://code.claude.com/docs/en/skills) and
[OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills).
File portability and the Python helpers have been tested. Native AI sessions in Claude Code
and Codex have not been tested; no claim is made about every product version, cloud
environment, or future model response.

Read more: [workflow](references/workflow.md),
[brainstorming](references/brainstorm.md),
[recent sources](references/fresh-industry-data.md),
[compatibility](references/runtime-compatibility.md).
These supporting documents are currently in Russian.

Version 1.2.0. [MIT](LICENSE). [Sources and credits](references/credits.md).
