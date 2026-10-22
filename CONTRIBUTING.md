# 开发与贡献

普通使用者无需构建；安装体验包见 [START_HERE.md](START_HERE.md)。下面是修改源码的路径。

## 环境

Python 3.12+、Rust stable、uv，以及 Chrome 或 Playwright Chromium。

```sh
uv venv --python 3.12
uv pip sync requirements-dev.lock
source .venv/bin/activate
maturin develop --release --locked
python -m playwright install chromium
deltadom demo
```

## 验证

```sh
cargo test --locked
cargo clippy --all-targets -- -D warnings
ruff check python tests examples install.py scripts
pytest -q
```

使用系统 Chrome 时：`DELTADOM_CHANNEL=chrome pytest -q`。

测试使用真实浏览器和本地样例页面。运行 `deltadom demo --headless` 可生成独立记录；添加 `--tokens` 可额外使用开发依赖中的 tiktoken 进行测量（首次可能下载 tokenizer 数据）。默认演示只按字节计量。不要将字节量、token、费用和任务成功率混为一谈。

## 制作预览包

```sh
maturin build --release --locked --out dist
python scripts/package_preview.py dist/deltadom-0.4.0-cp312-abi3-macosx_11_0_arm64.whl
python scripts/verify_preview.py dist/DeltaDOM-0.4.0-macosx_11_0_arm64.zip
```

将命令中的 wheel 文件名替换为实际构建的平台。当前只验证 Apple 芯片 Mac；其他系统构建成功并不自动等于完成安装验证。

预览包只包含白名单文件，不打包开发环境、用户数据或仓库历史。安装器始终使用 `--only-binary`。本地打包不会上传任何文件。

## 改动原则

- 先写清用户能观察到的行为，再改最小必要代码。
- 差分必须能恢复当前语义树；压缩不能丢掉稳定 ID、文字或属性。
- 将真实测量与推测分开；不要把字节量、token、费用、成功率互相替代。
- 面向首次使用者保持简单命令、明确错误和可访问的运行结果。
- 源码采用 MIT；第三方材料见 THIRD_PARTY_NOTICES.md。请勿提交真实账号数据或个人浏览记录。

## GitHub CI 模板

发布仓库的 `ci/check.yml` 为多平台构建模板，尚未启用。发布凭据缺少 workflow 权限；本次发布依赖上述本地 Mac 验证，不声称云端或 Windows/Linux 安装通过。维护者取得相应权限后，可将模板放入 `.github/workflows/check.yml` 启用。
