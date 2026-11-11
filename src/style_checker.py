#!/usr/bin/env python3
"""
style_checker.py - Coding Style Checker.

Checks the validity of the coding style based on Coding Style Standard (v1.0.0).
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

SEVERITY_ORDER = {
    "Error": 0,
    "Warning": 1,
}


class RuleViolation:
    def __init__(
        self,
        rule_id: str,
        severity: str,
        description: str,
        filepath: str,
        line: Optional[int],
        message: str,
        end_line: Optional[int] = None,
    ):
        self.rule_id = rule_id
        self.severity = severity  # "Error", "Warning"
        self.description = description
        self.filepath = filepath
        self.line = line
        self.end_line = end_line
        self.message = message

    def sort_key(self):
        m = re.match(r"^(\d+)\.(\d+)(?:\s+(.*))?$", self.rule_id)
        if m:
            sec, subsec, name = int(m.group(1)), int(m.group(2)), m.group(3) or ""
            rule_sort = (sec, subsec, name)
        else:
            rule_sort = (999, 999, self.rule_id)
        return (
            SEVERITY_ORDER.get(self.severity, 99),
            rule_sort,
            self.filepath,
            self.line if self.line is not None else 0,
            self.end_line if self.end_line is not None else (self.line if self.line is not None else 0),
        )


C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local"
}

STANDARD_TYPES = {
    "void", "char", "short", "int", "long", "float", "double", "signed",
    "unsigned", "size_t", "ssize_t", "off_t", "ptrdiff_t", "intptr_t",
    "uintptr_t", "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t",
    "uint16_t", "uint32_t", "uint64_t", "int_least8_t", "uint_least8_t",
    "int_fast8_t", "uint_fast8_t", "intmax_t", "uintmax_t", "bool", "_Bool",
    "_Complex", "_Imaginary", "FILE", "DIR", "va_list", "jmp_buf", "sigjmp_buf",
    "fpos_t", "div_t", "ldiv_t", "lldiv_t", "imaxdiv_t", "max_align_t",
    "wchar_t", "wint_t", "mbstate_t"
}

TYPE_QUALIFIERS = {"const", "volatile", "restrict", "__restrict", "__restrict__", "signed", "unsigned", "short", "long", "_Atomic"}

TRIGRAPHS = ["??=", "??(", "??/", "??)", "??'", "??<", "??!", "??>", "??-"]
DIGRAPHS = ["<%", "%>", "<:", ":>", "%:%:", "%:"]


class Token:
    def __init__(self, kind: str, value: str, line: int, col: int, end_line: int, end_col: int):
        self.kind = kind
        self.value = value
        self.line = line
        self.col = col
        self.end_line = end_line
        self.end_col = end_col

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, L{self.line}:{self.col})"


def skip_balanced(tokens: Sequence[Token], idx: int, open_tok: str = "{", close_tok: str = "}") -> int:
    """Advance past matching balanced delimiters starting at idx (where tokens[idx].value == open_tok).
    Returns the index immediately following close_tok, or len(tokens) if unbalanced."""
    n = len(tokens)
    if idx >= n or tokens[idx].value != open_tok:
        return idx
    depth = 1
    idx += 1
    while idx < n and depth > 0:
        val = tokens[idx].value
        if val == open_tok:
            depth += 1
        elif val == close_tok:
            depth -= 1
        idx += 1
    return idx


def find_statement_end(tokens: Sequence[Token], start_idx: int) -> int:
    """Find index of terminating semicolon at top-level brace depth starting at start_idx."""
    n = len(tokens)
    k = start_idx
    b_depth = 0
    while k < n:
        v = tokens[k].value
        if v == "{":
            b_depth += 1
        elif v == "}":
            b_depth -= 1
        elif v == ";" and b_depth <= 0:
            return k
        k += 1
    return n


def skip_expression_to_comma_or_semi(tokens: Sequence[Token], start_idx: int) -> int:
    """Advance past an expression until finding a comma or semicolon at zero nesting depth."""
    n = len(tokens)
    k = start_idx
    dp = db = dk = 0
    while k < n:
        v = tokens[k].value
        if v == "(":
            dp += 1
        elif v == ")":
            dp -= 1
        elif v == "{":
            db += 1
        elif v == "}":
            db -= 1
        elif v == "[":
            dk += 1
        elif v == "]":
            dk -= 1
        elif v in (",", ";") and dp <= 0 and db <= 0 and dk <= 0:
            break
        k += 1
    return k


def is_c_type(name: str, known_typedefs: Optional[Set[str]] = None) -> bool:
    if name in STANDARD_TYPES or name in TYPE_QUALIFIERS:
        return True
    if known_typedefs and name in known_typedefs:
        return True
    if name.startswith("t_") or name.endswith("_t"):
        return True
    return False


def tokenize_c(code: str) -> List[Token]:
    tokens = []
    i = 0
    n = len(code)
    line = 1
    col = 1

    def advance():
        nonlocal i, line, col
        ch = code[i]
        i += 1
        if ch == '\n':
            line += 1
            col = 1
        else:
            col += 1
        return ch

    multi_ops = (
        ">>=", "<<=", "...", "->", "++", "--", "<<", ">>", "<=", ">=",
        "==", "!=", "&&", "||", "+=", "-=", "*=", "/=", "%=", "&=",
        "^=", "|="
    )

    while i < n:
        start_line = line
        start_col = col
        ch = code[i]

        # Horizontal whitespace fast-path
        if ch in ' \t':
            j = i + 1
            while j < n and code[j] in ' \t':
                j += 1
            col += (j - i)
            i = j
            continue

        if ch == '\n':
            i += 1
            line += 1
            col = 1
            continue

        if ch == '\r':
            i += 1
            col += 1
            continue

        # Line comment
        if ch == '/' and i + 1 < n and code[i + 1] == '/':
            val = ""
            while i < n:
                if code[i] == '\\' and i + 1 < n and code[i + 1] == '\n':
                    val += advance() + advance()
                    continue
                if code[i] == '\\' and i + 2 < n and code[i + 1:i + 3] == '\r\n':
                    val += advance() + advance() + advance()
                    continue
                if code[i] == '\n':
                    break
                val += advance()
            tokens.append(Token("COMMENT_LINE", val, start_line, start_col, line, col - 1))
            continue

        # Block comment
        if ch == '/' and i + 1 < n and code[i + 1] == '*':
            val = advance() + advance()
            while i < n and code[i:i + 2] != '*/':
                val += advance()
            if i < n:
                val += advance() + advance()
            tokens.append(Token("COMMENT_BLOCK", val, start_line, start_col, line, col - 1))
            continue

        # String literal
        if ch == '"':
            val = advance()
            while i < n and code[i] != '"':
                if code[i] == '\\' and i + 1 < n:
                    val += advance()
                val += advance()
            if i < n:
                val += advance()
            tokens.append(Token("STRING", val, start_line, start_col, line, col - 1))
            continue

        # Char literal
        if ch == "'":
            val = advance()
            while i < n and code[i] != "'":
                if code[i] == '\\' and i + 1 < n:
                    val += advance()
                val += advance()
            if i < n:
                val += advance()
            tokens.append(Token("CHAR", val, start_line, start_col, line, col - 1))
            continue

        # Preprocessor directive
        if ch == '#':
            val = advance()
            deferred_comments: List[Token] = []
            while i < n:
                if code[i] == '\\' and i + 1 < n and code[i + 1] == '\n':
                    val += advance() + advance()
                    continue
                if code[i] == '\\' and i + 2 < n and code[i + 1:i + 3] == '\r\n':
                    val += advance() + advance() + advance()
                    continue
                if code[i] == '\n':
                    break
                if code[i] in ('"', "'"):
                    q = code[i]
                    val += advance()
                    while i < n and code[i] != q and code[i] != '\n':
                        if code[i] == '\\' and i + 1 < n:
                            if code[i + 1] == '\n':
                                val += advance() + advance()
                                continue
                            if code[i + 1:i + 3] == '\r\n':
                                val += advance() + advance() + advance()
                                continue
                            val += advance()
                        val += advance()
                    if i < n and code[i] == q:
                        val += advance()
                    continue
                if code[i:i + 2] == '//':
                    while i < n and code[i] != '\n':
                        if code[i] == '\\' and i + 1 < n and code[i + 1] == '\n':
                            val += advance() + advance()
                            continue
                        if code[i] == '\\' and i + 2 < n and code[i + 1:i + 3] == '\r\n':
                            val += advance() + advance() + advance()
                            continue
                        val += advance()
                    continue
                if code[i:i + 2] == '/*':
                    nl_pos = code.find('\n', i + 2)
                    close_pos = code.find('*/', i + 2)
                    if close_pos == -1 or (nl_pos != -1 and close_pos > nl_pos):
                        c_start_line, c_start_col = line, col
                        c_val = advance() + advance()
                        while i < n and code[i:i + 2] != '*/':
                            c_val += advance()
                        if i < n and code[i:i + 2] == '*/':
                            c_val += advance() + advance()
                        deferred_comments.append(
                            Token("COMMENT_BLOCK", c_val, c_start_line, c_start_col, line, col - 1)
                        )
                        val += c_val
                        continue
                    while i < n and code[i:i + 2] != '*/':
                        val += advance()
                    if i < n and code[i:i + 2] == '*/':
                        val += advance() + advance()
                    continue
                val += advance()
            tokens.append(Token("PREPROCESSOR", val, start_line, start_col, line, col - 1))
            tokens.extend(deferred_comments)
            continue

        # Trigraphs
        tri = code[i:i + 3]
        if tri in TRIGRAPHS:
            val = advance() + advance() + advance()
            tokens.append(Token("TRIGRAPH", val, start_line, start_col, line, col - 1))
            continue

        # Digraphs
        di4 = code[i:i + 4]
        if di4 == "%:%:":
            val = advance() + advance() + advance() + advance()
            tokens.append(Token("DIGRAPH", val, start_line, start_col, line, col - 1))
            continue
        di2 = code[i:i + 2]
        if di2 in DIGRAPHS:
            val = advance() + advance()
            tokens.append(Token("DIGRAPH", val, start_line, start_col, line, col - 1))
            continue

        # Identifiers and keywords fast-path
        if ch.isalpha() or ch == '_':
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] == '_'):
                j += 1
            val = code[i:j]
            col += (j - i)
            i = j
            kind = "KEYWORD" if val in C_KEYWORDS else "IDENTIFIER"
            tokens.append(Token(kind, val, start_line, start_col, line, col - 1))
            continue

        # Numbers fast-path
        if ch.isdigit():
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in '._'):
                j += 1
            val = code[i:j]
            col += (j - i)
            i = j
            tokens.append(Token("NUMBER", val, start_line, start_col, line, col - 1))
            continue

        # Multi-character operators fast-path
        matched_op = None
        for op in multi_ops:
            if code.startswith(op, i):
                matched_op = op
                break
        if matched_op:
            op_len = len(matched_op)
            i += op_len
            col += op_len
            tokens.append(Token("OPERATOR", matched_op, start_line, start_col, line, col - 1))
            continue

        # Single character punctuator
        ch = advance()
        tokens.append(Token("PUNCTUATOR", ch, start_line, start_col, start_line, start_col))

    return tokens


def extract_declarators_from_decl(tokens: List[Token], is_type_func) -> List[Tuple[str, int]]:
    """Extracts declared variable names from a declaration statement, properly skipping initializers."""
    var_names: List[Tuple[str, int]] = []
    n = len(tokens)
    i = 0

    spec_qualifiers = {
        "typedef", "static", "extern", "const", "volatile", "register", "auto",
        "inline", "restrict", "_Noreturn", "_Thread_local", "_Atomic",
        "__extension__", "__inline", "__inline__", "__restrict", "__restrict__",
    }
    builtin_type_words = {
        "void", "char", "short", "int", "long", "float", "double",
        "signed", "unsigned", "bool", "_Bool", "_Complex", "_Imaginary",
    }

    saw_type = False
    while i < n:
        val = tokens[i].value
        if val == "extern" and i + 1 < n and tokens[i + 1].kind == "STRING":
            i += 2
            continue
        if val in spec_qualifiers:
            i += 1
            continue
        if val in ("_Alignas", "typeof", "__typeof__", "__typeof", "__attribute__", "__attribute"):
            i += 1
            while i < n and tokens[i].value == "(":
                i = skip_balanced(tokens, i, "(", ")")
            if val in ("typeof", "__typeof__", "__typeof"):
                saw_type = True
            continue
        if val in ("struct", "union", "enum"):
            saw_type = True
            i += 1
            if i < n and tokens[i].kind == "IDENTIFIER":
                i += 1
            if i < n and tokens[i].value == "{":
                i = skip_balanced(tokens, i, "{", "}")
            continue
        if val in builtin_type_words:
            saw_type = True
            i += 1
            continue
        if not saw_type and is_type_func(val):
            saw_type = True
            i += 1
            continue
        if not saw_type and tokens[i].kind == "IDENTIFIER":
            if i + 1 < n and (
                tokens[i + 1].kind == "IDENTIFIER"
                or tokens[i + 1].value in ("*", "(")
                or tokens[i + 1].value in spec_qualifiers
            ):
                saw_type = True
                i += 1
                continue
        break

    def parse_direct_declarator_name(idx: int) -> Tuple[Optional[Tuple[str, int]], int]:
        while idx < n and (tokens[idx].value == "*" or tokens[idx].value in TYPE_QUALIFIERS):
            idx += 1
        if idx >= n:
            return None, idx
        decl_id: Optional[Tuple[str, int]] = None
        if tokens[idx].kind == "IDENTIFIER" and tokens[idx].value not in C_KEYWORDS and not is_type_func(tokens[idx].value):
            decl_id = (tokens[idx].value, tokens[idx].line)
            idx += 1
        elif tokens[idx].kind == "IDENTIFIER" and tokens[idx].value not in C_KEYWORDS:
            # Allow variable names that accidentally match an external typedef if followed by declarator punctuation
            if idx + 1 >= n or tokens[idx + 1].value in (
                "=", ",", ";", "[", "(", ":", ")",
                "__attribute__", "__attribute", "asm", "__asm__", "__asm",
            ):
                decl_id = (tokens[idx].value, tokens[idx].line)
                idx += 1
        elif tokens[idx].value == "(":
            # Parenthesized declarator such as (*fp)(...) or (*arr)[10]
            end_paren = skip_balanced(tokens, idx, "(", ")")
            inner_id, _ = parse_direct_declarator_name(idx + 1)
            if inner_id is not None:
                decl_id = inner_id
            idx = end_paren

        while idx < n:
            if tokens[idx].value == "[":
                idx = skip_balanced(tokens, idx, "[", "]")
            elif tokens[idx].value == "(":
                idx = skip_balanced(tokens, idx, "(", ")")
            else:
                break
        return decl_id, idx

    while i < n:
        decl_id, i = parse_direct_declarator_name(i)
        if decl_id is None:
            break
        var_names.append(decl_id)

        while i < n and tokens[i].value in ("__attribute__", "__attribute", "asm", "__asm__", "__asm"):
            i += 1
            while i < n and tokens[i].value == "(":
                i = skip_balanced(tokens, i, "(", ")")

        if i < n and tokens[i].value in (":", "="):
            i = skip_expression_to_comma_or_semi(tokens, i + 1)

        if i < n and tokens[i].value == ",":
            i += 1
            continue
        break

    return var_names



def has_top_level_specifier(tokens: List[Token], spec: str) -> bool:
    dp = db = dk = 0
    for t in tokens:
        if t.value == "(":
            dp += 1
        elif t.value == ")":
            if dp > 0:
                dp -= 1
        elif t.value == "{":
            db += 1
        elif t.value == "}":
            if db > 0:
                db -= 1
        elif t.value == "[":
            dk += 1
        elif t.value == "]":
            if dk > 0:
                dk -= 1
        elif dp == 0 and db == 0 and dk == 0 and t.value == spec:
            return True
    return False


class StyleChecker:
    def __init__(
        self,
        target_files: List[Path],
        max_func_lines: int = 30,
        warn_func_lines: int = 25,
        max_exported_globals: int = 1,
        max_exported_funcs: int = 10,
        max_func_args: int = 4,
        max_indent_level: int = 3,
        max_decls_per_line: int = 1,
        max_casts: int = 0,
    ):
        self.target_files = target_files
        self.max_func_lines = max_func_lines
        self.warn_func_lines = warn_func_lines
        self.max_exported_globals = max_exported_globals
        self.max_exported_funcs = max_exported_funcs
        self.max_func_args = max_func_args
        self.max_indent_level = max_indent_level
        self.max_decls_per_line = max_decls_per_line
        self.max_casts = max_casts
        self.project_casts: List[Tuple[str, int, str]] = []
        self._checked_files: Set[Path] = set()
        self._finalized: bool = False
        self.violations: List[RuleViolation] = []
        self.known_typedefs: Set[str] = set()
        self._file_cache: Dict[Path, Tuple[bytes, str, List[Token]]] = {}

    def _get_file_data(self, path: Path) -> Optional[Tuple[bytes, str, List[Token]]]:
        cached = self._file_cache.get(path)
        if cached is not None:
            return cached
        try:
            raw_bytes = path.read_bytes()
        except Exception:
            return None
        text = raw_bytes.decode("utf-8", errors="replace")
        tokens = tokenize_c(text)
        entry = (raw_bytes, text, tokens)
        self._file_cache[path] = entry
        return entry

    def add_violation(
        self,
        rule_id: str,
        severity: str,
        description: str,
        filepath: str,
        line: Optional[int],
        message: str,
        end_line: Optional[int] = None,
    ):
        self.violations.append(
            RuleViolation(rule_id, severity, description, filepath, line, message, end_line=end_line)
        )

    def finalize_violations(self):
        if self._finalized:
            return
        self._finalized = True
        if len(self.project_casts) > self.max_casts:
            desc = (
                "0 explicit C casts allowed"
                if self.max_casts == 0
                else f"At most {self.max_casts} explicit C casts allowed"
            )
            for fpath, line, cast_type in self.project_casts[self.max_casts:]:
                self.add_violation(
                    "1.1 cast",
                    "Error",
                    desc,
                    fpath,
                    line,
                    f"Explicit C cast to '({cast_type})' found",
                )

    def collect_global_info(self):
        """Pre-scan all files to collect typedef names for accurate cast and decl checking."""
        is_known = lambda name: is_c_type(name, self.known_typedefs)
        for path in self.target_files:
            data = self._get_file_data(path)
            if data is None:
                continue
            _, _, tokens = data
            code_toks = [
                t for t in tokens
                if t.kind not in ("COMMENT_LINE", "COMMENT_BLOCK", "PREPROCESSOR")
            ]
            n = len(code_toks)
            i = 0
            brace_depth = 0
            paren_depth = 0
            while i < n:
                t = code_toks[i]
                if t.value == "typedef" and paren_depth == 0:
                    end_idx = find_statement_end(code_toks, i + 1)
                    stmt_toks = code_toks[i:end_idx + 1] if end_idx < n else code_toks[i:end_idx]
                    for name, _ in extract_declarators_from_decl(stmt_toks, is_known):
                        self.known_typedefs.add(name)
                    i = end_idx + 1
                    continue
                if t.value == "{":
                    brace_depth += 1
                elif t.value == "}":
                    brace_depth = max(0, brace_depth - 1)
                elif t.value == "(":
                    paren_depth += 1
                elif t.value == ")":
                    paren_depth = max(0, paren_depth - 1)
                i += 1

    def check_file(self, path: Path):
        self._checked_files.add(path)
        filepath_str = str(path)
        is_header = path.suffix == ".h"
        is_source = path.suffix == ".c"

        data = self._get_file_data(path)
        if data is None:
            return
        raw_bytes, text, tokens = data

        # 1.32 file.dos (MUST): No CRLF line endings
        raw_lines_bytes = raw_bytes.split(b"\n")
        check_lines_bytes = raw_lines_bytes[:-1] if raw_bytes.endswith(b"\n") else raw_lines_bytes
        for idx, line_bytes in enumerate(check_lines_bytes, 1):
            if line_bytes.endswith(b"\r") or b"\r" in line_bytes:
                self.add_violation(
                    "1.32 file.dos",
                    "Error",
                    "No CRLF line endings",
                    filepath_str,
                    idx,
                    "CRLF line terminator found",
                )

        # 1.33 file.terminate (MUST): Empty line at the end of file must exist
        if len(raw_bytes) == 0 or not raw_bytes.endswith(b"\n"):
            last_line = max(1, len(raw_lines_bytes))
            self.add_violation(
                "1.33 file.terminate",
                "Error",
                "Empty line at the end of file must exist",
                filepath_str,
                last_line,
                "Empty line at the end of file must exist",
            )

        lines = text.split("\n")
        lines_content = lines[:-1] if text.endswith("\n") else lines

        # 1.34 file.trailing (MUST): No trailing whitespace
        for idx, line in enumerate(lines_content, 1):
            line_no_cr = line.rstrip("\r")
            if line_no_cr.endswith(" ") or line_no_cr.endswith("\t"):
                self.add_violation(
                    "1.34 file.trailing",
                    "Error",
                    "No trailing whitespace",
                    filepath_str,
                    idx,
                    "Trailing whitespace found",
                )

        # Empty lines at the end or beginning of file MUST be accepted per user requirement.
        # Rule 6.3 file.spurious for blank lines at beginning/end is removed.

        # 1.2 lines.empty (MUST): No two consecutive empty lines (outside beginning/end of file)
        non_empty_indices = [i for i, l in enumerate(lines_content) if l.strip() != ""]
        if non_empty_indices:
            first_non_empty = non_empty_indices[0]
            last_non_empty = non_empty_indices[-1]
            for idx in range(first_non_empty, last_non_empty):
                if lines_content[idx].strip() == "" and lines_content[idx + 1].strip() == "":
                    self.add_violation(
                        "1.2 lines.empty",
                        "Error",
                        "No two consecutive empty lines",
                        filepath_str,
                        idx + 2,
                        "Consecutive empty line",
                    )

        # 2. Check comments
        non_comment_lines: Set[int] = set()
        for tok in tokens:
            if tok.kind not in ("COMMENT_BLOCK", "COMMENT_LINE"):
                for ln in range(tok.line, tok.end_line + 1):
                    non_comment_lines.add(ln)

        single_comment_only_lines: Set[int] = set()
        for tok in tokens:
            if tok.kind == "COMMENT_BLOCK":
                # 2.6 comment.multi (SHOULD): Multi-line comment delimiters on own line, intermediary lines start with **
                is_closed = len(tok.value) >= 4 and tok.value.endswith("*/")
                if tok.end_line > tok.line or not is_closed:
                    start_line_text = lines_content[tok.line - 1]
                    pos_start = max(0, tok.col - 1)
                    if start_line_text[pos_start:pos_start + 2] != "/*":
                        pos_start = start_line_text.find("/*")
                    before_delim = start_line_text[:pos_start] if pos_start != -1 else ""
                    after_delim = start_line_text[pos_start + 2:] if pos_start != -1 else ""
                    if before_delim.strip() != "" or after_delim.strip() != "":
                        self.add_violation(
                            "2.6 comment.multi",
                            "Warning",
                            "Multi-line comment delimiters on own line, intermediary lines start with **",
                            filepath_str,
                            tok.line,
                            "Opening delimiter '/*' must appear on its own line",
                        )

                    if is_closed and tok.end_line - 1 < len(lines_content):
                        end_line_text = lines_content[tok.end_line - 1]
                        pos_end = tok.end_col - 2
                        if pos_end < 0 or end_line_text[pos_end:pos_end + 2] != "*/":
                            pos_end = end_line_text.rfind("*/")
                        before_end_delim = end_line_text[:pos_end] if pos_end != -1 else ""
                        after_end_delim = end_line_text[pos_end + 2:] if pos_end != -1 else ""
                        if before_end_delim.strip() != "" or after_end_delim.strip() != "":
                            self.add_violation(
                                "2.6 comment.multi",
                                "Warning",
                                "Multi-line comment delimiters on own line, intermediary lines start with **",
                                filepath_str,
                                tok.end_line,
                                "Closing delimiter '*/' must appear on its own line",
                            )
                    else:
                        report_end_line = max(tok.line, min(tok.end_line, len(lines_content)))
                        self.add_violation(
                            "2.6 comment.multi",
                            "Warning",
                            "Multi-line comment delimiters on own line, intermediary lines start with **",
                            filepath_str,
                            report_end_line,
                            "Closing delimiter '*/' must appear on its own line",
                        )

                    inter_end = tok.end_line if is_closed else min(tok.end_line + 1, len(lines_content) + 1)
                    for inter_l in range(tok.line + 1, inter_end):
                        if inter_l - 1 >= len(lines_content):
                            continue
                        inter_text = lines_content[inter_l - 1].strip()
                        if not inter_text.startswith("**"):
                            self.add_violation(
                                "2.6 comment.multi",
                                "Warning",
                                "Multi-line comment delimiters on own line, intermediary lines start with **",
                                filepath_str,
                                inter_l,
                                "Intermediary line in multi-line comment must start with '**'",
                            )
                else:
                    if tok.line not in non_comment_lines:
                        single_comment_only_lines.add(tok.line)

                # 2.5 file.deadcode (SHOULD): No commented-out code in block comment
                comment_lines = tok.value.split("\n")
                for c_idx, c_line in enumerate(comment_lines, tok.line):
                    stripped_c = c_line.strip()
                    if stripped_c.startswith("/*"):
                        stripped_c = stripped_c[2:].strip()
                    if stripped_c.endswith("*/"):
                        stripped_c = stripped_c[:-2].strip()
                    if stripped_c.startswith("**"):
                        stripped_c = stripped_c[2:].strip()
                    elif stripped_c.startswith("*"):
                        stripped_c = stripped_c[1:].strip()

                    if self._is_commented_code(stripped_c):
                        self.add_violation(
                            "2.5 file.deadcode",
                            "Warning",
                            "No commented-out code",
                            filepath_str,
                            c_idx,
                            f"Commented-out code detected: '{stripped_c}'",
                        )

            elif tok.kind == "COMMENT_LINE":
                if tok.end_line > tok.line:
                    self.add_violation(
                        "2.6 comment.multi",
                        "Warning",
                        "Multi-line comment delimiters on own line, intermediary lines start with **",
                        filepath_str,
                        tok.line,
                        "Multi-line comment must use '/* ... */' block format instead of line-continued '//'",
                    )
                elif tok.line not in non_comment_lines:
                    single_comment_only_lines.add(tok.line)

                for c_idx, c_line in enumerate(tok.value.split("\n"), tok.line):
                    stripped_c = c_line.strip()
                    if stripped_c.startswith("//"):
                        stripped_c = stripped_c[2:].strip()
                    if stripped_c.endswith("\\"):
                        stripped_c = stripped_c[:-1].strip()
                    if self._is_commented_code(stripped_c):
                        self.add_violation(
                            "2.5 file.deadcode",
                            "Warning",
                            "No commented-out code",
                            filepath_str,
                            c_idx,
                            f"Commented-out code detected: '{stripped_c}'",
                        )

        # Consecutive comment-only single-line comments (// or /* ... */) form a multi-line comment
        if single_comment_only_lines:
            sorted_clines = sorted(single_comment_only_lines)
            run_start = sorted_clines[0]
            prev_cl = sorted_clines[0]
            for cl in sorted_clines[1:]:
                if cl == prev_cl + 1:
                    prev_cl = cl
                else:
                    if prev_cl > run_start:
                        self.add_violation(
                            "2.6 comment.multi",
                            "Warning",
                            "Multi-line comment delimiters on own line, intermediary lines start with **",
                            filepath_str,
                            run_start,
                            "Consecutive single-line comments should use '/* ... */' multi-line comment format",
                        )
                    run_start = cl
                    prev_cl = cl
            if prev_cl > run_start:
                self.add_violation(
                    "2.6 comment.multi",
                    "Warning",
                    "Multi-line comment delimiters on own line, intermediary lines start with **",
                    filepath_str,
                    run_start,
                    "Consecutive single-line comments should use '/* ... */' multi-line comment format",
                )

        # 3. Preprocessor checks
        prep_tokens = [tok for tok in tokens if tok.kind == "PREPROCESSOR"]
        self._check_preprocessor(path, filepath_str, is_header, is_source, prep_tokens, lines_content)

        # 4. Lexical and AST-like checks on tokens
        self._check_code_tokens(path, filepath_str, is_header, is_source, tokens, lines_content)
        if self.target_files and self._checked_files >= set(self.target_files):
            self.finalize_violations()

    def _is_commented_code(self, s: str) -> bool:
        if not s:
            return False
        lower = s.lower()
        if any(lower.startswith(k) for k in [
            "return value", "return:", "returns:", "param:", "parameter:",
            "author:", "started on", "last update", "made by", "login"
        ]):
            return False
        patterns = [
            r"^(?:int|char|void|long|short|float|double|size_t|[a-zA-Z_]\w*\*)\s+[a-zA-Z_]\w*(\s*=\s*[^;]+)?\s*;",
            r"^(?:if|while|for|switch)\s*\([^)]+\)\s*\{?$",
            r"^return(\s+[^;]*)?;$",
            r"^[a-zA-Z_]\w*\s*=\s*[^;]+;$",
            r"^[a-zA-Z_]\w*\s*\([^)]*\)\s*;$",
        ]
        for pat in patterns:
            if re.match(pat, s):
                return True
        return False

    def _check_preprocessor(
        self,
        path: Path,
        filepath_str: str,
        is_header: bool,
        is_source: bool,
        prep_tokens: List[Token],
        lines_content: List[str],
    ):
        inc_list = []
        for tok in prep_tokens:
            val = tok.value

            # 1.15 cpp.mark (MUST): Preprocessor # must be on the first column
            if tok.col != 1:
                self.add_violation(
                    "1.15 cpp.mark",
                    "Error",
                    "Preprocessor # must be on the first column",
                    filepath_str,
                    tok.line,
                    "Preprocessor '#' not on the first column",
                )

            # 2.5 file.deadcode
            if re.match(r"^#\s*if\s+0\b", val):
                self.add_violation(
                    "2.5 file.deadcode",
                    "Warning",
                    "No commented-out code",
                    filepath_str,
                    tok.line,
                    "Commented-out code (#if 0) found",
                )

            # 1.13 cpp.if
            m_else = re.match(r"^#\s*else(.*)", val)
            if m_else:
                rest = m_else.group(1).strip()
                if not (rest.startswith("/*") or rest.startswith("//")):
                    self.add_violation(
                        "1.13 cpp.if",
                        "Error",
                        "#else and #endif must be followed by comment describing condition",
                        filepath_str,
                        tok.line,
                        "#else not followed by comment describing condition",
                    )
            m_endif = re.match(r"^#\s*endif(.*)", val)
            if m_endif:
                rest = m_endif.group(1).strip()
                if not (rest.startswith("/*") or rest.startswith("//")):
                    self.add_violation(
                        "1.13 cpp.if",
                        "Error",
                        "#else and #endif must be followed by comment describing condition",
                        filepath_str,
                        tok.line,
                        "#endif not followed by comment describing condition",
                    )

            # 1.14 cpp.include.filetype
            m_inc = re.search(r"#\s*include\s*[<\"']([^>\"']+)[>\"']", val)
            if m_inc:
                inc_target = m_inc.group(1)
                if inc_target.endswith(".c"):
                    self.add_violation(
                        "1.14 cpp.include.filetype",
                        "Error",
                        "Included files must be .h or .cxx (no including .c files)",
                        filepath_str,
                        tok.line,
                        f"Including .c file ('{inc_target}') is forbidden",
                    )

            # 2.3 cpp.include.order accumulation
            m_inc_order = re.search(r"^#\s*include\s*([<\"])([^>\"]+)([>\"])", val.strip())
            if m_inc_order:
                delim_open = m_inc_order.group(1)
                inc_target = m_inc_order.group(2)
                cat = 3  # LOCAL
                stem = path.stem
                if is_source and delim_open == '"' and Path(inc_target).name == f"{stem}.h":
                    cat = 1  # SAME_NAME
                elif delim_open == '<':
                    cat = 2  # SYSTEM
                inc_list.append((tok.line, cat, inc_target, val.strip()))

        if inc_list:
            blocks = []
            cur_block = [inc_list[0]]
            for prev_inc, cur_inc in zip(inc_list, inc_list[1:]):
                prev_line = prev_inc[0]
                cur_line = cur_inc[0]
                has_empty = any(lines_content[l - 1].strip() == "" for l in range(prev_line + 1, cur_line))
                if has_empty:
                    blocks.append(cur_block)
                    cur_block = [cur_inc]
                else:
                    cur_block.append(cur_inc)
            blocks.append(cur_block)

            prev_cat = 0
            for b in blocks:
                cats_in_block = {item[1] for item in b}
                if len(cats_in_block) > 1:
                    self.add_violation(
                        "2.3 cpp.include.order",
                        "Warning",
                        "Include blocks (same-name header, system headers, local headers) separated by empty line, alphabetical",
                        filepath_str,
                        b[0][0],
                        "Different include types (same-name, system, local) must be separated by an empty line",
                    )
                block_cat = b[0][1]
                if block_cat < prev_cat:
                    self.add_violation(
                        "2.3 cpp.include.order",
                        "Warning",
                        "Include blocks (same-name header, system headers, local headers) separated by empty line, alphabetical",
                        filepath_str,
                        b[0][0],
                        "Include blocks must appear in order: same-name header, system headers, local headers",
                    )
                prev_cat = max(prev_cat, block_cat)

                targets = [item[2] for item in b]
                for idx in range(len(targets) - 1):
                    if targets[idx] > targets[idx + 1]:
                        self.add_violation(
                            "2.3 cpp.include.order",
                            "Warning",
                            "Include blocks (same-name header, system headers, local headers) separated by empty line, alphabetical",
                            filepath_str,
                            b[idx + 1][0],
                            f"Includes not in alphabetical order: '{targets[idx]}' appears before '{targets[idx+1]}'",
                        )
                        break

        if is_header:
            stem = path.name
            guard_base = re.sub(r"[^a-zA-Z0-9]", "_", stem).upper()
            allowed_guards = {guard_base, guard_base + "_"}
            if not prep_tokens:
                self.add_violation(
                    "1.12 cpp.guard",
                    "Error",
                    "Header guards format (#ifndef, #define, #endif comment)",
                    filepath_str,
                    1,
                    f"Missing header guard (#ifndef {guard_base})",
                )
            else:
                first_tok = prep_tokens[0]
                m_ifndef = re.match(r"^#\s*ifndef\s+([a-zA-Z_]\w*)", first_tok.value)
                if not m_ifndef or m_ifndef.group(1) not in allowed_guards:
                    self.add_violation(
                        "1.12 cpp.guard",
                        "Error",
                        "Header guards format (#ifndef, #define, #endif comment)",
                        filepath_str,
                        first_tok.line,
                        f"Header must start with '#ifndef {guard_base}'",
                    )
                else:
                    guard_used = m_ifndef.group(1)
                    if len(prep_tokens) < 2:
                        self.add_violation(
                            "1.12 cpp.guard",
                            "Error",
                            "Header guards format (#ifndef, #define, #endif comment)",
                            filepath_str,
                            first_tok.line,
                            f"Missing '#define {guard_used}' after '#ifndef'",
                        )
                    else:
                        second_tok = prep_tokens[1]
                        m_def = re.match(r"^#\s*define\s+([a-zA-Z_]\w*)", second_tok.value)
                        if not m_def or m_def.group(1) != guard_used:
                            self.add_violation(
                                "1.12 cpp.guard",
                                "Error",
                                "Header guards format (#ifndef, #define, #endif comment)",
                                filepath_str,
                                second_tok.line,
                                f"Expected '#define {guard_used}'",
                            )

                    last_tok = prep_tokens[-1]
                    m_end = re.match(r"^#\s*endif(.*)", last_tok.value)
                    if not m_end:
                        self.add_violation(
                            "1.12 cpp.guard",
                            "Error",
                            "Header guards format (#ifndef, #define, #endif comment)",
                            filepath_str,
                            last_tok.line,
                            "Missing terminating '#endif'",
                        )
                    else:
                        comment_part = m_end.group(1).strip()
                        guard_pattern = re.compile(
                            rf"^(?:/\*\s*!?\s*{re.escape(guard_used)}\s*\*/|//\s*!?\s*{re.escape(guard_used)}\s*)$"
                        )
                        if not guard_pattern.match(comment_part):
                            self.add_violation(
                                "1.12 cpp.guard",
                                "Error",
                                "Header guards format (#ifndef, #define, #endif comment)",
                                filepath_str,
                                last_tok.line,
                                f"Terminating '#endif' must have comment matching guard (/* ! {guard_used} */ or // {guard_used})",
                            )

    def _check_code_tokens(
        self,
        path: Path,
        filepath_str: str,
        is_header: bool,
        is_source: bool,
        tokens: List[Token],
        lines_content: List[str],
    ):
        comment_lines_set: Set[int] = set()
        non_comment_lines_set: Set[int] = set()
        num_tokens = len(tokens)

        for idx in range(num_tokens):
            tok = tokens[idx]

            # Track comment vs non-comment lines for indentation check
            if tok.kind in ("COMMENT_BLOCK", "COMMENT_LINE"):
                comment_lines_set.update(range(tok.line, tok.end_line + 1))
                continue
            else:
                non_comment_lines_set.update(range(tok.line, tok.end_line + 1))

            # 1.16 cpp.digraphs
            if tok.kind in ("DIGRAPH", "TRIGRAPH"):
                self.add_violation(
                    "1.16 cpp.digraphs",
                    "Error",
                    "No digraphs/trigraphs (<%, %>, <:, :>, etc.)",
                    filepath_str,
                    tok.line,
                    f"Use of digraph/trigraph '{tok.value}' is forbidden",
                )

            # 1.11 gcc.builtins
            elif tok.kind == "IDENTIFIER" and tok.value.startswith("__builtin_"):
                self.add_violation(
                    "1.11 gcc.builtins",
                    "Error",
                    "No gcc builtins (__builtin_*)",
                    filepath_str,
                    tok.line,
                    f"Use of gcc builtin '{tok.value}' is forbidden",
                )

            # 1.19 keyword.goto
            elif tok.kind == "KEYWORD" and tok.value == "goto":
                self.add_violation(
                    "1.19 keyword.goto",
                    "Error",
                    "No goto",
                    filepath_str,
                    tok.line,
                    "Use of 'goto' keyword is forbidden",
                )

            # 1.20 stat.asm
            elif tok.kind in ("KEYWORD", "IDENTIFIER") and tok.value in ("asm", "__asm__", "__asm"):
                self.add_violation(
                    "1.20 stat.asm",
                    "Error",
                    "No asm / __asm__",
                    filepath_str,
                    tok.line,
                    f"Use of inline assembly '{tok.value}' is forbidden",
                )

            # 1.36 name.struct
            elif tok.kind == "KEYWORD" and tok.value == "typedef":
                next_idx = idx + 1
                while next_idx < num_tokens and tokens[next_idx].value in TYPE_QUALIFIERS:
                    next_idx += 1
                if next_idx < num_tokens and tokens[next_idx].value in ("struct", "union"):
                    self.add_violation(
                        "1.36 name.struct",
                        "Error",
                        "Structure and union names MUST NOT be aliased using typedef",
                        filepath_str,
                        tok.line,
                        f"Aliasing {tokens[next_idx].value} with typedef is forbidden",
                    )

            # 1.8 else_if.indent
            elif tok.kind == "KEYWORD" and tok.value == "else":
                k = idx + 1
                while k < num_tokens and tokens[k].kind in ("COMMENT_LINE", "COMMENT_BLOCK"):
                    k += 1
                if k < num_tokens and tokens[k].kind == "KEYWORD" and tokens[k].value == "if":
                    if tokens[k].line != tok.line:
                        self.add_violation(
                            "1.8 else_if.indent",
                            "Error",
                            "else if on same line",
                            filepath_str,
                            tokens[k].line,
                            "'else if' must appear on the same line",
                        )

            # 1.29 keyword.arg
            elif tok.kind == "KEYWORD" and tok.value in ("sizeof", "typeof", "_Alignof"):
                if idx + 1 < num_tokens and tokens[idx + 1].value != "(":
                    self.add_violation(
                        "1.29 keyword.arg",
                        "Error",
                        "Functional keywords enclosed in parentheses (e.g. sizeof(...))",
                        filepath_str,
                        tok.line,
                        f"Argument to functional keyword '{tok.value}' must be enclosed in parentheses",
                    )

            # 1.30 semicolon
            elif tok.kind == "PUNCTUATOR" and tok.value == ";":
                line_text = lines_content[tok.line - 1]
                if tok.col > 1 and line_text[tok.col - 2] in (' ', '\t'):
                    self.add_violation(
                        "1.30 semicolon",
                        "Error",
                        "No space before semicolon, space after semicolon if followed by statement",
                        filepath_str,
                        tok.line,
                        "No space allowed before semicolon",
                    )
                if tok.col < len(line_text):
                    after_char = line_text[tok.col]
                    if after_char not in (' ', '\t', '\r', '\n', ';', ')', '}', '/', '"', "'"):
                        self.add_violation(
                            "1.30 semicolon",
                            "Error",
                            "No space before semicolon, space after semicolon if followed by statement",
                            filepath_str,
                            tok.line,
                            "Space required after semicolon when followed by statement/expression",
                        )

            # 1.25 ctrl.switch.padding
            elif tok.kind == "KEYWORD" and tok.value in ("case", "default"):
                p_depth = 0
                for j in range(idx + 1, min(idx + 50, num_tokens)):
                    v = tokens[j].value
                    if v == "(":
                        p_depth += 1
                    elif v == ")":
                        p_depth -= 1
                    elif tokens[j].kind == "PUNCTUATOR" and v == ":" and p_depth == 0:
                        line_text = lines_content[tokens[j].line - 1]
                        if tokens[j].col > 1 and line_text[tokens[j].col - 2] in (' ', '\t'):
                            self.add_violation(
                                "1.25 ctrl.switch.padding",
                                "Error",
                                "No space before : in case/default",
                                filepath_str,
                                tokens[j].line,
                                f"No space allowed before ':' in {tok.value}",
                            )
                        break
                    elif tokens[j].kind == "PUNCTUATOR" and v in (";", "{", "}") and p_depth == 0:
                        break

            # 1.28 exp.args
            if tok.kind == "IDENTIFIER" and idx + 1 < num_tokens:
                next_tok = tokens[idx + 1]
                if next_tok.value == "(" and next_tok.line == tok.line and next_tok.col > tok.end_col + 1:
                    line_text = lines_content[tok.line - 1].strip()
                    if not line_text.startswith("#"):
                        self.add_violation(
                            "1.28 exp.args",
                            "Error",
                            "No space between function name and ( in call/decl",
                            filepath_str,
                            tok.line,
                            f"No space allowed between function name '{tok.value}' and '('",
                        )

        # 2.2 indent.level (SHOULD): Indentation should not exceed 3 levels (12 spaces)
        max_spaces = self.max_indent_level * 4
        indent_violations: List[Tuple[int, int]] = []
        for idx, line in enumerate(lines_content, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if idx in comment_lines_set and idx not in non_comment_lines_set:
                continue
            leading_spaces = 0
            for ch in line:
                if ch == ' ':
                    leading_spaces += 1
                elif ch == '\t':
                    leading_spaces += 4
                else:
                    break
            if leading_spaces > max_spaces:
                indent_violations.append((idx, leading_spaces))

        if indent_violations:
            r_start, r_min = indent_violations[0]
            r_end = r_start
            r_max = r_min
            groups: List[Tuple[int, int, int, int]] = []
            for v_line, v_spaces in indent_violations[1:]:
                if v_line == r_end + 1:
                    r_end = v_line
                    r_min = min(r_min, v_spaces)
                    r_max = max(r_max, v_spaces)
                else:
                    groups.append((r_start, r_end, r_min, r_max))
                    r_start = v_line
                    r_end = v_line
                    r_min = v_spaces
                    r_max = v_spaces
            groups.append((r_start, r_end, r_min, r_max))

            for g_start, g_end, g_min, g_max in groups:
                sp_desc = f"{g_min}" if g_min == g_max else f"{g_min}-{g_max}"
                self.add_violation(
                    "2.2 indent.level",
                    "Warning",
                    f"Indentation should not exceed {self.max_indent_level} levels ({max_spaces} spaces)",
                    filepath_str,
                    g_start,
                    f"Indentation level exceeds {self.max_indent_level} levels ({sp_desc} spaces)",
                    end_line=(g_end if g_end > g_start else None),
                )

        code_tokens = [tok for tok in tokens if tok.kind not in ("COMMENT_LINE", "COMMENT_BLOCK", "PREPROCESSOR")]
        self._check_casts(code_tokens, filepath_str)
        self._check_switches(code_tokens, tokens, filepath_str)
        self._analyze_structure(path, filepath_str, is_header, is_source, code_tokens, tokens, lines_content)

    def _is_type_token(self, val: str) -> bool:
        return is_c_type(val, self.known_typedefs)

    def _check_casts(self, code_tokens: List[Token], filepath_str: str):
        """Rule 1.1 cast (MUST): 0 explicit C casts allowed anywhere in code."""
        if any(part == "tests" for part in Path(filepath_str).parts):
            return
        n = len(code_tokens)
        for i, tok in enumerate(code_tokens):
            if tok.value == "(":
                prev_tok = code_tokens[i - 1] if i > 0 else None
                # Exclude if, while, for, switch, sizeof, etc. and function calls
                if prev_tok and (prev_tok.value in ("sizeof", "typeof", "_Alignof", "if", "while", "for", "switch") or prev_tok.kind == "IDENTIFIER"):
                    continue
                cast_type, closing_paren_idx = self._parse_cast_type(code_tokens, i)
                if cast_type and closing_paren_idx + 1 < n:
                    next_tok = code_tokens[closing_paren_idx + 1]
                    if next_tok.kind in ("IDENTIFIER", "NUMBER", "STRING", "CHAR") or next_tok.value in ("(", "*", "&", "-", "+", "~", "!", "sizeof"):
                        self.project_casts.append((filepath_str, tok.line, cast_type))

    def _is_case_body_terminating(self, tokens: List[Token]) -> bool:
        if not tokens:
            return True

        if tokens[-1].value == "}":
            depth = 1
            idx = len(tokens) - 2
            while idx >= 0 and depth > 0:
                if tokens[idx].value == "}":
                    depth += 1
                elif tokens[idx].value == "{":
                    depth -= 1
                idx -= 1
            if depth == 0:
                inner_tokens = tokens[idx + 2 : -1]
                if self._is_case_body_terminating(inner_tokens):
                    return True

        last_semi = None
        for idx in range(len(tokens) - 1, -1, -1):
            if tokens[idx].value == ";":
                last_semi = idx
                break
        if last_semi is None:
            return False

        p_depth = 0
        b_depth = 0
        stmt_start = 0
        for idx in range(last_semi - 1, -1, -1):
            t = tokens[idx]
            if t.value == ")":
                p_depth += 1
            elif t.value == "(":
                p_depth -= 1
            elif t.value == "}":
                b_depth += 1
            elif t.value == "{":
                b_depth -= 1
            elif p_depth == 0 and b_depth == 0 and t.value in (";", "{", "}"):
                stmt_start = idx + 1
                break

        stmt_tokens = tokens[stmt_start:last_semi]
        for t in stmt_tokens:
            if t.value in ("break", "return", "goto", "exit", "_Exit", "_exit", "abort"):
                return True
            if t.kind in ("KEYWORD", "IDENTIFIER"):
                break

        return False

    def _check_switches(self, code_tokens: List[Token], all_tokens: List[Token], filepath_str: str):
        """Rules 1.22 ctrl.switch, 1.23 ctrl.switch.fallthrough, 1.24 ctrl.switch.indentation."""
        n = len(code_tokens)
        for i in range(n):
            tok = code_tokens[i]
            if tok.kind == "KEYWORD" and tok.value == "switch":
                switch_line = tok.line
                switch_col = tok.col
                k = i + 1
                while k < n and code_tokens[k].value != "{":
                    k += 1
                if k >= n:
                    continue
                brace_tok = code_tokens[k]
                switch_brace_col = brace_tok.col

                depth = 1
                k += 1
                has_default = False
                case_indices = []
                while k < n and depth > 0:
                    if code_tokens[k].value == "{":
                        depth += 1
                    elif code_tokens[k].value == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    elif depth == 1:
                        if code_tokens[k].kind == "KEYWORD" and code_tokens[k].value in ("case", "default"):
                            if code_tokens[k].value == "default":
                                has_default = True
                            case_indices.append(k)
                            if code_tokens[k].col != switch_brace_col and code_tokens[k].col != switch_col:
                                self.add_violation(
                                    "1.24 ctrl.switch.indentation",
                                    "Error",
                                    "case on same column as switch {",
                                    filepath_str,
                                    code_tokens[k].line,
                                    f"'{code_tokens[k].value}' must be on the same column as switch '{{'",
                                )
                    k += 1

                switch_end_idx = k
                if not has_default:
                    self.add_violation(
                        "1.22 ctrl.switch",
                        "Error",
                        "Switch must have default case",
                        filepath_str,
                        switch_line,
                        "Switch statement must contain a 'default' case",
                    )

                for c_num, c_idx in enumerate(case_indices):
                    if c_num + 1 >= len(case_indices):
                        continue

                    next_case_idx = case_indices[c_num + 1]
                    next_bound_line = code_tokens[next_case_idx].line

                    colon_idx = c_idx + 1
                    p_depth = 0
                    while colon_idx < next_case_idx:
                        if code_tokens[colon_idx].value == "(":
                            p_depth += 1
                        elif code_tokens[colon_idx].value == ")":
                            p_depth -= 1
                        elif code_tokens[colon_idx].value == ":" and p_depth == 0:
                            break
                        colon_idx += 1

                    case_body_tokens = code_tokens[colon_idx + 1 : next_case_idx]
                    if not case_body_tokens:
                        continue

                    is_terminated = self._is_case_body_terminating(case_body_tokens)
                    if not is_terminated:
                        fallthrough_found = False
                        for all_t in all_tokens:
                            if all_t.line >= code_tokens[colon_idx].line and all_t.line <= next_bound_line:
                                if "FALLTHROUGH" in all_t.value.upper():
                                    fallthrough_found = True
                                    break
                        if not fallthrough_found:
                            self.add_violation(
                                "1.23 ctrl.switch.fallthrough",
                                "Error",
                                "Fallthrough must have /* FALLTHROUGH */",
                                filepath_str,
                                code_tokens[c_idx].line,
                                "Fallthrough in switch case without '/* FALLTHROUGH */' comment",
                            )

    def _skip_balanced_parens(self, tokens: List[Token], open_idx: int) -> Optional[int]:
        n = len(tokens)
        if open_idx >= n or tokens[open_idx].value != "(":
            return None
        depth = 1
        k = open_idx + 1
        while k < n and depth > 0:
            if tokens[k].value == "(":
                depth += 1
            elif tokens[k].value == ")":
                depth -= 1
                if depth == 0:
                    return k
            k += 1
        return None

    def _looks_like_param_list(self, inner: List[Token]) -> bool:
        if not inner:
            return True
        if len(inner) == 1 and inner[0].value == "void":
            return True
        params: List[List[Token]] = []
        cur: List[Token] = []
        dp = 0
        for t in inner:
            if t.value == "(":
                dp += 1
            elif t.value == ")":
                dp -= 1
            if t.value == "," and dp == 0:
                params.append(cur)
                cur = []
            else:
                cur.append(t)
        if cur:
            params.append(cur)
        first = params[0] if params else []
        if not first:
            return False
        if len(first) == 1:
            pv = first[0].value
            return (
                pv in STANDARD_TYPES
                or pv in self.known_typedefs
                or pv.startswith("t_")
                or pv.endswith("_t")
                or pv == "..."
            )
        if first[0].kind in ("KEYWORD", "IDENTIFIER") and first[0].value not in C_KEYWORDS and len(first) == 2 and first[1].value == "*":
            return True
        return self._looks_like_decl_start(first, 0)

    def _is_paren_declarator(self, tokens: List[Token], idx: int, is_definite_known: bool) -> bool:
        n = len(tokens)
        if idx + 2 >= n or tokens[idx + 1].value != "(" or tokens[idx + 2].value != "*":
            return False
        close_p = self._skip_balanced_parens(tokens, idx + 1)
        if close_p is None:
            return False
        inner = tokens[idx + 2 : close_p]
        k = 0
        ni = len(inner)
        while k < ni and (inner[k].value == "*" or inner[k].value in TYPE_QUALIFIERS):
            k += 1
        if k >= ni:
            return False
        if inner[k].kind == "IDENTIFIER" and inner[k].value not in C_KEYWORDS:
            k += 1
        elif inner[k].value == "(":
            # Nested parenthesized pointer declarator e.g. (*(*fp))
            sub_close = self._skip_balanced_parens(inner, k)
            if sub_close is None or k + 1 >= ni or inner[k + 1].value != "*":
                return False
            k = sub_close + 1
        else:
            return False
        while k < ni:
            if inner[k].value == "(":
                sub_close = self._skip_balanced_parens(inner, k)
                if sub_close is None:
                    return False
                k = sub_close + 1
            elif inner[k].value == "[":
                db = 1
                k += 1
                while k < ni and db > 0:
                    if inner[k].value == "[":
                        db += 1
                    elif inner[k].value == "]":
                        db -= 1
                    k += 1
                if db != 0:
                    return False
            else:
                return False

        after_idx = close_p + 1
        after_val = tokens[after_idx].value if after_idx < n else None
        if after_val in ("=", ",", "[", "__attribute__", "__attribute"):
            return True
        if after_val == "(":
            arg_close = self._skip_balanced_parens(tokens, after_idx)
            if arg_close is None:
                return False
            post_arg = tokens[arg_close + 1].value if arg_close + 1 < n else None
            if post_arg == "{" or is_definite_known:
                return True
            return self._looks_like_param_list(tokens[after_idx + 1 : arg_close])
        if is_definite_known and (after_val is None or after_val == ";"):
            return True
        return False

    def _looks_like_decl_start(self, tokens: List[Token], idx: int) -> bool:
        n = len(tokens)
        while idx < n and tokens[idx].value in ("__extension__", "__attribute__", "__attribute"):
            attr_val = tokens[idx].value
            idx += 1
            if attr_val != "__extension__":
                while idx < n and tokens[idx].value == "(":
                    close_p = self._skip_balanced_parens(tokens, idx)
                    if close_p is None:
                        return False
                    idx = close_p + 1
        if idx >= n:
            return False
        tok = tokens[idx]
        if tok.kind not in ("KEYWORD", "IDENTIFIER"):
            return False
        non_decl_kw = {
            "if", "else", "for", "while", "do", "switch", "case", "default",
            "return", "break", "continue", "goto", "sizeof", "_Alignof",
            "_Static_assert", "_Generic",
        }
        if tok.value in non_decl_kw:
            return False
        decl_kw = {
            "typedef", "static", "extern", "register", "auto", "inline",
            "const", "volatile", "restrict", "signed", "unsigned", "short",
            "long", "void", "char", "int", "float", "double", "struct",
            "union", "enum", "bool", "_Bool", "_Complex", "_Imaginary",
            "_Noreturn", "_Thread_local", "_Atomic", "_Alignas",
            "__inline", "__inline__", "__restrict", "__restrict__",
        }
        if tok.value in decl_kw:
            return True
        if tok.value in ("typeof", "__typeof__", "__typeof"):
            j = idx + 1
            if j < n and tokens[j].value == "(":
                dp = 1
                j += 1
                while j < n and dp > 0:
                    if tokens[j].value == "(":
                        dp += 1
                    elif tokens[j].value == ")":
                        dp -= 1
                    j += 1
            return j < n and (tokens[j].kind == "IDENTIFIER" or tokens[j].value in ("*", "(") or tokens[j].value in TYPE_QUALIFIERS)

        if idx + 1 >= n:
            return False
        nxt = tokens[idx + 1]

        is_definite_known = tok.value in STANDARD_TYPES or tok.value in self.known_typedefs
        is_heuristic_known = tok.value.startswith("t_") or tok.value.endswith("_t")

        if is_definite_known or is_heuristic_known:
            if nxt.kind == "IDENTIFIER" and nxt.value not in non_decl_kw:
                return True
            if nxt.value in TYPE_QUALIFIERS or nxt.value in STANDARD_TYPES:
                return True
            if nxt.value == "(":
                return self._is_paren_declarator(tokens, idx, is_definite_known)
        else:
            # Unknown IDENTIFIER (e.g., typedef from an external header)
            if nxt.kind == "IDENTIFIER" and nxt.value not in C_KEYWORDS:
                return True
            if nxt.value in ("const", "volatile", "restrict", "__restrict", "__restrict__", "_Atomic"):
                return True
            if nxt.value == "(":
                return self._is_paren_declarator(tokens, idx, False)

        if nxt.value == "*":
            j = idx + 2
            spaced_stars = False
            while j < n and (tokens[j].value == "*" or tokens[j].value in TYPE_QUALIFIERS):
                if tokens[j].value == "*" and tokens[j - 1].value == "*":
                    if tokens[j].line != tokens[j - 1].line or tokens[j].col != tokens[j - 1].end_col + 1:
                        spaced_stars = True
                        break
                j += 1
            if spaced_stars or j >= n:
                return False
            if tokens[j].value == "(":
                return self._is_paren_declarator(tokens, j - 1, is_definite_known)
            exclude_kw = non_decl_kw if (is_definite_known or is_heuristic_known) else C_KEYWORDS
            if tokens[j].kind == "IDENTIFIER" and tokens[j].value not in exclude_kw:
                after_tok = tokens[j + 1].value if j + 1 < n else None
                if after_tok not in (
                    None, ";", "=", ",", "[", "(", ")", ":",
                    "__attribute__", "__attribute", "asm", "__asm__", "__asm",
                ):
                    return False
                if is_definite_known:
                    return True
                if after_tok == "(":
                    close_p = self._skip_balanced_parens(tokens, j + 1)
                    if close_p is not None:
                        after_val = tokens[close_p + 1].value if close_p + 1 < n else None
                        return after_val == "{" or self._looks_like_param_list(tokens[j + 2 : close_p])
                    return False
                if after_tok in ("=", ",", "[", ":", "__attribute__", "__attribute", "asm", "__asm__", "__asm"):
                    return True
                star_left_glued = nxt.line == tok.line and nxt.col == tok.end_col + 1
                star_right_glued = tokens[j].line == tokens[j - 1].line and tokens[j].col == tokens[j - 1].end_col + 1
                has_qual = any(tokens[m].value in TYPE_QUALIFIERS for m in range(idx + 2, j))
                return star_left_glued or star_right_glued or has_qual
        return False

    def _check_struct_or_union_bodies(
        self,
        filepath_str: str,
        tokens: List[Token],
        lines_content: List[str],
        line_decls: Dict[int, List[str]],
    ):
        n = len(tokens)
        k = 0
        while k < n:
            if tokens[k].value == "=":
                # Stop before top-level initializer so compound literals aren't mistaken for struct definitions
                break
            if tokens[k].value in ("struct", "union"):
                j = k + 1
                if j < n and tokens[j].kind == "IDENTIFIER":
                    j += 1
                if j < n and tokens[j].value == "{":
                    m = skip_balanced(tokens, j, "{", "}") - 1
                    if m < n and tokens[m].value == "}":
                        inner = tokens[j + 1:m]
                        self._check_local_declarations(filepath_str, inner, lines_content, line_decls, in_struct=True)
                        k = m + 1
                        continue
            k += 1

    def _analyze_structure(
        self,
        path: Path,
        filepath_str: str,
        is_header: bool,
        is_source: bool,
        code_tokens: List[Token],
        all_tokens: List[Token],
        lines_content: List[str],
    ):
        n = len(code_tokens)
        i = 0
        exported_globals_count = 0
        exported_funcs_count = 0
        has_exported_funcs = False
        prev_func_end_line: Optional[int] = None
        line_decls: Dict[int, List[str]] = {}

        while i < n:
            tok = code_tokens[i]

            # 1. Typedef statements (Rule 1.36 checked in _check_code_tokens)
            if tok.kind == "KEYWORD" and tok.value == "typedef":
                k = find_statement_end(code_tokens, i + 1)
                td_tokens = code_tokens[i:k + 1] if k < n else code_tokens[i:k]
                self._check_struct_or_union_bodies(filepath_str, td_tokens, lines_content, line_decls)
                td_decls = extract_declarators_from_decl(td_tokens, self._is_type_token)
                for vname, vline in td_decls:
                    line_decls.setdefault(vline, []).append(vname)
                self._check_decl_point(filepath_str, td_tokens, lines_content)
                i = k + 1
                continue

            # Unwrap extern "C" { ... } linkage specification blocks so declarations inside are inspected
            if (
                tok.kind == "KEYWORD"
                and tok.value == "extern"
                and i + 2 < n
                and code_tokens[i + 1].kind == "STRING"
                and code_tokens[i + 2].value == "{"
            ):
                i += 3
                continue

            # 2. Enum definitions
            is_enum_def = False
            brace_k = None
            if tok.kind == "KEYWORD" and tok.value == "enum":
                k = i + 1
                has_paren = False
                while k < n:
                    if code_tokens[k].value == "(":
                        has_paren = True
                        break
                    elif code_tokens[k].value == ";":
                        break
                    elif code_tokens[k].value == "{":
                        brace_k = k
                        break
                    k += 1
                if brace_k is not None and not has_paren:
                    is_enum_def = True

            if is_enum_def and brace_k is not None:
                k = brace_k + 1
                depth = 1
                enum_tokens = []
                while k < n and depth > 0:
                    if code_tokens[k].value == "{":
                        depth += 1
                    elif code_tokens[k].value == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    if depth == 1:
                        enum_tokens.append(code_tokens[k])
                    k += 1
                if k < n and code_tokens[k].value == "}":
                    closing_brace = code_tokens[k]
                    if enum_tokens and enum_tokens[-1].value != ",":
                        self.add_violation(
                            "2.4 enum.comma",
                            "Warning",
                            "Enum last element has trailing comma",
                            filepath_str,
                            closing_brace.line,
                            "Last enumeration element must have a trailing comma",
                        )
                    m = k + 1
                    decl_after_enum = []
                    while m < n and code_tokens[m].value != ";" and code_tokens[m].value not in ("{", "}"):
                        decl_after_enum.append(code_tokens[m])
                        m += 1
                    if decl_after_enum:
                        var_names = extract_declarators_from_decl(code_tokens[i:m], self._is_type_token)
                        is_static = has_top_level_specifier(code_tokens[i:m], "static")
                        has_extern = has_top_level_specifier(code_tokens[i:m], "extern")
                        if not has_extern and not is_header and not is_static:
                            exported_globals_count += len(var_names)
                            if exported_globals_count > self.max_exported_globals:
                                desc = (
                                    "At most 1 non-function exported symbol (global variable) per source file"
                                    if self.max_exported_globals == 1
                                    else f"At most {self.max_exported_globals} non-function exported symbols (global variables) per source file"
                                )
                                self.add_violation(
                                    "1.3 export.other",
                                    "Error",
                                    desc,
                                    filepath_str,
                                    tok.line,
                                    f"More than {self.max_exported_globals} non-function exported symbol in source file",
                                )
                        if not is_static:
                            for vname, vline in var_names:
                                if not vname.startswith("g_"):
                                    self.add_violation(
                                        "1.35 name.prefix.global",
                                        "Error",
                                        "Global variables must start with g_",
                                        filepath_str,
                                        vline,
                                        f"Global variable '{vname}' must start with 'g_'",
                                    )
                        for vname, vline in var_names:
                            line_decls.setdefault(vline, []).append(vname)
                    if m < n and code_tokens[m].value == ";":
                        i = m + 1
                    else:
                        i = k + 1
                    continue

            # 3. Top-level declarations and function definitions
            if self._looks_like_decl_start(code_tokens, i):
                k = i
                has_eq = False
                brace_pos = None
                semi_pos = None
                while k < n:
                    if code_tokens[k].value == "=" and brace_pos is None:
                        has_eq = True
                    elif code_tokens[k].value == "{" and brace_pos is None:
                        if not has_eq:
                            cand_fn, _ = self._extract_func_info(code_tokens[i:k])
                            if cand_fn is None and any(
                                t.value in ("struct", "union", "enum") for t in code_tokens[i:k]
                            ):
                                b_depth = 1
                                k += 1
                                while k < n and b_depth > 0:
                                    if code_tokens[k].value == "{":
                                        b_depth += 1
                                    elif code_tokens[k].value == "}":
                                        b_depth -= 1
                                    k += 1
                                continue
                        brace_pos = k
                        break
                    elif code_tokens[k].value == ";" and brace_pos is None:
                        semi_pos = k
                        break
                    k += 1

                is_func_def = False
                func_name = None
                param_tokens = None
                if brace_pos is not None and not has_eq:
                    header_tokens = code_tokens[i:brace_pos]
                    fn_name, p_tokens = self._extract_func_info(header_tokens)
                    if fn_name:
                        is_func_def = True
                        func_name = fn_name
                        param_tokens = p_tokens

                if is_func_def and brace_pos is not None:
                    func_header_tokens = code_tokens[i:brace_pos]
                    is_static = has_top_level_specifier(func_header_tokens, "static")

                    if func_name != "main":
                        if not is_static and is_source:
                            exported_funcs_count += 1
                            has_exported_funcs = True

                    self._check_struct_or_union_bodies(filepath_str, func_header_tokens, lines_content, line_decls)
                    self._check_function_params(filepath_str, func_name, param_tokens, tok.line)

                    if prev_func_end_line is not None:
                        func_start_line = tok.line
                        between_toks = [
                            all_t for all_t in all_tokens
                            if prev_func_end_line < all_t.line and all_t.end_line < tok.line
                        ]
                        if not any(all_t.kind not in ("COMMENT_LINE", "COMMENT_BLOCK") for all_t in between_toks):
                            comm_toks = [
                                all_t for all_t in between_toks
                                if all_t.kind in ("COMMENT_LINE", "COMMENT_BLOCK")
                            ]
                            if comm_toks:
                                func_start_line = min(all_t.line for all_t in comm_toks)
                        diff = func_start_line - prev_func_end_line
                        if diff == 1:
                            self.add_violation(
                                "1.10 fun.sep.line",
                                "Error",
                                "Function definitions must be separated by one empty line",
                                filepath_str,
                                func_start_line,
                                "Function definitions must be separated by one empty line",
                            )

                    self._check_decl_point(filepath_str, func_header_tokens, lines_content)

                    body_start_line = code_tokens[brace_pos].line
                    k = skip_balanced(code_tokens, brace_pos, "{", "}") - 1
                    body_tokens = code_tokens[brace_pos + 1:k]
                    body_end_line = code_tokens[k].line if k < n else body_start_line
                    prev_func_end_line = body_end_line

                    self._check_function_length(
                        filepath_str,
                        func_name or "function",
                        body_start_line,
                        body_end_line,
                        lines_content,
                        all_tokens,
                    )

                    self._analyze_body_statements(filepath_str, body_tokens, lines_content, line_decls)
                    i = k + 1
                    continue

                else:
                    k = find_statement_end(code_tokens, i)

                    decl_tokens = code_tokens[i:k + 1] if k < n else code_tokens[i:k]
                    is_static = has_top_level_specifier(decl_tokens, "static")
                    has_extern = has_top_level_specifier(decl_tokens, "extern")

                    self._check_struct_or_union_bodies(filepath_str, decl_tokens, lines_content, line_decls)

                    has_eq = any(t.value == "=" for t in decl_tokens)
                    has_brace = any(t.value == "{" for t in decl_tokens)
                    fn_name, p_tokens = self._extract_func_info(decl_tokens) if (not has_eq and not has_brace) else (None, None)
                    if fn_name and p_tokens is not None:
                        if is_source and not is_static and fn_name != "main":
                            self.add_violation(
                                "1.9 fun.proto.layout",
                                "Error",
                                "Exported function prototypes must appear in header files, not source files; source files must include their header",
                                filepath_str,
                                tok.line,
                                f"Exported function prototype '{fn_name}' found in source file",
                            )
                        self._check_function_params(filepath_str, fn_name, p_tokens, tok.line)
                        proto_vars = extract_declarators_from_decl(decl_tokens, self._is_type_token)
                        if proto_vars:
                            for vname, vline in proto_vars:
                                line_decls.setdefault(vline, []).append(vname)
                        else:
                            line_decls.setdefault(tok.line, []).append(fn_name)
                        self._check_decl_point(filepath_str, decl_tokens, lines_content)
                    else:
                        var_names = extract_declarators_from_decl(decl_tokens, self._is_type_token)
                        if not has_extern and not is_header and not is_static:
                            exported_globals_count += len(var_names)
                            if exported_globals_count > self.max_exported_globals:
                                desc = (
                                    "At most 1 non-function exported symbol (global variable) per source file"
                                    if self.max_exported_globals == 1
                                    else f"At most {self.max_exported_globals} non-function exported symbols (global variables) per source file"
                                )
                                self.add_violation(
                                    "1.3 export.other",
                                    "Error",
                                    desc,
                                    filepath_str,
                                    tok.line,
                                    f"More than {self.max_exported_globals} non-function exported symbol in source file",
                                )

                        if not is_static:
                            for vname, vline in var_names:
                                if not vname.startswith("g_"):
                                    self.add_violation(
                                        "1.35 name.prefix.global",
                                        "Error",
                                        "Global variables must start with g_",
                                        filepath_str,
                                        vline,
                                        f"Global variable '{vname}' must start with 'g_'",
                                    )

                        for vname, vline in var_names:
                            line_decls.setdefault(vline, []).append(vname)

                        self._check_decl_point(filepath_str, decl_tokens, lines_content)

                    i = k + 1
                    continue

            if code_tokens[i].value == "(":
                close_p = self._skip_balanced_parens(code_tokens, i)
                if close_p is not None:
                    i = close_p + 1
                    continue
            i += 1

        if exported_funcs_count > self.max_exported_funcs:
            desc = (
                "At most 10 exported functions per source file"
                if self.max_exported_funcs == 10
                else f"At most {self.max_exported_funcs} exported functions per source file"
            )
            self.add_violation(
                "1.4 export.fun",
                "Error",
                desc,
                filepath_str,
                None,
                f"Source file has {exported_funcs_count} exported functions (maximum allowed is {self.max_exported_funcs})",
            )

        for line_num, names in line_decls.items():
            if len(names) > self.max_decls_per_line:
                desc = (
                    "At most 1 declaration per line (except in for)"
                    if self.max_decls_per_line == 1
                    else f"At most {self.max_decls_per_line} declarations per line (except in for)"
                )
                msg = (
                    "Multiple declarations on a single line"
                    if self.max_decls_per_line == 1
                    else f"More than {self.max_decls_per_line} declarations on a single line"
                )
                self.add_violation(
                    "1.17 decl.single",
                    "Error",
                    desc,
                    filepath_str,
                    line_num,
                    msg,
                )

        if is_source and has_exported_funcs:
            stem = path.stem
            header_name = f"{stem}.h"
            includes_own_header = False
            for tok in all_tokens:
                if tok.kind == "PREPROCESSOR" and "#include" in tok.value:
                    m = re.search(r'#\s*include\s*[<"]([^>"]+)[>"]', tok.value)
                    if m:
                        inc_target = m.group(1).replace("\\", "/")
                        if Path(inc_target).name == header_name:
                            includes_own_header = True
                            break
            if not includes_own_header:
                self.add_violation(
                    "1.9 fun.proto.layout",
                    "Error",
                    "Exported function prototypes must appear in header files, not source files; source files must include their header",
                    filepath_str,
                    1,
                    f"Source file defining exported functions must include its header ('{header_name}')",
                )

    def _extract_func_info(self, tokens: List[Token]) -> Tuple[Optional[str], Optional[List[Token]]]:
        n = len(tokens)
        idx = 0
        while idx < n - 1:
            tv = tokens[idx].value
            if tv == "{":
                b_depth = 1
                idx += 1
                while idx < n and b_depth > 0:
                    if tokens[idx].value == "{":
                        b_depth += 1
                    elif tokens[idx].value == "}":
                        b_depth -= 1
                    idx += 1
                continue
            if tv in ("__attribute__", "__attribute", "typeof", "__typeof__", "__typeof", "_Alignas", "__declspec"):
                idx += 1
                while idx < n and tokens[idx].value == "(":
                    close_p = self._skip_balanced_parens(tokens, idx)
                    if close_p is None:
                        return None, None
                    idx = close_p + 1
                continue
            if tokens[idx].kind == "IDENTIFIER" and tokens[idx + 1].value == "(":
                func_name = tokens[idx].value
                depth = 1
                k = idx + 2
                param_tokens = []
                while k < n and depth > 0:
                    if tokens[k].value == "(":
                        depth += 1
                    elif tokens[k].value == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    param_tokens.append(tokens[k])
                    k += 1
                if depth == 0:
                    return func_name, param_tokens
            idx += 1
        return None, None

    def _check_function_params(self, filepath_str: str, func_name: str, param_tokens: List[Token], line: int):
        if not param_tokens or len(param_tokens) == 0:
            self.add_violation(
                "1.7 fun.proto.void",
                "Error",
                "Prototypes with no arguments MUST specify void",
                filepath_str,
                line,
                f"Function '{func_name}' with no arguments must specify 'void'",
            )
            return

        if len(param_tokens) == 1 and param_tokens[0].value == "void":
            return

        comma_count = 0
        depth = 0
        for tok in param_tokens:
            if tok.value == "(":
                depth += 1
            elif tok.value == ")":
                depth -= 1
            elif tok.value == "," and depth == 0:
                comma_count += 1
        arg_count = comma_count + 1
        if arg_count > self.max_func_args:
            desc = (
                "Functions MUST NOT take more than 4 arguments"
                if self.max_func_args == 4
                else f"Functions MUST NOT take more than {self.max_func_args} arguments"
            )
            self.add_violation(
                "1.5 fun.arg.count",
                "Error",
                desc,
                filepath_str,
                line,
                f"Function '{func_name}' has {arg_count} arguments (maximum allowed is {self.max_func_args})",
            )

    def _strip_decl_for_point(self, tokens: List[Token]) -> List[Token]:
        """Keep declaration specifiers, parameters, and declarator pointers while stripping initializers, struct bodies, array bounds, and sizeof/typeof args."""
        cleaned: List[Token] = []
        n = len(tokens)
        i = 0
        while i < n:
            v = tokens[i].value
            if v in ("sizeof", "typeof", "__typeof__", "__typeof", "_Alignof"):
                cleaned.append(tokens[i])
                i += 1
                if i < n and tokens[i].value == "(":
                    i = skip_balanced(tokens, i, "(", ")")
                continue
            if v in ("[", "{"):
                close_delim = "]" if v == "[" else "}"
                i = skip_balanced(tokens, i, v, close_delim)
                continue
            if v == "=":
                i = skip_expression_to_comma_or_semi(tokens, i + 1)
                continue
            cleaned.append(tokens[i])
            i += 1
        return cleaned

    def _check_decl_point(self, filepath_str: str, tokens: List[Token], lines_content: List[str]):
        """Rule 1.26 decl.point (MUST): Pointer * next to variable name, not type."""
        cleaned = self._strip_decl_for_point(tokens)
        for idx in range(len(cleaned)):
            tok = cleaned[idx]
            if tok.value == "*":
                if idx > 0:
                    prev_tok = cleaned[idx - 1]
                    is_type_prev = (
                        self._is_type_token(prev_tok.value)
                        or prev_tok.value in TYPE_QUALIFIERS
                        or (idx >= 2 and cleaned[idx - 2].value in ("struct", "union", "enum"))
                        or (
                            prev_tok.kind == "IDENTIFIER"
                            and prev_tok.value not in C_KEYWORDS
                            and (idx == 1 or cleaned[idx - 2].value in ("(", ","))
                        )
                    )
                    if is_type_prev and tok.line == prev_tok.line and tok.col == prev_tok.end_col + 1:
                        self.add_violation(
                            "1.26 decl.point",
                            "Error",
                            "Pointer * next to variable name, not type",
                            filepath_str,
                            tok.line,
                            f"Pointer '*' must be next to variable/function name, not type '{prev_tok.value}*'",
                        )
                if idx + 1 < len(cleaned):
                    next_tok = cleaned[idx + 1]
                    if (
                        next_tok.kind == "IDENTIFIER"
                        and not self._is_type_token(next_tok.value)
                        and next_tok.value not in TYPE_QUALIFIERS
                        and next_tok.value not in C_KEYWORDS
                    ):
                        if next_tok.line == tok.line and next_tok.col > tok.end_col + 1:
                            self.add_violation(
                                "1.26 decl.point",
                                "Error",
                                "Pointer * next to variable name, not type",
                                filepath_str,
                                tok.line,
                                f"Pointer '*' must be next to variable/function name '{next_tok.value}'",
                            )

    def _check_function_length(
        self,
        filepath_str: str,
        func_name: str,
        start_line: int,
        end_line: int,
        lines_content: List[str],
        all_tokens: List[Token],
    ):
        comment_lines_set = set()
        for tok in all_tokens:
            if tok.kind in ("COMMENT_BLOCK", "COMMENT_LINE"):
                for l in range(tok.line, tok.end_line + 1):
                    comment_lines_set.add(l)

        counted_lines = 0
        for l in range(start_line, end_line + 1):
            line_str = lines_content[l - 1].strip()
            if not line_str:
                continue
            if line_str in ("{", "}"):
                continue
            if l in comment_lines_set:
                has_code = any(
                    t.line == l and t.kind not in ("COMMENT_BLOCK", "COMMENT_LINE") for t in all_tokens
                )
                if not has_code:
                    continue
            counted_lines += 1

        if counted_lines > self.max_func_lines:
            self.add_violation(
                "1.6 fun.len",
                "Error",
                f"Function body must not exceed {self.max_func_lines} lines",
                filepath_str,
                start_line,
                f"Function '{func_name}' body has {counted_lines} lines (limit is {self.max_func_lines})",
            )
        elif counted_lines > self.warn_func_lines:
            desc = (
                "Function body should not exceed 25 lines"
                if self.warn_func_lines == 25
                else f"Function body should not exceed {self.warn_func_lines} lines"
            )
            self.add_violation(
                "2.1 fun.len",
                "Warning",
                desc,
                filepath_str,
                start_line,
                f"Function '{func_name}' body has {counted_lines} lines (recommended limit is {self.warn_func_lines})",
            )

    def _check_local_declarations(
        self,
        filepath_str: str,
        tokens: List[Token],
        lines_content: List[str],
        line_decls: Dict[int, List[str]],
        in_struct: bool = False,
    ):
        n = len(tokens)
        i = 0

        while i < n:
            tok = tokens[i]

            if tok.value == ";":
                i += 1
                continue

            if tok.value == "{":
                j = skip_balanced(tokens, i, "{", "}") - 1
                if not in_struct:
                    self._check_local_declarations(filepath_str, tokens[i + 1:j], lines_content, line_decls, in_struct=False)
                i = j + 1
                continue

            if tok.value == "}":
                i += 1
                continue

            if not in_struct:
                if tok.kind == "IDENTIFIER" and i + 1 < n and tokens[i + 1].value == ":":
                    i += 2
                    continue
                if tok.kind == "KEYWORD" and tok.value == "default" and i + 1 < n and tokens[i + 1].value == ":":
                    i += 2
                    continue
                if tok.kind == "KEYWORD" and tok.value == "case":
                    j = i + 1
                    dp = db = dk = 0
                    while j < n:
                        v = tokens[j].value
                        if v == "(":
                            dp += 1
                        elif v == ")":
                            dp -= 1
                        elif v == "{":
                            db += 1
                        elif v == "}":
                            db -= 1
                        elif v == "[":
                            dk += 1
                        elif v == "]":
                            dk -= 1
                        elif v == ":" and dp == 0 and db == 0 and dk == 0:
                            break
                        j += 1
                    i = j + 1
                    continue

                if tok.kind == "KEYWORD" and tok.value == "for":
                    j = i + 1
                    while j < n and tokens[j].value != "(":
                        j += 1
                    if j < n:
                        end_p = skip_balanced(tokens, j, "(", ")")
                        inner_for = tokens[j + 1:end_p - 1]
                        semi_idx = None
                        dp = db = dk = 0
                        for idx_f, ft in enumerate(inner_for):
                            if ft.value == "(":
                                dp += 1
                            elif ft.value == ")":
                                dp -= 1
                            elif ft.value == "{":
                                db += 1
                            elif ft.value == "}":
                                db -= 1
                            elif ft.value == "[":
                                dk += 1
                            elif ft.value == "]":
                                dk -= 1
                            elif ft.value == ";" and dp == 0 and db == 0 and dk == 0:
                                semi_idx = idx_f
                                break
                        for_init = inner_for[:semi_idx] if semi_idx is not None else inner_for
                        if for_init and self._looks_like_decl_start(for_init, 0):
                            self._check_decl_point(filepath_str, for_init, lines_content)
                        i = end_p
                    else:
                        i += 1
                    continue

                if tok.kind == "KEYWORD" and tok.value in ("if", "while", "switch"):
                    j = i + 1
                    if j < n and tokens[j].value == "(":
                        i = skip_balanced(tokens, j, "(", ")")
                    else:
                        i += 1
                    continue

                if tok.kind == "KEYWORD" and tok.value in ("else", "do"):
                    i += 1
                    continue

            if self._looks_like_decl_start(tokens, i):
                k = i
                dp = db = dk = 0
                while k < n:
                    v = tokens[k].value
                    if v == "(":
                        dp += 1
                    elif v == ")":
                        dp -= 1
                    elif v == "{":
                        db += 1
                    elif v == "}":
                        if db == 0:
                            break
                        db -= 1
                    elif v == "[":
                        dk += 1
                    elif v == "]":
                        dk -= 1
                    elif v == ";" and dp == 0 and db == 0 and dk == 0:
                        break
                    k += 1

                if k < n and tokens[k].value == ";":
                    decl_tokens = tokens[i:k + 1]
                    self._check_struct_or_union_bodies(filepath_str, decl_tokens, lines_content, line_decls)
                    var_names = extract_declarators_from_decl(decl_tokens, self._is_type_token)
                    for vname, vline in var_names:
                        line_decls.setdefault(vline, []).append(vname)
                    self._check_decl_point(filepath_str, decl_tokens, lines_content)
                    i = k + 1
                    continue

            # Non-declaration statement
            k = i
            dp = db = dk = 0
            while k < n:
                v = tokens[k].value
                if v == "(":
                    dp += 1
                elif v == ")":
                    if dp > 0:
                        dp -= 1
                elif v == "{":
                    if dp == 0 and db == 0 and dk == 0:
                        prev_v = tokens[k - 1].value if k > i else ""
                        if prev_v not in ("=", ")", ","):
                            break
                        if prev_v == ")" and k > i:
                            open_p = k - 2
                            p_bal = 1
                            while open_p >= i and p_bal > 0:
                                if tokens[open_p].value == ")":
                                    p_bal += 1
                                elif tokens[open_p].value == "(":
                                    p_bal -= 1
                                open_p -= 1
                            if (
                                open_p >= i
                                and tokens[open_p].kind == "IDENTIFIER"
                                and "=" not in [t.value for t in tokens[i:open_p + 1]]
                            ):
                                break
                    db += 1
                elif v == "}":
                    if db == 0:
                        break
                    db -= 1
                elif v == "[":
                    dk += 1
                elif v == "]":
                    if dk > 0:
                        dk -= 1
                elif v == ";" and dp == 0 and db == 0 and dk == 0:
                    k += 1
                    break
                k += 1

            i = k if k > i else i + 1

    def _analyze_body_statements(
        self,
        filepath_str: str,
        body_tokens: List[Token],
        lines_content: List[str],
        line_decls: Dict[int, List[str]],
    ):
        self._check_local_declarations(filepath_str, body_tokens, lines_content, line_decls)

        n = len(body_tokens)
        i = 0

        while i < n:
            tok = body_tokens[i]

            # 1.18 decl.vla (MUST): No VLA
            if tok.value == "[" and i >= 2:
                ident_tok = body_tokens[i - 1]
                type_tok = body_tokens[i - 2]
                is_type = self._is_type_token(type_tok.value) or type_tok.value == "*" or (
                    i >= 3 and body_tokens[i - 3].value in ("struct", "union", "enum")
                )
                if ident_tok.kind == "IDENTIFIER" and is_type:
                    k = i + 1
                    dim_tokens = []
                    while k < n and body_tokens[k].value != "]":
                        dim_tokens.append(body_tokens[k])
                        k += 1
                    if dim_tokens:
                        has_vla = False
                        dt_idx = 0
                        while dt_idx < len(dim_tokens):
                            dt = dim_tokens[dt_idx]
                            if dt.value == "sizeof":
                                dt_idx += 1
                                if dt_idx < len(dim_tokens) and dim_tokens[dt_idx].value == "(":
                                    p_depth = 1
                                    dt_idx += 1
                                    while dt_idx < len(dim_tokens) and p_depth > 0:
                                        if dim_tokens[dt_idx].value == "(":
                                            p_depth += 1
                                        elif dim_tokens[dt_idx].value == ")":
                                            p_depth -= 1
                                        dt_idx += 1
                                continue
                            if dt.kind == "IDENTIFIER":
                                if any(c.islower() for c in dt.value):
                                    has_vla = True
                                    break
                            dt_idx += 1
                        if has_vla:
                            dim_expr = "".join(dt.value for dt in dim_tokens)
                            self.add_violation(
                                "1.18 decl.vla",
                                "Error",
                                "No VLA",
                                filepath_str,
                                ident_tok.line,
                                f"Variable-length array '{ident_tok.value}[{dim_expr}]' is forbidden",
                            )

            # 1.21 ctrl.empty: Single-line loop body on next line, if empty must be continue;
            if tok.kind == "KEYWORD" and tok.value in ("while", "for"):
                is_do_while = False
                if tok.value == "while" and i > 0 and body_tokens[i - 1].value == "}":
                    is_do_while = True
                if not is_do_while:
                    k = i + 1
                    while k < n and body_tokens[k].value != "(":
                        k += 1
                    if k < n and body_tokens[k].value == "(":
                        k = skip_balanced(body_tokens, k, "(", ")") - 1
                        if k < n:
                            closing_paren = body_tokens[k]
                            if k + 1 < n:
                                next_tok = body_tokens[k + 1]
                                # Single line loop body must be on next line (if not '{')
                                if next_tok.value != "{" and next_tok.line == closing_paren.line:
                                    self.add_violation(
                                        "1.21 ctrl.empty",
                                        "Error",
                                        "Single-line loop body on next line, if empty must be continue;",
                                        filepath_str,
                                        closing_paren.line,
                                        "Loop body must be placed on the next line",
                                    )
                                if next_tok.value == ";":
                                    self.add_violation(
                                        "1.21 ctrl.empty",
                                        "Error",
                                        "Single-line loop body on next line, if empty must be continue;",
                                        filepath_str,
                                        next_tok.line,
                                        "Empty loop body must be 'continue;'",
                                    )
                                elif next_tok.value == "{" and k + 2 < n and body_tokens[k + 2].value == "}":
                                    self.add_violation(
                                        "1.21 ctrl.empty",
                                        "Error",
                                        "Single-line loop body on next line, if empty must be continue;",
                                        filepath_str,
                                        next_tok.line,
                                        "Empty loop body must be 'continue;'",
                                    )

            # 1.27 ctrl.do_while: } while (...); on same line
            if tok.kind == "KEYWORD" and tok.value == "do":
                k = i + 1
                while k < n and body_tokens[k].value != "{":
                    k += 1
                if k < n and body_tokens[k].value == "{":
                    k = skip_balanced(body_tokens, k, "{", "}") - 1
                    if k < n and body_tokens[k].value == "}":
                        closing_brace = body_tokens[k]
                        if k + 1 < n and body_tokens[k + 1].kind == "KEYWORD" and body_tokens[k + 1].value == "while":
                            while_tok = body_tokens[k + 1]
                            if while_tok.line != closing_brace.line:
                                self.add_violation(
                                    "1.27 ctrl.do_while",
                                    "Error",
                                    "} while (...); on same line",
                                    filepath_str,
                                    while_tok.line,
                                    "'} while (...);' must be on the same line",
                                )

            # 1.31 stat.sep: Comma operator not used outside for
            if tok.value == ",":
                if not self._is_allowed_comma(body_tokens, i):
                    self.add_violation(
                        "1.31 stat.sep",
                        "Error",
                        "Comma operator not used outside for",
                        filepath_str,
                        tok.line,
                        "Comma operator must not be used outside 'for'",
                    )

            i += 1

    def _parse_cast_type(self, tokens: List[Token], paren_idx: int) -> Tuple[Optional[str], int]:
        k = paren_idx + 1
        depth = 1
        inner_tokens = []
        while k < len(tokens) and depth > 0:
            if tokens[k].value == "(":
                depth += 1
            elif tokens[k].value == ")":
                depth -= 1
                if depth == 0:
                    break
            inner_tokens.append(tokens[k])
            k += 1

        if depth != 0 or not inner_tokens:
            return None, k

        type_parts = []
        is_type = False
        idx = 0
        while idx < len(inner_tokens) and inner_tokens[idx].value in TYPE_QUALIFIERS:
            type_parts.append(inner_tokens[idx].value)
            idx += 1

        if idx < len(inner_tokens):
            if inner_tokens[idx].value in ("struct", "union", "enum"):
                type_parts.append(inner_tokens[idx].value)
                idx += 1
                if idx < len(inner_tokens) and inner_tokens[idx].kind == "IDENTIFIER":
                    type_parts.append(inner_tokens[idx].value)
                    idx += 1
                    is_type = True
            elif self._is_type_token(inner_tokens[idx].value):
                type_parts.append(inner_tokens[idx].value)
                idx += 1
                is_type = True
            elif inner_tokens[idx].kind == "IDENTIFIER":
                if any(t.value == "*" for t in inner_tokens[idx+1:]):
                    type_parts.append(inner_tokens[idx].value)
                    idx += 1
                    is_type = True

        if not is_type:
            return None, k

        while idx < len(inner_tokens):
            if inner_tokens[idx].value in TYPE_QUALIFIERS or inner_tokens[idx].value == "*":
                type_parts.append(inner_tokens[idx].value)
                idx += 1
            else:
                return None, k

        return " ".join(type_parts), k

    def _is_inside_for_header(self, tokens: List[Token], semi_idx: int) -> bool:
        dp = 0
        db = 0
        p = semi_idx - 1
        while p >= 0:
            v = tokens[p].value
            if v == "}":
                db += 1
            elif v == "{":
                if db > 0:
                    db -= 1
                else:
                    return False
            elif v == ")":
                dp += 1
            elif v == "(":
                if dp > 0:
                    dp -= 1
                elif db == 0:
                    return p > 0 and tokens[p - 1].value == "for"
                else:
                    return False
            p -= 1
        return False

    def _is_brace_initializer_or_enum(self, tokens: List[Token], brace_idx: int) -> bool:
        prev = tokens[brace_idx - 1] if brace_idx > 0 else None
        if prev:
            if prev.value in ("=", "enum"):
                return True
            if prev.value == ")":
                dp = 1
                q = brace_idx - 2
                while q >= 0 and dp > 0:
                    if tokens[q].value == ")":
                        dp += 1
                    elif tokens[q].value == "(":
                        dp -= 1
                    q -= 1
                if q < 0 or tokens[q].value not in ("if", "while", "for", "switch"):
                    return True
        j = brace_idx - 1
        b_depth = 0
        while j >= 0:
            v = tokens[j].value
            if v == "}":
                b_depth += 1
            elif v == "{":
                if b_depth > 0:
                    b_depth -= 1
                else:
                    p_prev = tokens[j - 1] if j > 0 else None
                    if p_prev and p_prev.value in ("=", "enum"):
                        return True
                    if p_prev and p_prev.value == ")":
                        dp = 1
                        q = j - 2
                        while q >= 0 and dp > 0:
                            if tokens[q].value == ")":
                                dp += 1
                            elif tokens[q].value == "(":
                                dp -= 1
                            q -= 1
                        if q < 0 or tokens[q].value not in ("if", "while", "for", "switch"):
                            return True
            elif b_depth == 0:
                if v in ("=", "enum"):
                    return True
                if v == ";":
                    return False
            j -= 1
        return False

    def _is_allowed_comma(self, tokens: List[Token], comma_idx: int) -> bool:
        depth_paren = 0
        depth_brace = 0
        depth_bracket = 0
        k = comma_idx - 1
        while k >= 0:
            tok = tokens[k]
            if tok.value == "]":
                depth_bracket += 1
            elif tok.value == "[":
                if depth_bracket > 0:
                    depth_bracket -= 1
                else:
                    return False
            elif tok.value == ")":
                depth_paren += 1
            elif tok.value == "(":
                if depth_paren > 0:
                    depth_paren -= 1
                else:
                    prev = tokens[k - 1] if k > 0 else None
                    if prev:
                        if prev.value == "for":
                            return True
                        if prev.kind == "IDENTIFIER":
                            return True
                        if prev.value == ")":
                            return True
                    return False
            elif tok.value == "}":
                if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
                    # Find matching '{' to see whether this '}' closed a compound statement vs struct/enum decl
                    b = 1
                    m = k - 1
                    while m >= 0 and b > 0:
                        if tokens[m].value == "}":
                            b += 1
                        elif tokens[m].value == "{":
                            b -= 1
                        m -= 1
                    open_brace = m + 1
                    is_tag_or_init = False
                    if b == 0 and open_brace >= 0:
                        if self._is_brace_initializer_or_enum(tokens, open_brace):
                            is_tag_or_init = True
                        else:
                            scan = open_brace - 1
                            while scan >= 0 and tokens[scan].value not in (";", "{", "}"):
                                if tokens[scan].value in ("struct", "union", "enum", "="):
                                    is_tag_or_init = True
                                    break
                                scan -= 1
                    if not is_tag_or_init:
                        stmt_start = k + 1
                        if stmt_start < len(tokens) and self._looks_like_decl_start(tokens, stmt_start):
                            return True
                        return False
                depth_brace += 1
            elif tok.value == "{":
                if depth_brace > 0:
                    depth_brace -= 1
                else:
                    if self._is_brace_initializer_or_enum(tokens, k):
                        return True
                    stmt_start = k + 1
                    if stmt_start < len(tokens) and self._looks_like_decl_start(tokens, stmt_start):
                        return True
                    return False
            elif tok.value == ";" and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
                if self._is_inside_for_header(tokens, k):
                    return True
                stmt_start = k + 1
                if stmt_start < len(tokens) and self._looks_like_decl_start(tokens, stmt_start):
                    return True
                return False
            k -= 1

        if tokens and self._looks_like_decl_start(tokens, 0):
            return True

        return False


def print_report(
    violations: List[RuleViolation],
    ignore_warnings: bool = False,
) -> int:
    if ignore_warnings:
        violations = [v for v in violations if v.severity != "Warning"]

    if not violations:
        return 0

    groups: Dict[Tuple[str, str, str], List[RuleViolation]] = {}
    has_errors = False
    seen = set()

    for v in violations:
        sig = (v.rule_id, v.severity, v.filepath, v.line, v.end_line, v.message)
        if sig in seen:
            continue
        seen.add(sig)
        if v.severity == "Error":
            has_errors = True
        key = (v.rule_id, v.severity, v.description)
        if key not in groups:
            groups[key] = []
        groups[key].append(v)

    def group_sort_key(item):
        (r_id, sev, desc), v_list = item
        m = re.match(r"^(\d+)\.(\d+)(?:\s+(.*))?$", r_id)
        if m:
            sec, subsec, name = int(m.group(1)), int(m.group(2)), m.group(3) or ""
            rule_sort = (sec, subsec, name)
        else:
            rule_sort = (999, 999, r_id)
        return (SEVERITY_ORDER.get(sev, 99), rule_sort)

    sorted_groups = sorted(groups.items(), key=group_sort_key)

    COLOR_RED = "[31m"
    COLOR_YELLOW = "[33m"
    COLOR_WHITE = "[97m"
    COLOR_LIGHT_GRAY = "[37m"
    COLOR_RESET = "[0m"

    for (rule_id, severity, description), v_list in sorted_groups:
        sev_color = COLOR_RED if severity == "Error" else COLOR_YELLOW
        print(f"[[{sev_color}{severity}{COLOR_RESET}]] {COLOR_WHITE}{rule_id}: {description}{COLOR_RESET}")
        sorted_violations = sorted(
            v_list,
            key=lambda v: (
                v.filepath,
                v.line if v.line is not None else 0,
                v.end_line if v.end_line is not None else 0,
                v.message,
            ),
        )
        for v in sorted_violations:
            if v.line is None:
                loc = v.filepath
            elif v.end_line is not None and v.end_line > v.line:
                loc = f"{v.filepath}:{v.line}-{v.end_line}"
            else:
                loc = f"{v.filepath}:{v.line}"
            print(f"- at: {COLOR_WHITE}{loc}{COLOR_RESET}:")
            print(f"	{COLOR_LIGHT_GRAY}{v.message}{COLOR_RESET}")
        print()

    return 1 if has_errors else 0


def main():
    parser = argparse.ArgumentParser(
        description="Coding Style Checker (v1.0.0)"
    )
    parser.add_argument(
        "path",
        help="Root directory to recursively scan for .c and .h files",
    )
    parser.add_argument(
        "--line",
        "--lines",
        "--max-func-lines",
        dest="max_func_lines",
        type=int,
        default=30,
        help="Specify the max function length for errors (defaults to 30)",
    )
    parser.add_argument(
        "--warn-func-lines",
        "--warn-lines",
        dest="warn_func_lines",
        type=int,
        default=25,
        help="Specify the function length limit for warnings (defaults to 25)",
    )
    parser.add_argument(
        "--max-exported-globals",
        "--max-exported-other",
        dest="max_exported_globals",
        type=int,
        default=1,
        help="Specify the max non-function exported symbols per file (defaults to 1)",
    )
    parser.add_argument(
        "--max-exported-funcs",
        "--max-exported-functions",
        dest="max_exported_funcs",
        type=int,
        default=10,
        help="Specify the max exported functions per file (defaults to 10)",
    )
    parser.add_argument(
        "--max-func-args",
        "--max-args",
        dest="max_func_args",
        type=int,
        default=4,
        help="Specify the max function arguments (defaults to 4)",
    )
    parser.add_argument(
        "--max-indent-level",
        "--max-indent",
        dest="max_indent_level",
        type=int,
        default=3,
        help="Specify the max indentation level in levels of 4 spaces (defaults to 3)",
    )
    parser.add_argument(
        "--max-decls-per-line",
        "--max-decls",
        dest="max_decls_per_line",
        type=int,
        default=1,
        help="Specify the max declarations per line (defaults to 1)",
    )
    parser.add_argument(
        "--max-casts",
        dest="max_casts",
        type=int,
        default=0,
        metavar="N",
        help="Specify the max allowed explicit C casts across non-test files (defaults to 0)",
    )
    parser.add_argument(
        "--IgnoreW",
        "--ignore-w",
        action="store_true",
        dest="ignore_w",
        help="Ignore warning checks",
    )

    args = parser.parse_args()
    setattr(args, "line", args.max_func_lines)

    root_path = Path(args.path)
    if not root_path.exists():
        sys.stderr.write(f"Error: path '{args.path}' does not exist\n")
        sys.exit(1)

    target_files: List[Path] = []
    if root_path.is_file():
        if not root_path.name.startswith(".") and root_path.suffix in (".c", ".h"):
            target_files.append(root_path)
    else:
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if not f.startswith("."):
                    p = Path(root) / f
                    if p.suffix in (".c", ".h"):
                        target_files.append(p)

    target_files.sort()

    if not target_files:
        sys.exit(0)

    checker = StyleChecker(
        target_files,
        max_func_lines=args.max_func_lines,
        warn_func_lines=args.warn_func_lines,
        max_exported_globals=args.max_exported_globals,
        max_exported_funcs=args.max_exported_funcs,
        max_func_args=args.max_func_args,
        max_indent_level=args.max_indent_level,
        max_decls_per_line=args.max_decls_per_line,
        max_casts=args.max_casts,
    )
    checker.collect_global_info()

    for p in target_files:
        checker.check_file(p)
    checker.finalize_violations()

    exit_code = print_report(checker.violations, ignore_warnings=args.ignore_w)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
