"""app.py —— 兼容壳（真正的实现已移到 prototype/wsgi.py）。

为什么改名
----------
`app` 这个名字在 PyPI 上被一个无关的发行版占用了。只要第三方站点目录出现在
sys.path 的靠前位置，`import app` 就会静默拿到那个包，然后报
`ImportError: cannot import name 'VERSION' from 'app'` —— 排查成本很高。
打包成 .exe 时（PyInstaller 会把入口目录也放进搜索路径）撞名的概率进一步升高，
所以应用本体改用不会撞名的 `wsgi`（这也符合 Flask 生态里 "wsgi.py" 的惯例）。

这个文件保留下来只为两件事：
  1. `python prototype/app.py` 仍然能起服务（run.ps1 与历史文档都引用了它）；
  2. 用脚本路径加载时（importlib.util.spec_from_file_location）依然可用。

新代码请直接 `import wsgi` 或 `from wsgi import create_app`。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from wsgi import (  # noqa: E402,F401
    Dataset,
    VERSION,
    WEB_DIR,
    create_app,
)

app = create_app()  # 兼容 `flask --app prototype/app.py` 与旧测试的模块级 app

if __name__ == "__main__":
    from wsgi import main

    main()
