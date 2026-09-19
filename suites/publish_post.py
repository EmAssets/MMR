"""Publish a series post to WordPress as a DRAFT — repeatable, idempotent, never public.

Written for a blog series, so the mechanics are the same every time: take a
markdown file, convert it to Gutenberg blocks, create or update a draft on the
site, and stop. The operator reviews and toggles visibility themselves.

WHY DRAFT-ONLY, ENFORCED IN CODE. `post_status` is hardcoded to `draft` and there
is no flag to change it. Publishing is a judgement about whether a piece is ready,
and that judgement is not something a tool should be able to make on someone's
behalf — least of all a tool that could be re-run by a scheduler. To publish, open
the post and press the button.

IDEMPOTENT BY SLUG. Re-running with the same `--slug` UPDATES the existing draft
rather than creating a second one. A series means many revisions of the same post,
and a script that silently produces `my-post`, `my-post-2`, `my-post-3` is worse
than useless.

    python -m suites.publish_post --file post1.md --title "..." --slug what-i-track
    python -m suites.publish_post --file post1.md --slug what-i-track --show
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]

# The site, from the deploy tooling that already talks to it. Overridable by env
# so this file carries no assumption that cannot be changed without editing it.
SSH_HOST = os.environ.get("WP_SSH_HOST", "")
SSH_PORT = os.environ.get("WP_SSH_PORT", "22")
SSH_USER = os.environ.get("WP_SSH_USER", "")
SSH_KEY = os.environ.get("WP_SSH_KEY", str(Path.home() / ".ssh" / "emergencemachine"))
WP_ROOT = os.environ.get("WP_ROOT", "domains/emergencemachine.com/public_html")


def ssh(cmd: str, timeout=180) -> tuple[int, str, str]:
    r = subprocess.run(
        ["ssh", "-p", SSH_PORT, "-i", SSH_KEY, "-o", "BatchMode=yes",
         "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20",
         "%s@%s" % (SSH_USER, SSH_HOST), cmd],
        capture_output=True, timeout=timeout)
    return (r.returncode,
            (r.stdout or b"").decode("utf-8", "replace"),
            (r.stderr or b"").decode("utf-8", "replace"))


# --- markdown -> Gutenberg -------------------------------------------------
#
# Deliberately small. It handles exactly the constructs this series uses --
# headings, paragraphs, bullet and ordered lists, pipe tables, fenced code,
# blockquotes, rules -- and leaves anything else as a paragraph rather than
# guessing. A converter that silently mangles an unfamiliar construct is worse
# than one that passes it through visibly.

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def to_blocks(md: str) -> str:
    out, i = [], 0
    lines = md.split("\n")
    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if not st:
            i += 1
            continue
        if st.startswith("```"):
            lang = st[3:].strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            out.append("<!-- wp:code -->\n<pre class=\"wp-block-code\"><code>%s</code></pre>\n<!-- /wp:code -->"
                       % html.escape("\n".join(body), quote=False))
            continue
        if re.match(r"^#{1,4}\s", st):
            lvl = len(st) - len(st.lstrip("#"))
            txt = _inline(st[lvl:].strip())
            attrs = "" if lvl == 2 else ' {"level":%d}' % lvl
            out.append("<!-- wp:heading%s -->\n<h%d>%s</h%d>\n<!-- /wp:heading -->"
                       % (attrs, lvl, txt, lvl))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", st):
            out.append('<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->')
            i += 1
            continue
        if st.startswith(">"):
            body = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                body.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append('<!-- wp:quote -->\n<blockquote class="wp-block-quote"><p>%s</p></blockquote>\n<!-- /wp:quote -->'
                       % _inline(" ".join(body)))
            continue
        if st.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            def cells(r):
                return [c.strip() for c in r.strip().strip("|").split("|")]
            head = cells(lines[i])
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            t = ["<!-- wp:table -->", '<figure class="wp-block-table"><table><thead><tr>']
            t += ["<th>%s</th>" % _inline(h) for h in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in r) + "</tr>")
            t += ["</tbody></table></figure>", "<!-- /wp:table -->"]
            out.append("\n".join(t))
            continue
        m = re.match(r"^(\d+)\.\s", st)
        if st.startswith(("- ", "* ")) or m:
            ordered = bool(m)
            items = []
            while i < len(lines):
                s2 = lines[i].strip()
                if ordered and re.match(r"^\d+\.\s", s2):
                    items.append(re.sub(r"^\d+\.\s", "", s2))
                elif (not ordered) and s2.startswith(("- ", "* ")):
                    items.append(s2[2:])
                else:
                    break
                i += 1
            tag, attrs = ("ol", ' {"ordered":true}') if ordered else ("ul", "")
            out.append("<!-- wp:list%s -->\n<%s>\n%s\n</%s>\n<!-- /wp:list -->"
                       % (attrs, tag,
                          "\n".join("<li>%s</li>" % _inline(x) for x in items), tag))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|```|>|\||-\s|\*\s|\d+\.\s|-{3,}$)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append("<!-- wp:paragraph -->\n<p>%s</p>\n<!-- /wp:paragraph -->"
                       % _inline(" ".join(para)))
    return "\n\n".join(out)


def find_by_slug(slug: str) -> dict | None:
    """The post with this slug, any status, or None.

    `wp post list --name=<slug>` does not reliably filter non-published posts on
    this host -- it returned [] for a draft that was plainly present. Idempotence
    depends on this lookup, because a miss creates a SECOND draft of the same
    post, so the slug is matched here rather than trusted to the flag.
    """
    rc, out, err = ssh("cd ~/%s && wp post list --post_type=post --post_status=any "
                       "--fields=ID,post_status,post_title,post_name,post_modified "
                       "--format=json" % WP_ROOT)
    if rc != 0:
        raise SystemExit("cannot reach the site: %s" % (err.strip() or out.strip())[:300])
    try:
        rows = json.loads(out.strip() or "[]")
    except ValueError:
        return None
    for r in rows:
        if r.get("post_name") == slug:
            return r
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="markdown source")
    ap.add_argument("--title", default="")
    ap.add_argument("--slug", required=True, help="stable slug; re-running UPDATES this draft")
    ap.add_argument("--excerpt", default="")
    ap.add_argument("--category", default="", help="category name; created if absent")
    ap.add_argument("--show", action="store_true", help="just report the draft's state")
    ap.add_argument("--render-only", action="store_true",
                    help="write the converted HTML locally and touch nothing remote")
    a = ap.parse_args()

    if a.show:
        r = find_by_slug(a.slug)
        if not r:
            print("no post with slug %r yet" % a.slug)
        else:
            print("id %s  status %s  modified %s" % (r["ID"], r["post_status"],
                                                    r.get("post_modified")))
            print("  %s" % r.get("post_title"))
            print("  edit: https://emergencemachine.com/wp-admin/post.php?post=%s&action=edit"
                  % r["ID"])
        return

    if not a.file:
        raise SystemExit("--file is required unless --show")
    md = Path(a.file).read_text(encoding="utf-8")
    # A leading `# Title` becomes the post title, not body content -- WordPress
    # renders the title itself and a duplicate H1 is the classic tell.
    title = a.title
    m = re.match(r"^#\s+(.+)$", md.split("\n")[0].strip())
    if m and not title:
        title = m.group(1).strip()
        md = "\n".join(md.split("\n")[1:])
    body = to_blocks(md)

    local = ROOT / "publish" / ("post-%s.html" % a.slug)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(body, encoding="utf-8")
    print("[post] %s" % (title or a.slug))
    print("  %d blocks, %d bytes -> %s" % (body.count("<!-- wp:"), len(body), local))
    if a.render_only:
        print("  --render-only: nothing sent.")
        return

    found = find_by_slug(a.slug)

    # The body goes over stdin, never inside the remote command line: it is tens
    # of kilobytes with quotes, backticks and newratios in it, and shell-quoting
    # it would corrupt the post in ways that are tedious to spot.
    remote_tmp = "/tmp/mmr-post-%s.html" % a.slug
    p = subprocess.run(
        ["ssh", "-p", SSH_PORT, "-i", SSH_KEY, "-o", "BatchMode=yes",
         "%s@%s" % (SSH_USER, SSH_HOST), "cat > %s" % remote_tmp],
        input=body.encode("utf-8"), capture_output=True, timeout=300)
    if p.returncode != 0:
        raise SystemExit("upload of body failed: %s"
                         % (p.stderr or b"").decode("utf-8", "replace")[:300])

    common = ("--post_status=draft --post_type=post "
              "--post_title=%s --post_name=%s" % (_q(title or a.slug), _q(a.slug)))
    if a.excerpt:
        common += " --post_excerpt=%s" % _q(a.excerpt)

    if found:
        pid = found["ID"]
        cmd = ("cd ~/%s && wp post update %s %s --post_content=\"$(cat %s)\" 2>&1"
               % (WP_ROOT, pid, common, remote_tmp))
        action = "updated draft %s" % pid
    else:
        cmd = ("cd ~/%s && wp post create %s --post_content=\"$(cat %s)\" --porcelain 2>&1"
               % (WP_ROOT, common, remote_tmp))
        action = "created draft"
    rc, out, err = ssh(cmd, timeout=300)
    print("  %s" % (out.strip() or err.strip())[:400])
    if rc != 0:
        raise SystemExit("wp failed (rc=%d)" % rc)
    if not found:
        pid = out.strip().splitlines()[-1].strip() if out.strip() else "?"
    if a.category:
        ssh("cd ~/%s && wp post term add %s category %s 2>&1"
            % (WP_ROOT, pid, _q(a.category)))
    ssh("rm -f %s" % remote_tmp)
    print("  %s (id %s), status DRAFT" % (action, pid))
    print("  review at: https://emergencemachine.com/wp-admin/post.php?post=%s&action=edit" % pid)
    print("  it stays a draft until you publish it yourself -- this tool cannot.")


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
