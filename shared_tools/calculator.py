"""Safe arithmetic calculator, shared by every AIMAOS agent.

Local models are unreliable at multi-step arithmetic; this gives them a
real calculator instead of guessing. Evaluates via a whitelisted AST walk
(no `eval`/`exec`, no name or attribute access) so it can't be used to run
arbitrary code even if a hostile string reaches it.
"""
import ast
import math
import operator

TOOL_DEFINITION = {
    "name": "calculator",
    "description": "Evaluates an arithmetic expression (+ - * / ** % // parentheses, and functions like "
                   "sqrt, abs, round, min, max) and returns the numeric result.",
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression, e.g. '(1500 * 1.06) / 12' or 'sqrt(144) + 3'."
            }
        },
        "required": ["expression"]
    }
}

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
    "floor": math.floor, "ceil": math.ceil, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        args = [_eval_node(a) for a in node.args]
        return _FUNCS[node.func.id](*args)
    raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


def execute(expression):
    if not expression or not expression.strip():
        return "Error: expression must not be empty."
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)
    except ZeroDivisionError:
        return "Error: division by zero."
    except Exception as e:
        return f"Error: could not evaluate '{expression}': {e}"
    return f"{expression} = {result}"
