#!/bin/sh
# 运行全部测试与检查 (提交前全绿):
#   后端: pylint (app 严检 / tests 放宽仪式代码) / mypy /
#         pytest (JS 纯逻辑模块另有 c8 门禁, 不带覆盖率跑 python)
#   前端: ESLint (页面脚本+测试) / tsc --checkJS (纯逻辑模块) /
#         stylelint (CSS) / html-validate (页面) /
#         node --test + c8 覆盖率门禁 95%
# 前端工具链版本锁在 package.json。独立 clone 先 `npm install` 自建
# node_modules; 从 My Home 组合仓的 apps/ 下跑时自动软链组合仓根的那份
# (本机与容器 /repo/apps/my-tesla 的相对路径二合一)。QNAP 宿主 node 缺
# ICU 数据, 静态检查在调试容器 mytesla-debug 里跑 (容器把组合仓挂在
# /repo); 别的机器有本地 node_modules 就直接宿主跑。
cd "$(dirname "$0")" || exit 1
rc=0

# pytest 的 tmp_path 优先放内存 (/dev/shm): 测试的 SQLite 种子库全在
# 内存里跑, 不跟机械盘抢 IO; 没有就退回仓库目录。
if [ -d /dev/shm ] && [ -w /dev/shm ]; then
  mkdir -p /dev/shm/mytesla-pytest
  export TMPDIR=/dev/shm/mytesla-pytest
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

# 前端工具链: 组合仓内跑 (apps/<name> 下) 时软链组合仓根的 node_modules,
# 相对路径统一; 独立 clone 由 npm install 自建
if [ ! -e node_modules ] && [ -d ../../node_modules/eslint ]; then
  ln -s ../../node_modules node_modules
fi
if [ ! -d node_modules/eslint ]; then
  echo "跳过前端检查: 没有 node_modules (npm install 后再跑)" >&2
  exit $rc
fi

FRONT="node node_modules/eslint/bin/eslint.js app/home/static app/tesla/static/js tests/js \
   && node node_modules/typescript/bin/tsc -p tsconfig.json \
   && node node_modules/stylelint/bin/stylelint.mjs 'app/*/static/css/*.css' \
   && node node_modules/html-validate/bin/html-validate.mjs 'app/*/static/*.html'"

DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker
if $DOCKER exec mytesla-debug true 2>/dev/null; then
  # QNAP 部署: 宿主 node 缺 ICU, 工具链在调试容器里跑 (本仓 = /repo/apps/my-tesla,
  # 软链的 node_modules 在容器内解析到 /repo/node_modules)
  if ! $DOCKER exec mytesla-debug sh -c "cd /repo/apps/my-tesla && $FRONT"; then
    echo "前端静态检查失败 (或调试容器 mytesla-debug 未运行)" >&2
    rc=1
  fi
else
  sh -c "$FRONT" || rc=1
fi

# 单元测试 + 覆盖率门禁: 只统计纯逻辑模块 (页面脚本由 E2E 覆盖)
node node_modules/c8/bin/c8.js \
  --include 'app/tesla/static/js/gcj02.js' \
  --include 'app/tesla/static/js/trackutil.js' \
  --include 'app/tesla/static/js/track-animation.js' \
  --include 'app/tesla/static/js/format.js' \
  --include 'app/tesla/static/js/trip-playback.js' \
  --include 'app/tesla/static/js/lastpage.js' \
  --check-coverage --lines 95 --branches 95 --functions 95 \
  --reporter text node --test tests/js/*.test.mjs || rc=1

exit $rc
