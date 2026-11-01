import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

NEXTCLOUD_URL = os.environ["NEXTCLOUD_URL"].rstrip("/")
NOTES_USER = os.environ["NOTES_USER"]
NOTES_PASSWORD = os.environ["NOTES_PASSWORD"]
NOTES_CATEGORY = os.environ.get("NOTES_CATEGORY", "Voice")
NOTES_API_URL = f"{NEXTCLOUD_URL}/index.php/apps/notes/api/v1/notes"

TITLE_WORDS = 6
SHOPPING_LIST_TITLE = os.environ.get("SHOPPING_LIST_TITLE", "Shopping list")

# "take a note, buy milk" / "note down that ..." / "write down: ..." -> everything after the trigger phrase is the note
_NOTE_CONTENT_RE = re.compile(
    r"\b(?:(?:take|make|add|create|write|save)\s+(?:a\s+|new\s+)*note|note\s+down|write\s+down|jot\s+down)\b"
    r"(?:\s+(?:that|saying|says))?[\s,:.-]*(.*)",
    re.IGNORECASE | re.DOTALL,
)

# "add milk and eggs to my shopping list" / "put bread on the shopping list" -> "milk and eggs" / "bread"
_SHOPPING_ITEMS_RE = re.compile(
    r"\b(?:add|put)\s+(?:(.+?)\s+)?(?:to|on(?:to)?)\s+(?:my\s+|the\s+)?shopping\s+list\b",
    re.IGNORECASE | re.DOTALL,
)
# items are separated by commas or "and": "milk, eggs and bread"
_ITEM_SPLIT_RE = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)
# an unchecked Markdown checklist line: "- [ ] milk"
_OPEN_ITEM_RE = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+?)\s*$", re.MULTILINE)


def match_shopping_items_from_prompt(prompt: str) -> list[str] | None:
    """Pull the items out of the prompt, or None if the prompt doesn't add to the shopping list."""
    match = _SHOPPING_ITEMS_RE.search(prompt)
    if not match:
        return None
    items = (item.strip(" .,!?;:") for item in _ITEM_SPLIT_RE.split(match.group(1) or ""))
    return [item for item in items if item]


def match_note_from_prompt(prompt: str) -> str | None:
    """Pull the note text out of the prompt, or None if the prompt doesn't ask to take a note."""
    match = _NOTE_CONTENT_RE.search(prompt)
    return match.group(1).strip() if match else None


def _title_from(content: str) -> str:
    """First few words of the note, without trailing punctuation."""
    words = content.split()
    title = " ".join(words[:TITLE_WORDS]).rstrip(".,!?;:")
    return title[:1].upper() + title[1:]


def save_note(content: str) -> str:
    """Create a note in Nextcloud Notes and return its title."""
    title = _title_from(content)
    response = requests.post(
        NOTES_API_URL,
        auth=(NOTES_USER, NOTES_PASSWORD),
        json={"title": title, "content": content, "category": NOTES_CATEGORY},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("title", title)


def _find_note_id(title: str) -> int | None:
    """Id of the note called `title`, or None if there is none."""
    response = requests.get(
        NOTES_API_URL,
        auth=(NOTES_USER, NOTES_PASSWORD),
        params={"exclude": "content"},
        timeout=15,
    )
    response.raise_for_status()
    return next((note["id"] for note in response.json() if note["title"].casefold() == title.casefold()), None)


def add_to_shopping_list(items: list[str]) -> list[str]:
    """Add `items` as unchecked entries to the shopping list note, creating it if needed.
    Items already open on the list are skipped. Returns the items that were added.
    """
    note_id = _find_note_id(SHOPPING_LIST_TITLE)
    if note_id is None:
        content, etag = f"# {SHOPPING_LIST_TITLE}\n", None
    else:
        response = requests.get(f"{NOTES_API_URL}/{note_id}", auth=(NOTES_USER, NOTES_PASSWORD), timeout=15)
        response.raise_for_status()
        content, etag = response.json()["content"], response.headers.get("ETag")

    already_open = {item.casefold() for item in _OPEN_ITEM_RE.findall(content)}
    added = list(dict.fromkeys(item for item in items if item.casefold() not in already_open))
    if not added:
        return []

    content = content.rstrip("\n") + "\n" + "".join(f"- [ ] {item}\n" for item in added)
    if note_id is None:
        response = requests.post(
            NOTES_API_URL,
            auth=(NOTES_USER, NOTES_PASSWORD),
            json={"title": SHOPPING_LIST_TITLE, "content": content, "category": NOTES_CATEGORY},
            timeout=15,
        )
    else:
        # If-Match: Nextcloud answers 412 if the list was edited (e.g. on the phone) since we read it, instead of overwriting that edit
        response = requests.put(
            f"{NOTES_API_URL}/{note_id}",
            auth=(NOTES_USER, NOTES_PASSWORD),
            headers={"If-Match": etag} if etag else {},
            json={"content": content},
            timeout=15,
        )
    response.raise_for_status()
    return added


# for testing and debugging, run this file directly to create a note or add to the shopping list
# usage: uv run -m services.notes_service "take a note, buy milk and eggs"
#        uv run -m services.notes_service "add milk and eggs to my shopping list"
if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:])
    shopping_items = match_shopping_items_from_prompt(prompt)
    if shopping_items:
        print(f"Added to {SHOPPING_LIST_TITLE}: {add_to_shopping_list(shopping_items)}")
        sys.exit()
    note = match_note_from_prompt(prompt)
    if not note:
        sys.exit("No note or shopping items found in the prompt.")
    print(f"Saved: {save_note(note)}")
