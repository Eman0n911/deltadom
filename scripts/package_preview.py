"""Create an installable preview ZIP from an already built wheel; never publishes."""

import argparse
import shutil
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--binding-preview", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheel = args.wheel.resolve()
    if not wheel.is_file() or not wheel.name.startswith("deltadom-") or wheel.suffix!='.whl':
        parser.error("provide a built DeltaDOM wheel")
    platform_tag = wheel.stem.rsplit("-", 1)[-1]
    name = "DeltaDOM-" + wheel.name.split('-')[1] + '-' + platform_tag
    folder = root / "dist" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "wheels").mkdir(exist_ok=True)
    shutil.copy2(wheel, folder / "wheels" / wheel.name)
    for file in [
        "install.py",
        "run.py",
        "Start DeltaDOM.command",
        "START_HERE.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    ]:
        shutil.copy2(root / file, folder / file)
    (folder / "Start DeltaDOM.command").chmod(0o755)
    if args.binding_preview:
        shutil.copy2(root/'docs/BINDING-PREVIEW.md',folder/'START_HERE.md')
        launcher=folder/'Start DeltaDOM.command'
        launcher.write_text(launcher.read_text().replace('install.py "$@"','install.py --demo binding-demo "$@"'))
    archive = root / "dist" / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        # Deliberate allowlist: never package a local environment, keys or development state.
        for rel in [
            "install.py",
            "run.py",
            "Start DeltaDOM.command",
            "START_HERE.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "wheels/" + wheel.name,
        ]:
            z.write(folder / rel, name + "/" + rel)
    print(archive)


if __name__ == "__main__":
    main()
