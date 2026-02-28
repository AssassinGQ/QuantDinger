"""
控制台输出：本地可观测性，输出到 stdout 供用户在控制台查看状态。
"""


def console_print(msg: str) -> None:
    """打印到 stdout，flush 确保实时输出"""
    try:
        print(str(msg or ""), flush=True)
    except Exception:
        pass
