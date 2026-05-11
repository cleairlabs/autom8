# AGENTS

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.


# Instructions
- Never mix whitespace changes with functionality changes.
- Use the code convention specified below.


## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.


## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.


## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.


# Python Style
- Do not split a line into multiple lines unless the line length exceeds 150 characters.
- Use verbose variable names.
- When a list literal or call spans multiple lines, put the first item on the same line as the opening `[` or `()` whenever practical.
- Do not leave a closing `]` on its own line for these multi-line lists.
- Do not leave a closing `)` on its own line for multi-line calls, comprehensions, or expressions when the statement can be formatted cleanly without it.
- Dictionary literals are exempt from this rule. It is fine for multi-line dictionaries to use a trailing `}` on its own line.

Preferred:

```python
record_entities = [row["customer_name"],
                   row["account_owner"],
                   row["csm"]]
```

Also preferred:

```python
result = some_call(first_arg,
                   second_arg,
                   third_arg)
```

Allowed for dictionaries:

```python
FILES = {
    "company": "company.jsonl",
    "customers": "customers.jsonl",
}
```
