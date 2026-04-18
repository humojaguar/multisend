#!/usr/bin/env python3
"""
multisend — telegram-send with multiple bot support
Usage: multisend [OPTIONS] MESSAGE
       echo "text" | multisend [OPTIONS]
"""

import argparse
import configparser
import logging
import logging.handlers
import os
import sys
import json
import mimetypes
from pathlib import Path
from urllib import request, parse, error
import urllib.request

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "multisend"
CONFIG_FILE = CONFIG_DIR / "config.ini"

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

LOG_FILE = CONFIG_DIR / "multisend.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5

log = logging.getLogger("multisend")


def setup_logging(log_file: Path = None):
    log_file = log_file or LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)


# ── Telegram API ────────────────────────────────────────────────────────────

def api_call(token: str, method: str, payload: dict) -> dict:
    url = TELEGRAM_API.format(token=token, method=method)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except error.HTTPError as e:
        body = json.loads(e.read())
        raise RuntimeError(f"Telegram error {e.code}: {body.get('description', 'unknown')}")
    except error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


def send_text(token: str, chat_id: str, text: str, parse_mode: str = None,
              disable_preview: bool = False, silent: bool = False) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_preview:
        payload["link_preview_options"] = {"is_disabled": True}
    if silent:
        payload["disable_notification"] = True
    return api_call(token, "sendMessage", payload)


def send_photo(token: str, chat_id: str, path: str, caption: str = None,
               silent: bool = False) -> dict:
    return _send_file(token, chat_id, path, caption, "sendPhoto", "photo", silent)


def send_document(token: str, chat_id: str, path: str, caption: str = None,
                  silent: bool = False) -> dict:
    return _send_file(token, chat_id, path, caption, "sendDocument", "document", silent)


def _send_file(token: str, chat_id: str, filepath: str, caption: str,
               method: str, field: str, silent: bool) -> dict:
    import multipart  # only if needed — fall back to urllib multipart below
    raise NotImplementedError("Use _send_file_urllib instead")


def send_file_urllib(token: str, chat_id: str, filepath: str, caption: str,
                     method: str, field: str, silent: bool) -> dict:
    """Multipart file upload without requests dependency."""
    url = TELEGRAM_API.format(token=token, method=method)
    boundary = "----MultisendBoundary7f3a91b"
    path = Path(filepath)
    mime = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

    body = b""
    # chat_id field
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode()
    # silent field
    if silent:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"disable_notification\"\r\n\r\ntrue\r\n".encode()
    # caption field
    if caption:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode()
    # file field
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode()
    body += path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except error.HTTPError as e:
        body_resp = json.loads(e.read())
        raise RuntimeError(f"Telegram error {e.code}: {body_resp.get('description', 'unknown')}")
    except error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


# ── Config ──────────────────────────────────────────────────────────────────

def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        cfg.read(CONFIG_FILE)
    return cfg


def save_config(cfg: configparser.ConfigParser):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        cfg.write(f)
    CONFIG_FILE.chmod(0o600)


def get_bot_names(cfg: configparser.ConfigParser) -> list:
    return [s for s in cfg.sections() if s != "DEFAULT"]


def resolve_bots(cfg: configparser.ConfigParser, names: list, all_bots: bool) -> list:
    """Return list of (name, token, chat_id) tuples."""
    bot_names = get_bot_names(cfg)
    if not bot_names:
        raise RuntimeError("No bots configured. Run: multisend --configure")

    if all_bots:
        targets = bot_names
    elif names:
        targets = names
    else:
        # Default: first bot, or bot marked default=yes
        default = next(
            (n for n in bot_names if cfg[n].getboolean("default", fallback=False)),
            bot_names[0]
        )
        targets = [default]

    result = []
    for name in targets:
        if name not in cfg:
            raise RuntimeError(f"Unknown bot: '{name}'. Available: {', '.join(bot_names)}")
        token = cfg[name].get("token")
        chat_id = cfg[name].get("chat_id")
        if not token or not chat_id:
            raise RuntimeError(f"Bot '{name}' is missing token or chat_id in config.")
        result.append((name, token, chat_id))
    return result


# ── Interactive configure ────────────────────────────────────────────────────

def cmd_configure(args):
    cfg = load_config()
    print("multisend — bot configuration")
    print("─" * 36)

    if args.bot:
        bot_name = args.bot
    else:
        bot_name = input("Bot profile name (e.g. homelab, alerts): ").strip()
    if not bot_name:
        print("Error: name cannot be empty.", file=sys.stderr)
        sys.exit(1)

    existing = cfg[bot_name] if bot_name in cfg else {}
    token = input(f"Bot token [{existing.get('token', '')}]: ").strip() or existing.get("token", "")
    chat_id = input(f"Chat ID  [{existing.get('chat_id', '')}]: ").strip() or existing.get("chat_id", "")

    if not token or not chat_id:
        print("Error: token and chat_id are required.", file=sys.stderr)
        sys.exit(1)

    if bot_name not in cfg:
        cfg[bot_name] = {}
    cfg[bot_name]["token"] = token
    cfg[bot_name]["chat_id"] = chat_id

    # Ask if default
    if not any(cfg[n].getboolean("default", fallback=False) for n in get_bot_names(cfg) if n != bot_name):
        make_default = input("Make this the default bot? [Y/n]: ").strip().lower()
        if make_default != "n":
            cfg[bot_name]["default"] = "yes"

    save_config(cfg)
    print(f"\n✓ Bot '{bot_name}' saved to {CONFIG_FILE}")

    # Verify
    try:
        resp = api_call(token, "getMe", {})
        username = resp["result"].get("username", "?")
        print(f"✓ Connected as @{username}")
    except Exception as e:
        print(f"⚠  Could not verify token: {e}", file=sys.stderr)


def cmd_list(args):
    cfg = load_config()
    bots = get_bot_names(cfg)
    if not bots:
        print("No bots configured. Run: multisend --configure")
        return
    print(f"{'NAME':<20} {'CHAT ID':<18} {'DEFAULT'}")
    print("─" * 52)
    for name in bots:
        chat_id = cfg[name].get("chat_id", "")
        is_default = "yes" if cfg[name].getboolean("default", fallback=False) else ""
        token_preview = cfg[name].get("token", "")
        token_preview = token_preview[:8] + "…" if len(token_preview) > 8 else token_preview
        print(f"{name:<20} {chat_id:<18} {is_default}")


def cmd_remove(args):
    cfg = load_config()
    bot = args.bot
    if bot not in cfg:
        print(f"Error: bot '{bot}' not found.", file=sys.stderr)
        sys.exit(1)
    cfg.remove_section(bot)
    save_config(cfg)
    print(f"✓ Removed bot '{bot}'")


def cmd_default(args):
    cfg = load_config()
    bot = args.bot
    if bot not in cfg:
        print(f"Error: bot '{bot}' not found.", file=sys.stderr)
        sys.exit(1)
    for name in get_bot_names(cfg):
        if "default" in cfg[name]:
            del cfg[name]["default"]
    cfg[bot]["default"] = "yes"
    save_config(cfg)
    print(f"✓ Default bot set to '{bot}'")


# ── Send ─────────────────────────────────────────────────────────────────────

def do_send(args):
    cfg = load_config()

    bot_names = [b.strip() for b in args.bot.split(",")] if args.bot else []
    targets = resolve_bots(cfg, bot_names, args.all)

    # Determine message text
    if args.file or args.image or args.video:
        text = args.message or args.caption or None
    elif not sys.stdin.isatty() and not args.message:
        text = sys.stdin.read().rstrip("\n")
    elif args.message:
        text = args.message
    else:
        print("Error: provide a message or pipe text via stdin.", file=sys.stderr)
        sys.exit(1)

    errors = []
    for name, token, chat_id in targets:
        try:
            if args.image:
                resp = send_file_urllib(token, chat_id, args.image, text,
                                        "sendPhoto", "photo", args.silent)
            elif args.video:
                resp = send_file_urllib(token, chat_id, args.video, text,
                                        "sendVideo", "video", args.silent)
            elif args.file:
                resp = send_file_urllib(token, chat_id, args.file, text,
                                        "sendDocument", "document", args.silent)
            else:
                parse_mode = None
                if args.markdown:
                    parse_mode = "MarkdownV2"
                elif args.html:
                    parse_mode = "HTML"
                resp = send_text(token, chat_id, text, parse_mode=parse_mode,
                                 disable_preview=args.no_preview, silent=args.silent)

            msg_id = resp.get("result", {}).get("message_id", "?")
            log.info("sent bot=%s chat_id=%s message_id=%s", name, chat_id, msg_id)
            if not args.quiet:
                print(f"✓ [{name}] sent (message_id={msg_id})")
        except Exception as e:
            errors.append((name, str(e)))
            log.error("failed bot=%s chat_id=%s error=%s", name, chat_id, e)
            print(f"✗ [{name}] {e}", file=sys.stderr)

    if errors:
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="multisend",
        description="Send Telegram messages via multiple named bot profiles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  multisend "hello world"                  # send via default bot
  multisend -b alerts "disk usage 95%%"    # send via 'alerts' bot
  multisend -b homelab,alerts "rebooting"  # send to multiple bots
  multisend --all "deploy done"            # send to all configured bots
  echo "done" | multisend -b homelab      # pipe stdin
  multisend --image /tmp/graph.png "Q3"   # send image with caption
  multisend --configure                    # add/edit a bot profile
  multisend --list                         # list configured bots
        """
    )

    # Send options
    p.add_argument("message", nargs="?", help="Message text (or pipe via stdin)")
    p.add_argument("-b", "--bot", metavar="NAME[,NAME…]",
                   help="Target bot profile(s), comma-separated")
    p.add_argument("--all", action="store_true",
                   help="Send to all configured bots")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="Suppress output on success")
    p.add_argument("--silent", action="store_true",
                   help="Send without notification sound")
    p.add_argument("--no-preview", action="store_true",
                   help="Disable link preview")
    p.add_argument("--markdown", action="store_true",
                   help="Parse message as MarkdownV2")
    p.add_argument("--html", action="store_true",
                   help="Parse message as HTML")
    p.add_argument("--image", metavar="PATH",
                   help="Send an image file")
    p.add_argument("--video", metavar="PATH",
                   help="Send a video file (inline playback)")
    p.add_argument("--file", metavar="PATH",
                   help="Send a file as document")
    p.add_argument("--caption", metavar="TEXT",
                   help="Caption for --image, --video, or --file")

    # Management subcommands
    p.add_argument("--configure", action="store_true",
                   help="Add or edit a bot profile interactively")
    p.add_argument("--list", action="store_true",
                   help="List configured bots")
    p.add_argument("--remove", metavar="NAME",
                   help="Remove a bot profile")
    p.add_argument("--set-default", metavar="NAME",
                   help="Set the default bot")
    p.add_argument("--config-file", action="store_true",
                   help="Print config file path")
    p.add_argument("--log-file", metavar="PATH",
                   help=f"Log file path (default: {LOG_FILE})")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(Path(args.log_file) if args.log_file else None)

    # Management commands
    if args.config_file:
        print(CONFIG_FILE)
        return

    if args.configure:
        cmd_configure(args)
        return

    if args.list:
        cmd_list(args)
        return

    if args.remove:
        class _a: bot = args.remove
        cmd_remove(_a())
        return

    if args.set_default:
        class _a: bot = args.set_default
        cmd_default(_a())
        return

    # Send mode
    do_send(args)


if __name__ == "__main__":
    main()
