import os
import ast

PROJECT_ROOT = "app"  # Adjust to your project root


class FileInfo:
    def __init__(self):
        self.pydantic_models = []
        self.sqlalchemy_models = []
        self.fastapi_routes = []
        self.functions = []


# --------------------
# Helpers
# --------------------
def is_pydantic_model(node):
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def is_sqlalchemy_model(node):
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Base":
            return True
    return False


def extract_pydantic_fields(node):
    fields = {}
    for stmt in node.body:
        if isinstance(stmt, ast.FunctionDef):
            continue
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                type_ann = ast.unparse(stmt.annotation) if stmt.annotation else "Any"
                default = ast.unparse(stmt.value) if stmt.value else None
                fields[name] = (type_ann, default)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    default = ast.unparse(stmt.value) if stmt.value else None
                    fields[name] = ("Any", default)
    return fields


def extract_sqlalchemy_fields(node):
    fields = {}
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    val = stmt.value
                    if isinstance(val, ast.Call):
                        if isinstance(val.func, ast.Name) and val.func.id == "Column":
                            col_type = None
                            if val.args:
                                col_type = ast.unparse(val.args[0])
                            else:
                                for kw in val.keywords:
                                    if kw.arg == "type_":
                                        col_type = ast.unparse(kw.value)
                            default = None
                            for kw in val.keywords:
                                if kw.arg in ("default", "server_default"):
                                    default = ast.unparse(kw.value)
                            fields[name] = (col_type, default)
    return fields


def extract_fastapi_routes(tree):
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and hasattr(decorator.func, "attr"):
                    if decorator.func.attr in ["get", "post", "put", "delete", "patch"]:
                        path = "/"
                        if decorator.args:
                            if isinstance(decorator.args[0], ast.Constant):
                                path = decorator.args[0].value or "/"
                        routes.append({
                            "method": decorator.func.attr.upper(),
                            "path": path,
                            "function": node.name
                        })
    return routes


def extract_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return None

    info = FileInfo()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if is_pydantic_model(node):
                info.pydantic_models.append({
                    "name": node.name,
                    "fields": extract_pydantic_fields(node)
                })
            if is_sqlalchemy_model(node):
                info.sqlalchemy_models.append({
                    "name": node.name,
                    "fields": extract_sqlalchemy_fields(node)
                })
        elif isinstance(node, ast.FunctionDef):
            # Store full function signature instead of only the name
            info.functions.append(
                "def " + node.name + "(" +
                ", ".join(arg.arg for arg in node.args.args) +
                "):"
            )

    info.fastapi_routes = extract_fastapi_routes(tree)
    return info


# --------------------
# Walk project
# --------------------
def walk_project(root):
    report = {}
    for dirname, _, files in os.walk(root):
        for file in files:
            if file.endswith(".py"):
                fullpath = os.path.join(dirname, file)
                relpath = os.path.relpath(fullpath, root)
                info = extract_from_file(fullpath)
                if info:
                    # Keep only files with models, routes, or functions
                    if info.pydantic_models or info.sqlalchemy_models or info.fastapi_routes or info.functions:
                        report[relpath] = info
    return report


# --------------------
# Print AI-optimized
# --------------------
def print_report(report):
    for file, info in report.items():
        print(f"=== {file} ===")

        if info.pydantic_models:
            print("Pydantic Models:")
            for model in info.pydantic_models:
                print(f"  - {model['name']}")
                for fname, (ftype, fdefault) in model['fields'].items():
                    type_str = ftype if ftype else "Any"
                    default_str = f" = {fdefault}" if fdefault else ""
                    print(f"      {fname}: {type_str}{default_str}")

        if info.sqlalchemy_models:
            print("SQLAlchemy Models:")
            for model in info.sqlalchemy_models:
                print(f"  - {model['name']}")
                for fname, (ftype, fdefault) in model['fields'].items():
                    type_str = ftype if ftype else "Unknown"
                    default_str = f" = {fdefault}" if fdefault else ""
                    print(f"      {fname}: {type_str}{default_str}")

        if info.fastapi_routes:
            print("FastAPI Routes:")
            for r in info.fastapi_routes:
                path = r['path'] if r['path'] else "/"
                print(f"  - {r['method']} {path} → {r['function']}")

        if info.functions:
            # Show each function on its own line
            print("Functions:\n  " + "\n  ".join(info.functions))


# --------------------
# Main
# --------------------
if __name__ == "__main__":
    report = walk_project(PROJECT_ROOT)
    print_report(report)
