"""
observe.py
Turns the live page into a compact, model-readable observation: a list of
interactive elements (with accessible names) plus the visible text. Page text
is passed through guard.sanitize_text first.
"""

from . import guard

MAX_TEXT = 1500
MAX_ELEMENTS = 40

_COLLECT_JS = """
() => {
  const sel = 'a[href], button, input, select, textarea, [role="button"], [role="link"]';
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    const labelEl = el.id ? document.querySelector('label[for="' + el.id + '"]') : null;
    const name = (el.getAttribute('aria-label') || (labelEl && labelEl.innerText) ||
                  el.getAttribute('placeholder') || el.innerText || el.value || el.getAttribute('title') || '')
                 .trim().replace(/\\s+/g, ' ').slice(0, 80);
    el.setAttribute('data-bta-id', String(i));
    out.push({
      id: i, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
      name: name, href: el.tagName === 'A' ? el.href : ''
    });
    i += 1;
  }
  return out;
}
"""


def observe(page) -> dict:
    """Snapshot of the page. Tags interactive elements with data-bta-id so actions can find them."""
    elements = page.evaluate(_COLLECT_JS)[:MAX_ELEMENTS]
    raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")[:MAX_TEXT]
    text, flags = guard.sanitize_text(raw_text)
    title = page.title()
    for value in [title] + [e["name"] for e in elements] + [e["href"] for e in elements]:
        flags.extend(guard.scan(value))
    return {"url": page.url, "title": title, "text": text, "elements": elements, "injection_flags": flags}


REMOVED = "[removed: possible prompt injection]"


def _clean(value: str) -> str:
    """Anything the model reads is scanned: an attacker can hide instructions in labels, titles or URLs too."""
    return REMOVED if guard.scan(value) else value


def render(observation: dict) -> str:
    """Plain-text form of an observation, for the model prompt. Raw values stay in the observation
    (the runner needs real hrefs for its host check); only this text goes to the model."""
    lines = [f"URL: {_clean(observation['url'])}", f"Title: {_clean(observation['title'])}", "Interactive elements:"]
    for e in observation["elements"]:
        kind = e["tag"] + (f"[{e['type']}]" if e["type"] else "")
        extra = f" -> {_clean(e['href'])}" if e["href"] else ""
        lines.append(f'  - {kind} "{_clean(e["name"])}"{extra}')
    lines.append("Visible text:")
    lines.append(observation["text"])
    return "\n".join(lines)
