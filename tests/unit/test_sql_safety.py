"""PRD target: "0 unparameterized SQL queries in the codebase".

This test reads every .py file in src/ and fails if any execute()/executemany()/executescript()
call builds its SQL dynamically (f-string, + concatenation, % formatting or .format()).
It protects the search code you write in week 2 as well.

Limitation: it only looks at the argument written inside execute(...). SQL built in a variable
first (sql = f"..."; conn.execute(sql)) is not detected, so keep SQL in constant strings.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "audit_search"
SQL_METHODS = {"execute", "executemany", "executescript"}


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):  # f"..."
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):  # "..." + x / %
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def find_unsafe_sql_calls(root: Path = SRC) -> list[str]:
    problems = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in SQL_METHODS
                and node.args
                and _is_dynamic_string(node.args[0])
            ):
                problems.append(f"{path.relative_to(root)}:{node.lineno}")
    return problems


def test_no_dynamic_sql_in_codebase():
    assert find_unsafe_sql_calls() == []


def test_checker_catches_each_kind_of_dynamic_sql(tmp_path):
    (tmp_path / "bad.py").write_text(
        'conn.execute(f"SELECT * FROM t WHERE id = {x}")\n'
        'conn.execute("SELECT * FROM t WHERE id = " + x)\n'
        'conn.execute("SELECT * FROM t WHERE id = %s" % x)\n'
        'conn.executemany("INSERT INTO {} VALUES (?)".format(t), rows)\n'
        'conn.execute("SELECT * FROM t WHERE id = ?", (x,))\n'  # safe: not reported
    )
    assert find_unsafe_sql_calls(tmp_path) == ["bad.py:1", "bad.py:2", "bad.py:3", "bad.py:4"]
