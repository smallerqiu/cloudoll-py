__author__ = "Qiu / smallerqiu@gmail.com"
from html.parser import HTMLParser
from typing import Any, Optional


class parser(HTMLParser):
    def __init__(self) -> None:
        """
        标签属性查找
        :params tags :{ "div":{ "id" : "list" ,"class": "table" }}
        """
        HTMLParser.__init__(self)
        self._text: list[str] = []
        # self._tags = tags
        self._images: list[Optional[str]] = []
        self._videos: list[Optional[str]] = []
        self._finds: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        # print('<%s>' % tag)
        # if self._tags:
        #     for t in self._tags:
        #         if tag == t:
        #             s = attrs
        pass

    def handle_endtag(self, tag: str) -> None:
        # print('</%s>' % tag)

        pass

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        """
        处理单闭合标签
        """
        if tag == "img":
            src = [v for k, v in attrs if k == "src"]
            if len(src):
                self._images.append(src[0])
        if tag == "video":
            src = [v for k, v in attrs if k == "src"]
            if len(src):
                self._videos.append(src[0])
        # print('<%s/>' % tag)

        pass

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        # print(data)
        pass

    def handle_comment(self, data: str) -> None:
        # print('<!--', data, '-->')
        pass

    def handle_entityref(self, name: str) -> None:
        # print('&%s;' % name)
        pass

    def handle_charref(self, name: str) -> None:
        # print('&#%s;' % name)
        pass

    @property
    def text(self) -> str:
        return "".join(self._text)

    @text.setter
    def text(self, value: list[str]) -> None:
        self._text = value

    @property
    def images(self) -> list[Optional[str]]:
        return self._images

    @images.setter
    def images(self, value: list[Optional[str]]) -> None:
        self._images = value

    @property
    def videos(self) -> list[Optional[str]]:
        return self._videos

    @videos.setter
    def videos(self, value: list[Optional[str]]) -> None:
        self._videos = value

    def parser(self, code: str) -> "parser":
        self.feed(code)
        return self
