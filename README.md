# C Coding Style Checker

A standalone static analysis style checker for C projects (`.c` and `.h` files), powered by a custom C tokenizer and structural analyzer.

## Overview

`src/style_checker.py` recursively scans a target directory (or checks a single `.c`/`.h` file) against 42 coding style rules partitioned into:

- **Errors (`1.1` – `1.36`)**: Mandatory style rules (`[[Error]]`) that cause a non-zero exit status (`1`).
- **Warnings (`2.1` – `2.6`)**: Advisory style rules (`[[Warning]]`) that do not fail the exit code (`0` when no errors are present) and can be suppressed with `--ignore-warnings`.

Violations are reported with file locations and contextual descriptions formatted for terminal inspection.

## Installation

### As a python script

```sh
curl https://raw.githubusercontent.com/AvenReal/ClangTidy/refs/heads/master/src/style_checker.py ./style_checker.py
```

### As a shell command

```sh
curl https://raw.githubusercontent.com/AvenReal/ClangTidy/refs/heads/master/src/style_checker.py ~/.local/bin/style_checker
```

### As a git precommit

```sh
curl https://raw.githubusercontent.com/AvenReal/ClangTidy/refs/heads/master/src/style_checker.py ~/.local/bin/style_checker
echo "style_checker ./ [list of arguments] " >> ./git/hooks/pre-commit
```

## Directory Layout

```text
.
├── README.md                          # Project overview, usage, and test instructions
├── coding_style.md                    # Complete specification of all Error (1.x) and Warning (2.x) rules
└── src/
    └── style_checker.py               # Main CLI style checker and C structural analyzer
```

## Dependencies

- **Python 3** (3.8+ recommended; uses only the Python standard library)

## CLI Usage

```bash
python3 src/style_checker.py [OPTIONS] <path>
```

`<path>` can be either a root directory (scanned recursively for `.c` and `.h` files, skipping dotfiles/directories) or a single `.c`/`.h` file.

### Options

| Flag(s)                                              | Default | Description                                                                |
| :--------------------------------------------------- | :------ | :------------------------------------------------------------------------- |
| `-h`, `--help`                                       | —       | Show help message and exit                                                 |
| `--line`, `--lines`, `--max-func-lines N`            | `30`    | Maximum allowed lines in a function body before reporting `1.6 fun.len`    |
| `--warn-func-lines`, `--warn-lines N`                | `25`    | Soft warning limit for function body length (`2.1 fun.len`)                |
| `--max-exported-globals`, `--max-exported-other N`   | `1`     | Maximum non-function exported symbols per source file (`1.3 export.other`) |
| `--max-exported-funcs`, `--max-exported-functions N` | `10`    | Maximum exported functions per source file (`1.4 export.fun`)              |
| `--max-func-args`, `--max-args N`                    | `4`     | Maximum parameters per function (`1.5 fun.arg.count`)                      |
| `--max-indent-level`, `--max-indent N`               | `3`     | Maximum indentation depth in units of 4 spaces (`2.2 indent.level`)        |
| `--max-decls-per-line`, `--max-decls N`              | `1`     | Maximum declarations on a single line outside `for` (`1.17 decl.single`)   |
| `--max-casts N`                                      | `0`     | Maximum explicit C casts across non-test source/header files (`1.1 cast`)  |
| `--IgnoreW`, `--ignore-w`                            | `False` | Suppress all warning checks (`2.x`)                                        |

### Examples

Run all checks on a directory:

```bash
python3 src/style_checker.py path/to/c_project
```

Run checks on a single source file:

```bash
python3 src/style_checker.py path/to/c_project/main.c
```

Run checks with warnings suppressed and custom cast budget:

```bash
python3 src/style_checker.py --IgnoreW --max-casts 2 path/to/c_project
```

Configure custom function length limits:

```bash
python3 src/style_checker.py --max-func-lines 40 --warn-func-lines 30 path/to/c_project
```

### Exit Codes

- `0`: Clean run or warnings only (no Errors found).
- `1`: One or more Errors found.
- `2`: Invalid command-line arguments or syntax.

## Rules Summary

See [coding_style.md](coding_style.md) for the complete specification of all 42 rules.

### Standard Errors (`1.1` – `1.36`)

All 36 Error rules result in a non-zero exit status (`1`) if violated:

- `1.1 cast`: 0 explicit C casts allowed across non-test files (configurable via `--max-casts`)
- `1.2 lines.empty`: No two consecutive empty lines
- `1.3 export.other`: At most 1 non-function exported symbol (global variable) per source file (configurable via `--max-exported-globals`)
- `1.4 export.fun`: At most 10 exported functions per source file (configurable via `--max-exported-funcs`)
- `1.5 fun.arg.count`: Functions must not take more than 4 arguments (configurable via `--max-func-args`)
- `1.6 fun.len`: Function body must not exceed 30 lines (configurable via `--max-func-lines`, `--line`, or `--lines`)
- `1.7 fun.proto.void`: Function prototypes with no arguments must explicitly specify `void`
- `1.8 else_if.indent`: `else if` must appear on the same line
- `1.9 fun.proto.layout`: Exported function prototypes must appear in header files, not source files; source files must include their header
- `1.10 fun.sep.line`: Function definitions must be separated by one empty line
- `1.11 gcc.builtins`: No GCC builtins (`__builtin_*`)
- `1.12 cpp.guard`: Header guards format (`#ifndef`, `#define`, `#endif` comment)
- `1.13 cpp.if`: `#else` and `#endif` must be followed by a comment describing the condition
- `1.14 cpp.include.filetype`: Included files must be `.h` or `.cxx` (no including `.c` files)
- `1.15 cpp.mark`: Preprocessor `#` must be on the first column
- `1.16 cpp.digraphs`: No digraphs or trigraphs (`<%`, `%>`, `<:`, `:>`, etc.)
- `1.17 decl.single`: At most 1 declaration per line (except in `for`, configurable via `--max-decls-per-line`)
- `1.18 decl.vla`: No variable-length arrays (VLAs)
- `1.19 keyword.goto`: No `goto`
- `1.20 stat.asm`: No inline assembly (`asm` / `__asm__`)
- `1.21 ctrl.empty`: Single-line loop body on next line, if empty must be `continue;`
- `1.22 ctrl.switch`: `switch` statement must contain a `default` case
- `1.23 ctrl.switch.fallthrough`: Fallthrough in `switch` case must have `/* FALLTHROUGH */`
- `1.24 ctrl.switch.indentation`: `case` on same column as `switch` `{`
- `1.25 ctrl.switch.padding`: No space before `:` in `case`/`default`
- `1.26 decl.point`: Pointer `*` next to variable/function name, not type
- `1.27 ctrl.do_while`: `} while (...);` must appear on the same line
- `1.28 exp.args`: No space between function name and `(` in call/decl
- `1.29 keyword.arg`: Functional keywords enclosed in parentheses (e.g. `sizeof(...)`)
- `1.30 semicolon`: No space before semicolon, space after semicolon if followed by statement
- `1.31 stat.sep`: Comma operator not used outside `for`
- `1.32 file.dos`: No CRLF line endings
- `1.33 file.terminate`: Empty line at the end of file must exist
- `1.34 file.trailing`: No trailing whitespace
- `1.35 name.prefix.global`: Global variables must start with `g_`
- `1.36 name.struct`: Structure and union names MUST NOT be aliased using `typedef`

### Standard Warnings (`2.1` – `2.6`)

All 6 Warning rules provide advisory feedback, exit with `0` when no errors exist, and can be suppressed via `--ignore-warnings`:

- `2.1 fun.len`: Soft warning on function length, default > 25 lines (configurable via `--warn-func-lines` or `--warn-lines`)
- `2.2 indent.level`: Indentation depth must not exceed 3 levels / 12 spaces (configurable via `--max-indent-level`)
- `2.3 cpp.include.order`: Include blocks (same-name header, system headers, local headers) separated by empty line, alphabetical
- `2.4 enum.comma`: Trailing comma on the last enumerator in `enum` definitions
- `2.5 file.deadcode`: No commented-out code (`//`, `/* */`, and `#if 0`)
- `2.6 comment.multi`: Multi-line comment delimiters on own line, intermediary lines start with `**`
