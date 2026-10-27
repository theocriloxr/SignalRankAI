"""Quick smoke test to verify Telegram command module health."""

import py_compile


def collect_command_functions():
    from signalrank_telegram import commands

    return [
        name
        for name in dir(commands)
        if name.endswith("_command") and callable(getattr(commands, name))
    ]


def test_commands_module_imports_and_compiles():
    cmd_funcs = collect_command_functions()

    assert len(cmd_funcs) >= 1
    py_compile.compile("signalrank_telegram/commands.py", doraise=True)


if __name__ == "__main__":
    funcs = collect_command_functions()
    print(f"Commands module imports successfully; found {len(funcs)} command functions.")
    for cmd in sorted(funcs):
        print(f"  - {cmd}")
    py_compile.compile("signalrank_telegram/commands.py", doraise=True)
    print("commands.py compiles without errors")
