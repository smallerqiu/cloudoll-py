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


class Field:
    def __init__(self, title: str | int, text: str | int):
        self._title = title
        self._text = text

    def get_json(self):
        return {"type": "mrkdwn", "text": f"*{self._title}:*\n{self._text}"}


class Section:
    def __init__(self):
        self._fileds: list[Field] = []

    def add(self, field: Field):
        self._fileds.append(field.get_json())

    def get_json(self):
        return {"type": "section", "fields": self._fileds}


class Blocks:
    def __init__(self, header=None):
        self._header: Header = header
        self._section: list[Section] = []

    def add(self, section: Section):
        self._section.append(section.get_json())

    def get_json(self):
        blocks = []
        blocks.append(self._header.get_json())
        for s in self._section:
            blocks.append(s)
        return blocks


class Slack:
    def __init__(self, url: str):
        self._url = url

    def send_notify(self, blocks: Blocks):
        res = http.post(url=self._url, json={"blocks": blocks})
        return res
