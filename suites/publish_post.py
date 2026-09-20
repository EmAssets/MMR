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

# The byline. wp-cli over SSH has no logged-in user, so a post created without
# this lands with post_author=0 -- no byline at all, which WordPress renders as
# blank or falls back to whatever the theme guesses. Set explicitly.
WP_AUTHOR = os.environ.get("WP_AUTHOR", "emergent2")


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
        # A bare X/Twitter or YouTube URL on its own line becomes a native
        # embed block. An embed beats a screenshot for someone else's post: it
        # stays current, it carries attribution and engagement figures the
        # author controls, and it cannot be accused of a selective crop.
        memb = re.fullmatch(r"(https?://(?:(?:www\.)?(?:twitter|x)\.com/\S+/status/\d+"
                            r"|(?:www\.)?youtube\.com/watch\?v=\S+|youtu\.be/\S+))", st)
        if memb:
            url = memb.group(1)
            if "youtu" in url:
                prov, cls = "youtube", "wp-embed-aspect-16-9 wp-has-aspect-ratio"
            else:
                prov, cls = "twitter", ""
            attrs = (chr(123) + chr(34) + "url" + chr(34) + ":" + chr(34) + url + chr(34)
                     + "," + chr(34) + "type" + chr(34) + ":" + chr(34) + "rich" + chr(34)
                     + "," + chr(34) + "providerNameSlug" + chr(34) + ":" + chr(34) + prov
                     + chr(34) + "," + chr(34) + "responsive" + chr(34) + ":true" + chr(125))
            fig = ("<figure class=" + chr(34) + "wp-block-embed is-type-rich "
                   + "is-provider-" + prov + " wp-block-embed-" + prov
                   + ((" " + cls) if cls else "") + chr(34) + ">"
                   + "<div class=" + chr(34) + "wp-block-embed__wrapper" + chr(34) + ">"
                   + url + "</div></figure>")
            out.append("<!-- wp:embed " + attrs + " -->" + chr(10) + fig
                       + chr(10) + "<!-- /wp:embed -->")
            i += 1
            continue
        mimg = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", st)
        if mimg:
            alt, url = mimg.group(1), mimg.group(2)
            cap = ("<figcaption class=" + chr(34) + "wp-element-caption" + chr(34) + ">"
                   + _inline(alt) + "</figcaption>") if alt else ""
            fig = ("<figure class=" + chr(34) + "wp-block-image size-large" + chr(34) + ">"
                   + "<img src=" + chr(34) + html.escape(url, quote=True) + chr(34)
                   + " alt=" + chr(34) + html.escape(alt, quote=True) + chr(34) + "/>"
                   + cap + "</figure>")
            out.append("<!-- wp:image -->" + chr(10) + fig + chr(10) + "<!-- /wp:image -->")
            i += 1
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


def find_by_slug(slug: str, ptype: str = "post") -> dict | None:
    """The post with this slug, any status, or None.

    `wp post list --name=<slug>` does not reliably filter non-published posts on
    this host -- it returned [] for a draft that was plainly present. Idempotence
    depends on this lookup, because a miss creates a SECOND draft of the same
    post, so the slug is matched here rather than trusted to the flag.
    """
    rc, out, err = ssh("cd ~/%s && wp post list --post_type=%s --post_status=any "
                       "--fields=ID,post_status,post_title,post_name,post_modified "
                       "--format=json" % (WP_ROOT, ptype))
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


def upload_images(md: str, src_dir: Path, slug: str) -> tuple[str, list]:
    """Upload every local image the markdown references; rewrite to media URLs.

    Markdown pointing at a file on this machine is useless once published, so
    each local `![alt](path)` is sent to the WordPress media library and the
    reference rewritten to the uploaded URL. Remote URLs are left alone.

    Uploads are keyed by filename: re-running does not create a second copy of
    the same screenshot, for the same reason the post itself is idempotent.
    """
    done = []
    for alt, rel in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", md):
        if rel.startswith(("http://", "https://")):
            continue
        local = (src_dir / rel).resolve()
        if not local.exists():
            print("  [warn] image not found, left as-is: %s" % rel)
            continue
        name = local.name
        rc, out, _ = ssh("cd ~/%s && wp post list --post_type=attachment "
                         "--post_status=any --fields=ID,post_title --format=json" % WP_ROOT)
        existing = None
        try:
            for r in json.loads(out.strip() or "[]"):
                if str(r.get("post_title", "")).lower() == local.stem.lower():
                    existing = r["ID"]
                    break
        except ValueError:
            pass
        if existing:
            aid = existing
            print("  image already uploaded: %s (id %s)" % (name, aid))
        else:
            remote = "/tmp/mmr-img-%s" % name
            pr = subprocess.run(
                ["ssh", "-p", SSH_PORT, "-i", SSH_KEY, "-o", "BatchMode=yes",
                 "%s@%s" % (SSH_USER, SSH_HOST), "cat > %s" % remote],
                input=local.read_bytes(), capture_output=True, timeout=600)
            if pr.returncode != 0:
                print("  [warn] upload failed for %s" % name)
                continue
            rc, out, err = ssh("cd ~/%s && wp media import %s --title=%s --alt=%s "
                               "--porcelain 2>&1" % (WP_ROOT, remote, _q(local.stem), _q(alt)))
            ssh("rm -f %s" % remote)
            aid = (out.strip().splitlines() or ["?"])[-1].strip()
            if not aid.isdigit():
                print("  [warn] media import said: %s" % out.strip()[:160])
                continue
            print("  uploaded %s -> attachment %s" % (name, aid))
        rc, out, _ = ssh("cd ~/%s && wp post get %s --field=guid" % (WP_ROOT, aid))
        url = out.strip().splitlines()[-1].strip() if out.strip() else ""
        if url:
            md = md.replace("(%s)" % rel, "(%s)" % url)
            done.append({"file": name, "id": aid, "url": url, "alt": alt})
    return md, done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="markdown source")
    ap.add_argument("--title", default="")
    ap.add_argument("--slug", required=True, help="stable slug; re-running UPDATES this draft")
    ap.add_argument("--excerpt", default="")
    ap.add_argument("--category", default="", help="category name; created if absent")
    ap.add_argument("--as-page", dest="as_page", action="store_true",
                    help="publish as a PAGE rather than a post -- for evergreen "
                         "explainers every article links to")
    ap.add_argument("--rename-from", dest="rename_from", default="",
                    help="previous slug, when changing it. Without this the lookup "
                         "misses and a SECOND post is created.")
    ap.add_argument("--focus-kw", dest="focus_kw", default="",
                    help="Yoast focus keyphrase")
    ap.add_argument("--metadesc", default="",
                    help="Yoast meta description; 120-158 chars or it is truncated "
                         "in search results. Defaults to --excerpt.")
    ap.add_argument("--author", default=WP_AUTHOR,
                    help="WordPress user login or ID for the byline "
                         "(default %s)" % WP_AUTHOR)
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
    md, imgs = ("", []) if False else upload_images(md, Path(a.file).parent, a.slug)         if not a.render_only else (md, [])
    if imgs:
        print("  %d image(s) in media library" % len(imgs))
    body = to_blocks(md)

    local = ROOT / "publish" / ("post-%s.html" % a.slug)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(body, encoding="utf-8")
    print("[post] %s" % (title or a.slug))
    print("  %d blocks, %d bytes -> %s" % (body.count("<!-- wp:"), len(body), local))
    if a.render_only:
        print("  --render-only: nothing sent.")
        return

    ptype = "page" if a.as_page else "post"
    found = find_by_slug(a.slug, ptype)
    if not found and a.rename_from:
        found = find_by_slug(a.rename_from, ptype)
        if found:
            print("  renaming slug %s -> %s (post %s)"
                  % (a.rename_from, a.slug, found["ID"]))

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

    # Resolve the author to an ID once, so a typo fails here rather than silently
    # producing an unattributed post.
    author_id = ""
    if a.author:
        rc, out, _ = ssh("cd ~/%s && wp user get %s --field=ID 2>&1"
                         % (WP_ROOT, _q(a.author)))
        cand = (out.strip().splitlines() or [""])[-1].strip()
        if cand.isdigit():
            author_id = cand
        else:
            raise SystemExit("no such WordPress user %r -- refusing to publish an "
                             "unattributed post. `wp user list` shows the logins."
                             % a.author)

    common = ("--post_status=draft --post_type=" + ptype +
              " --post_title=" + _q(title or a.slug) +
              " --post_name=" + _q(a.slug))
    if a.excerpt:
        common += " --post_excerpt=%s" % _q(a.excerpt)
    if author_id:
        common += " --post_author=%s" % author_id

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

    # Yoast fields. The site runs wordpress-seo and its other posts carry these,
    # so a post without them is the odd one out: no focus keyphrase, no meta
    # description, and Google writes its own snippet from whatever it finds.
    md_desc = a.metadesc or a.excerpt
    if md_desc:
        if not 120 <= len(md_desc) <= 158:
            print("  [note] meta description is %d chars; 120-158 is the range that "
                  "survives truncation in search results" % len(md_desc))
        ssh("cd ~/%s && wp post meta update %s _yoast_wpseo_metadesc %s"
            % (WP_ROOT, pid, _q(md_desc)))
    if a.focus_kw:
        ssh("cd ~/%s && wp post meta update %s _yoast_wpseo_focuskw %s"
            % (WP_ROOT, pid, _q(a.focus_kw)))
        print("  yoast: focus keyphrase %r" % a.focus_kw)
    print("  %s (id %s), status DRAFT, author %s (%s)"
          % (action, pid, a.author, author_id))
    print("  review at: https://emergencemachine.com/wp-admin/post.php?post=%s&action=edit" % pid)
    print("  it stays a draft until you publish it yourself -- this tool cannot.")


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
