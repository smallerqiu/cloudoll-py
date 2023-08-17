from cloudoll.web import http

""" 
web_hook: https://infloww.slack.com/apps/A0F7XDUAZ-incoming-webhook?tab=settings&next_id=0
blocks_info: https://api.slack.com/messaging/composing/layouts
"""


class Header:
    def __init__(self, text: str):
        self._text = text

    def get_json(self):
        return {"type": "header", "text": {"type": "plain_text", "text": self._text}}


class Text:
    def __init__(self, text: str | int):
        self._text = text

    def get_json(self):
        return {"type": "section", "text": {"type": "mrkdwn", "text": self._text}}


class Field:
    def __init__(self, title: str | int, text: str | int):
        self._title = title
        self._text = text

    def get_json(self):
        return {"type": "mrkdwn", "text": f"{self._title}\n{self._text}"}


class Link:
    def __init__(self, title: str | int, url: str | int):
        self._title = title
        self._url = url

    def get_json(self):
        return {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{self._url}|_{self._title}_>"}],
        }


class Section:
    def __init__(self):
        self._fileds: list[Field] = []

    def add(self, field: Field):
        self._fileds.append(field.get_json())
        return self

    def get_json(self):
        return {"type": "section", "fileds": self._fileds}


class Elements:
    def __init__(self):
        self._elements: list[Field] = []

    def add(self, field: Field):
        self._elements.append(field.get_json())
        return self

    def get_json(self):
        return {"type": "context", "elements": self._elements}


class Divider:
    def __init__(self):
        self._fileds: list[Field] = []

    def get_json(self):
        return {"type": "divider"}


class Blocks:
    def __init__(self):
        self._blocks = []

    def add(self, block: Section | Header | Text | Divider | Link):
        self._blocks.append(block)
        return self

    def add_header(self, text):
        self._blocks.append(Header(text))
        return self

    def add_link(self, title, url: str):
        self._blocks.append(Link(title, url))
        return self

    def add_text(self, text):
        self._blocks.append(Text(text))
        return self

    def add_divider(self):
        self._blocks.append(Divider())
        return self

    def get_json(self):
        blocks = []
        for block in self._blocks:
            blocks.append(block.get_json())
        return blocks


class Slack:
    def __init__(self, url: str):
        self._url = url

    def send_notify(self, blocks: Blocks):
        res = http.post(url=self._url, json={"blocks": blocks})
        return res
