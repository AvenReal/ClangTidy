# Coding Style Guide

This document lists all the coding style rules checked by `src/style_checker.py` along with their short descriptions.

---

## Summary of Rules

| Rule ID | Rule Name                 | Severity | Short Description                                                                                                    |
| ------- | ------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------- |
| `1.1`   | `cast`                    | Error    | 0 explicit C casts allowed (configurable via `--max-casts`)                                                          |
| `1.2`   | `lines.empty`             | Error    | No two consecutive empty lines                                                                                       |
| `1.3`   | `export.other`            | Error    | At most 1 non-function exported symbol (global variable) per source file (configurable via `--max-exported-globals`) |
| `1.4`   | `export.fun`              | Error    | At most 10 exported functions per source file (configurable via `--max-exported-funcs`)                              |
| `1.5`   | `fun.arg.count`           | Error    | Functions MUST NOT take more than 4 arguments (configurable via `--max-func-args`)                                   |
| `1.6`   | `fun.len`                 | Error    | Function body must not exceed 30 lines (configurable via `--max-func-lines`, `--line`, or `--lines`)                 |
| `1.7`   | `fun.proto.void`          | Error    | Prototypes with no arguments MUST specify void                                                                       |
| `1.8`   | `else_if.indent`          | Error    | `else if` must appear on the same line                                                                               |
| `1.9`   | `fun.proto.layout`        | Error    | Exported function prototypes must appear in header files, not source files; source files must include their header   |
| `1.10`  | `fun.sep.line`            | Error    | Function definitions must be separated by one empty line                                                             |
| `1.11`  | `gcc.builtins`            | Error    | No GCC builtins (`__builtin_*`)                                                                                      |
| `1.12`  | `cpp.guard`               | Error    | Header guards format (`#ifndef`, `#define`, `#endif` comment)                                                        |
| `1.13`  | `cpp.if`                  | Error    | `#else` and `#endif` must be followed by a comment describing the condition                                          |
| `1.14`  | `cpp.include.filetype`    | Error    | Included files must be `.h` or `.cxx` (no including `.c` files)                                                      |
| `1.15`  | `cpp.mark`                | Error    | Preprocessor `#` must be on the first column                                                                         |
| `1.16`  | `cpp.digraphs`            | Error    | No digraphs/trigraphs (`<%`, `%>`, `<:`, `:>`, etc.)                                                                 |
| `1.17`  | `decl.single`             | Error    | At most 1 declaration per line (except in `for`, configurable via `--max-decls-per-line`)                            |
| `1.18`  | `decl.vla`                | Error    | No variable-length arrays (VLAs)                                                                                     |
| `1.19`  | `keyword.goto`            | Error    | No `goto`                                                                                                            |
| `1.20`  | `stat.asm`                | Error    | No inline assembly (`asm` / `__asm__`)                                                                               |
| `1.21`  | `ctrl.empty`              | Error    | Single-line loop body on next line, if empty must be `continue;`                                                     |
| `1.22`  | `ctrl.switch`             | Error    | `switch` statement must contain a `default` case                                                                     |
| `1.23`  | `ctrl.switch.fallthrough` | Error    | Fallthrough in `switch` case must have `/* FALLTHROUGH */`                                                           |
| `1.24`  | `ctrl.switch.indentation` | Error    | `case` on same column as `switch` `{`                                                                                |
| `1.25`  | `ctrl.switch.padding`     | Error    | No space before `:` in `case`/`default`                                                                              |
| `1.26`  | `decl.point`              | Error    | Pointer `*` next to variable/function name, not type                                                                 |
| `1.27`  | `ctrl.do_while`           | Error    | `} while (...);` must appear on the same line                                                                        |
| `1.28`  | `exp.args`                | Error    | No space between function name and `(` in call/decl                                                                  |
| `1.29`  | `keyword.arg`             | Error    | Functional keywords enclosed in parentheses (e.g. `sizeof(...)`)                                                     |
| `1.30`  | `semicolon`               | Error    | No space before semicolon, space after semicolon if followed by statement                                            |
| `1.31`  | `stat.sep`                | Error    | Comma operator not used outside `for`                                                                                |
| `1.32`  | `file.dos`                | Error    | No CRLF line endings                                                                                                 |
| `1.33`  | `file.terminate`          | Error    | Empty line at the end of file must exist                                                                             |
| `1.34`  | `file.trailing`           | Error    | No trailing whitespace                                                                                               |
| `1.35`  | `name.prefix.global`      | Error    | Global variables must start with `g_`                                                                                |
| `1.36`  | `name.struct`             | Error    | Structure and union names MUST NOT be aliased using `typedef`                                                        |
| `2.1`   | `fun.len`                 | Warning  | Function body should not exceed 25 lines (configurable via `--warn-func-lines` or `--warn-lines`)                    |
| `2.2`   | `indent.level`            | Warning  | Indentation should not exceed 3 levels / 12 spaces (configurable via `--max-indent-level`)                           |
| `2.3`   | `cpp.include.order`       | Warning  | Include blocks (same-name header, system headers, local headers) separated by empty line, alphabetical               |
| `2.4`   | `enum.comma`              | Warning  | Enum last element must have a trailing comma                                                                         |
| `2.5`   | `file.deadcode`           | Warning  | No commented-out code                                                                                                |
| `2.6`   | `comment.multi`           | Warning  | Multi-line comment delimiters on own line, intermediary lines start with `**`                                        |

---

## Detailed Rules by Category

### 1. Errors (1.X)

- **`1.1 cast` (Error)**: Explicit C casts (e.g., `(int)x`) are forbidden, with the allowed cast budget configurable via `--max-casts` (default 0). The limit applies across all checked non-test files; files under `tests/` are excluded from counting and violations.
- **`1.2 lines.empty` (Error)**: Consecutive empty lines are not permitted within code.
- **`1.3 export.other` (Error)**: At most 1 non-function exported symbol (global variable) per source file (configurable via `--max-exported-globals`).
- **`1.4 export.fun` (Error)**: At most 10 exported functions per source file (configurable via `--max-exported-funcs`), reported once per offending source file with total count.
- **`1.5 fun.arg.count` (Error)**: Functions must not accept more than 4 arguments (configurable via `--max-func-args`).
- **`1.6 fun.len` (Error)**: Function bodies must not exceed 30 lines (configurable via `--max-func-lines`, `--line`, or `--lines`).
- **`1.7 fun.proto.void` (Error)**: Functions taking no arguments must explicitly specify `void` in their parameter list (e.g., `int foo(void)`).
- **`1.8 else_if.indent` (Error)**: `else if` must be placed on the same line.
- **`1.9 fun.proto.layout` (Error)**: Prototypes of exported functions must be in header files, not source files; source files defining exported functions must include their corresponding header.
- **`1.10 fun.sep.line` (Error)**: Function definitions must be separated by exactly one empty line.
- **`1.11 gcc.builtins` (Error)**: Builtin GCC functions (prefixed with `__builtin_`) must not be used.
- **`1.12 cpp.guard` (Error)**: Header files must be protected with header guards conforming to `#ifndef GUARD_`, `#define GUARD_`, and `#endif /* ! GUARD_ */`.
- **`1.13 cpp.if` (Error)**: `#else` and `#endif` directives must be followed by a comment specifying the condition.
- **`1.14 cpp.include.filetype` (Error)**: Only header files (`.h` or `.cxx`) may be included; including `.c` files is prohibited.
- **`1.15 cpp.mark` (Error)**: The preprocessor directive token `#` must start on column 1.
- **`1.16 cpp.digraphs` (Error)**: Digraphs and trigraphs (such as `<%`, `%>`, `<:`, `:>`) are forbidden.
- **`1.17 decl.single` (Error)**: At most one declaration is permitted per line, except within `for` loop headers (configurable via `--max-decls-per-line`).
- **`1.18 decl.vla` (Error)**: Variable-length arrays (VLAs) are not allowed.
- **`1.19 keyword.goto` (Error)**: The `goto` keyword is forbidden.
- **`1.20 stat.asm` (Error)**: Inline assembly (`asm` or `__asm__`) is forbidden.
- **`1.21 ctrl.empty` (Error)**: Single-line loop bodies must be on the next line; an empty loop body must consist of `continue;`.
- **`1.22 ctrl.switch` (Error)**: Every `switch` statement must include a `default` case.
- **`1.23 ctrl.switch.fallthrough` (Error)**: Intentional fallthrough between `case` blocks must be documented with a `/* FALLTHROUGH */` comment.
- **`1.24 ctrl.switch.indentation` (Error)**: `case` labels must align on the same column as the opening brace `{` of the `switch`.
- **`1.25 ctrl.switch.padding` (Error)**: No whitespace is allowed before the `:` in `case` and `default` statements.
- **`1.26 decl.point` (Error)**: The pointer asterisk `*` must be attached to the identifier, not the type (e.g., `int *ptr`, not `int* ptr`).
- **`1.27 ctrl.do_while` (Error)**: In `do ... while` constructs, `} while (...);` must be on the same line as the closing brace.
- **`1.28 exp.args` (Error)**: No whitespace is allowed between a function name and the opening parenthesis `(` in declarations or calls.
- **`1.29 keyword.arg` (Error)**: Arguments to functional keywords like `sizeof(...)`, `typeof(...)`, and `_Alignof(...)` must be enclosed in parentheses.
- **`1.30 semicolon` (Error)**: No whitespace before a semicolon; a space is required after a semicolon when followed by a statement.
- **`1.31 stat.sep` (Error)**: The comma operator `,` must not be used outside of `for` loop headers.
- **`1.32 file.dos` (Error)**: CRLF (`\r\n`) line endings are forbidden; use LF (`\n`).
- **`1.33 file.terminate` (Error)**: Files must terminate with a newline character.
- **`1.34 file.trailing` (Error)**: Trailing whitespace at the end of lines is forbidden.
- **`1.35 name.prefix.global` (Error)**: Global variables must have names prefixed with `g_`.
- **`1.36 name.struct` (Error)**: Structures and unions must not be aliased using `typedef`.

### 2. Warnings (2.X)

- **`2.1 fun.len` (Warning)**: Function bodies should not exceed 25 lines (configurable via `--warn-func-lines` or `--warn-lines`).
- **`2.2 indent.level` (Warning)**: Code indentation should not exceed 3 levels / 12 spaces (configurable via `--max-indent-level`), reported per contiguous line range.
- **`2.3 cpp.include.order` (Warning)**: Include directives must be organized in blocks (same-name header, system headers, local headers) separated by an empty line, each sorted alphabetically.
- **`2.4 enum.comma` (Warning)**: The last enumerator in an `enum` definition must have a trailing comma.
- **`2.5 file.deadcode` (Warning)**: Commented-out code (or `#if 0` blocks) must not be left in files.
- **`2.6 comment.multi` (Warning)**: In multi-line comments, delimiters `/*` and `*/` must reside on their own lines, intermediary lines must start with `**`, and consecutive single-line or line-continued comments must use block format.

---

## CLI Options

`src/style_checker.py` supports the following command-line options:

- `path`: Target file or directory to recursively scan for `.c` and `.h` files.
- `--line <N>`, `--lines <N>`, `--max-func-lines <N>`: Maximum function length for error (default: `30`).
- `--warn-func-lines <N>`, `--warn-lines <N>`: Function length limit for warning (default: `25`).
- `--max-exported-globals <N>`, `--max-exported-other <N>`: Maximum non-function exported symbols per file (default: `1`).
- `--max-exported-funcs <N>`, `--max-exported-functions <N>`: Maximum exported functions per source file (default: `10`).
- `--max-func-args <N>`, `--max-args <N>`: Maximum number of function arguments (default: `4`).
- `--max-indent-level <N>`, `--max-indent <N>`: Maximum indentation level in levels of 4 spaces (default: `3` levels / 12 spaces).
- `--max-decls-per-line <N>`, `--max-decls <N>`: Maximum declarations per line (default: `1`).
- `--max-casts <N>`: Maximum allowed explicit C casts across non-test files (default: `0`).
- `--ignore-warnings`, `--ignore-w`: Suppress warning checks.
