#!/bin/sh
# 运行全部测试与检查 (提交前全绿):
#   后端: pylint / mypy / pytest (2026-09-15 起不跑覆盖率, NAS 上太拖时间;
#         JS 纯模块仍有 c8 门禁)
#   前端: ESLint (页面脚本+测试) / tsc --checkJS (纯逻辑模块) /
#         node --test + c8 覆盖率门禁 95% (gcj02 / trackutil / format /
#         trip-playback / lastpage)
# 前端工具链要 node_modules (npm ci 安装); 本机没装时跳过静态检查与
# c8 门禁 (CI 会全量跑), node --test 照跑。
cd "$(dirname "$0")" || exit 1
rc=0

# pytest 的 tmp_path 优先放内存 (/dev/shm 3.8G tmpfs): 测试的 SQLite 种子库
# 全在内存里跑, 不用跟机械盘上的媒体服务抢 IO —— 那是全量测试最大的拖累。
# /tmp 只有 64M 不够一轮 (会 ENOSPC); /dev/shm 重启即清, 没有就退回仓库目录。
if [ -d /dev/shm ] && [ -w /dev/shm ]; then
  mkdir -p /dev/shm/my-tesla-pytest
  export TMPDIR=/dev/shm/my-tesla-pytest
else
  mkdir -p .pytest-tmp
  export TMPDIR="$PWD/.pytest-tmp"
fi

# 静态检查: app 严检; tests 是 pytest 仪式代码 (fixture 形参/保护访问/
# 模块内导入), 单独放宽这几类 —— 4.0 没有 per-path-ignores, 只好两次调用
.venv/bin/python -m pylint app || rc=1
.venv/bin/python -m pylint tests --disable=W0613,W0212,R0801,C0415 || rc=1
.venv/bin/python -m mypy || rc=1

.venv/bin/python -m pytest tests -q || rc=1

# 前端: npx --no-install 只认本仓库 node_modules (不悄悄下载)
if [ -d node_modules ]; then
  npx --no-install eslint app/tesla/static app/static tests/js || rc=1
  npx --no-install tsc -p tsconfig.json || rc=1
  npx --no-install c8 \
    --include 'app/tesla/static/gcj02.js' --include 'app/tesla/static/trackutil.js' \
    --include 'app/tesla/static/format.js' --include 'app/tesla/static/trip-playback.js' \
    --include 'app/tesla/static/lastpage.js' \
    --check-coverage --lines 95 --branches 95 --functions 95 \
    --reporter text node --test tests/js/*.test.mjs || rc=1
else
  echo "跳过前端静态检查与覆盖率门禁 (本机无 node_modules; CI 会跑全量)" >&2
  node --test tests/js/*.test.mjs || rc=1
fi

exit $rc
