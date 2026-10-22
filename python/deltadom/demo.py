import argparse
import asyncio
import json
import platform
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from playwright.async_api import async_playwright

from . import DeltaBrowser, DeltaSession, StateMirror
from .runtime import launch_browser


@contextmanager
def fixture_server():
    html = files("deltadom").joinpath("fixture.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/api/products":
                payload = json.dumps(
                    {
                        "items": [
                            {
                                "name": "Rust toolkit",
                                "price": 19,
                                "description": "Full description from local fixture",
                                "secret": "API-SECRET-SENTINEL",
                            },
                            {"name": "DOM toolkit", "price": 29, "description": "Second record"},
                        ]
                    }
                ).encode()
                content_type = "application/json"
            else:
                payload, content_type = html, "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def run(
    channel=None,
    output="artifacts/demo.json",
    headed=False,
    *,
    delay=0,
    tokens=False,
    keep_open=False,
):
    tokenizer = None
    if tokens:
        try:
            import tiktoken
        except ImportError:
            raise ValueError(
                "Token measurement needs tiktoken. Run without --tokens, or install it."
            ) from None
        tokenizer = tiktoken.get_encoding("cl100k_base")
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    transcript = []

    def emit(line):
        transcript.append(line)
        print(line, flush=True)

    emit("DeltaDOM / real browser demo")
    emit("Local sample page. No API key. No model calls.")
    emit("")
    emit(f"{'STEP':<22} {'FRAME':<6} {'NODES':>6} {'FULL BYTES':>11} {'SENT BYTES':>11}  CHECK")
    with fixture_server() as url:
        async with async_playwright() as p:
            browser, selected_channel = await launch_browser(p, channel, headless=not headed)
            page = await browser.new_page(viewport={"width": 1040, "height": 760})
            mirror, observations = StateMirror(), []
            full_session = DeltaSession()
            async with DeltaBrowser(
                page, api_fields={url + "/api/products": ["name", "price", "description"]}
            ) as delta:
                await page.goto(url, wait_until="domcontentloaded")

                async def record(label):
                    obs = await delta.observe()
                    rebuilt = mirror.apply(obs.frame)
                    assert rebuilt == list(obs.nodes), (
                        "patch must reconstruct the exact captured tree"
                    )
                    # Matched baseline: identical semantic content, full tree sent at each step.
                    full = json.dumps(list(obs.nodes), ensure_ascii=False, separators=(",", ":"))
                    full_compressed = json.loads(
                        full_session.process_frame(
                            json.dumps(
                                {
                                    "document": obs.frame["document"],
                                    "url": obs.frame["url"],
                                    "nodes": list(obs.nodes),
                                }
                            ),
                            True,
                        )
                    )["text"]
                    observations.append(
                        {
                            "label": label,
                            "frame": obs.frame,
                            "api": list(obs.api),
                            "settle": obs.settle,
                            "warnings": list(obs.warnings),
                            "timings_ms": obs.timings_ms,
                            "node_count": len(obs.nodes),
                            "reconstruction_equal": rebuilt == list(obs.nodes),
                            "full_semantic_bytes": len(full.encode("utf-8")),
                            "full_compressed_bytes": len(full_compressed.encode("utf-8")),
                            "transmitted_dom_bytes": len(obs.frame["text"].encode("utf-8")),
                            "observation_bytes_including_api": len(obs.text.encode("utf-8")),
                        }
                    )
                    if tokenizer:
                        observations[-1].update(
                            {
                                "full_semantic_tokens": len(tokenizer.encode(full)),
                                "full_compressed_tokens": len(tokenizer.encode(full_compressed)),
                                "transmitted_dom_tokens": len(tokenizer.encode(obs.frame["text"])),
                                "observation_tokens_including_api": len(tokenizer.encode(obs.text)),
                            }
                        )
                    row = observations[-1]
                    emit(
                        f"{label:<22} {obs.frame['kind']:<6} {len(obs.nodes):>6} "
                        f"{row['full_semantic_bytes']:>11,} {row['transmitted_dom_bytes']:>11,}  OK"
                    )
                    if delay:
                        await asyncio.sleep(delay)
                    return obs

                obs = await record("initial")
                obs = await record("unchanged")
                await delta.act(
                    obs, obs.find(tag="input", attr=("name", "query"))[0]["id"], "fill", "Rust"
                )
                obs = await record("fill")
                await delta.act(obs, obs.find(tag="button", attr=("id", "load"))[0]["id"], "click")
                await page.get_by_text("Loaded 2 API records", exact=True).wait_for()
                obs = await record("api")
                assert obs.api and "API-SECRET-SENTINEL" not in obs.text
                await delta.act(obs, obs.find(tag="button", attr=("id", "sort"))[0]["id"], "click")
                obs = await record("reorder")
                # A product remains actionable after repeated subtrees are compressed / reordered.
                # Choose an exact live product through its subtree text, without a CSS ID mutation.
                text = obs.find(tag="#text", text="Choose 7")[0]
                button_id = text["parent"]
                await delta.act(obs, button_id, "click")
                await page.get_by_text("Selected product 7", exact=True).wait_for()
                obs = await record("choose")
                await delta.act(obs, obs.find(tag="button", attr=("id", "add"))[0]["id"], "click")
                obs = await record("add")
                old_document = obs.frame["document"]
                await page.reload(wait_until="domcontentloaded")
                obs = await record("same_url_reload")
                assert obs.frame["kind"] == "full" and obs.frame["document"] != old_document
                screenshot = str(Path(output).with_suffix(".png"))
                await page.screenshot(path=screenshot)
                if keep_open:
                    await asyncio.to_thread(input, "Press Enter to close the demo browser… ")
            browser_version = browser.version
            await browser.close()
    # Store complete captured states, not only patches, in the checked stream.
    from .recording import inspect_tape
    from .tape import TapeWriter

    tape_path = output.with_suffix(".ddt")
    if tape_path.exists():
        from uuid import uuid4

        tape_path = tape_path.with_stem(tape_path.stem + "-" + uuid4().hex[:8])
    mirror = StateMirror()
    with TapeWriter(tape_path) as tape:
        for row in observations:
            tape.add(
                json.dumps(
                    {
                        "label": row["label"],
                        "document": row["frame"]["document"],
                        "url": row["frame"]["url"],
                        "nodes": mirror.apply(row["frame"]),
                        "api": row["api"],
                        "settle": row["settle"],
                        "warnings": row["warnings"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
    tape_report = inspect_tape(tape_path)
    result = {
        "recording": str(tape_path),
        "recording_verification": tape_report,
        "scope": "local deterministic fixture; no LLM; no Browser Use baseline",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "browser": browser_version,
        "channel": selected_channel,
        "playwright": version("playwright"),
        "steps": len(observations),
        "reconstruction_equal": all(x["reconstruction_equal"] for x in observations),
        "full_semantic_bytes": sum(x["full_semantic_bytes"] for x in observations),
        "full_compressed_bytes": sum(x["full_compressed_bytes"] for x in observations),
        "transmitted_dom_bytes": sum(x["transmitted_dom_bytes"] for x in observations),
        "observations": observations,
        "not_run": [
            "model task success",
            "end-to-end model speedup",
            "Browser Use integration",
            "WebArena",
        ],
    }
    if tokenizer:
        baseline = sum(x["full_semantic_tokens"] for x in observations)
        transmitted = sum(x["transmitted_dom_tokens"] for x in observations)
        compressed = sum(x["full_compressed_tokens"] for x in observations)
        result.update(
            {
                "tokenizer": "cl100k_base",
                "full_semantic_tokens": baseline,
                "transmitted_dom_tokens": transmitted,
                "full_compressed_tokens": compressed,
                "delta_reduction_vs_full_compressed": 1 - transmitted / compressed,
                "dom_token_reduction": 1 - transmitted / baseline,
            }
        )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit("")
    emit(
        f"Verified {len(observations)}/{len(observations)}: every frame reconstructs the captured nodes."
    )
    emit("FULL = complete semantic JSON. SENT = new DOM text; excludes API and prompt history.")
    emit("Local sample only; bytes are not tokens, model cost, or task success.")
    emit(f"Results: {output}")
    emit(f"Screenshot: {output.with_suffix('.png')}")
    emit(f"Offline replay: deltadom replay {tape_path}")
    output.with_suffix(".txt").write_text("\n".join(transcript) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    parser.add_argument("--output", default="artifacts/demo.json")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--tokens", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.channel, args.output, args.headed, tokens=args.tokens))


if __name__ == "__main__":
    main()
