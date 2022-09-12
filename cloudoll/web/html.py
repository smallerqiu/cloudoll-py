#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"
from html.parser import HTMLParser


class parser(HTMLParser):
    def __init__(self, tags: dict = None):
        """
        标签属性查找
        :params tags :{ "div":{ "id" : "list" ,"class": "table" }}
        """
        HTMLParser.__init__(self)
        self._text = []
        self._tags = tags
        self._images = []
        self._videos = []
        self._finds = []

    def handle_starttag(self, tag, attrs):
        # print('<%s>' % tag)
        # if self._tags:
        #     for t in self._tags:
        #         if tag == t:
        #             s = attrs
        pass

    def handle_endtag(self, tag):
        # print('</%s>' % tag)
        
        pass

    def handle_startendtag(self, tag, attrs):
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

    def handle_data(self, data):
        self._text.append(data)
        # print(data)
        pass

    def handle_comment(self, data):
        # print('<!--', data, '-->')
        pass

    def handle_entityref(self, name):
        # print('&%s;' % name)
        pass

    def handle_charref(self, name):
        # print('&#%s;' % name)
        pass

    @property
    def text(self):
        return "".join(self._text)

    @text.setter
    def text(self, value):
        self._text = value

    @property
    def images(self):
        return self._images

    @images.setter
    def images(self, value):
        self._images = value

    @property
    def videos(self):
        return self._videos

    @videos.setter
    def videos(self, value):
        self._videos = value

    def parser(self, code: str):
        self.feed(code)
        return self
