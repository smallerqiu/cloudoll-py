#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# docs: https://open.dingtalk.com/document/group/message-types-and-data-format
__author__ = "chuchur/chuchur.com"

import base64
import hashlib
import hmac
import logging
import requests as http
import time
from urllib import parse


class Client(object):
    def __init__(self, **kw):
        self._webhook = kw.get("webhook")
        self._secret = kw.get("secret")
        self._access_token = kw.get("access_token")

    def _get_sign(self):
        secret = self._secret
        if not secret:
            logging.error("缺少secret")
            return None, None

        # 拼接timestamp和secret
        timestamp = str(round(time.time() * 1000))
        string_to_sign = "{}\n{}".format(timestamp, secret)
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        # 对结果进行base64处理
        sign = base64.b64encode(hmac_code).decode("utf-8")
        sign = parse.quote(sign)
        return timestamp, sign

    def upload(self, type: str, filepath: str):
        """
        上传媒体
        :params access_token
        :params type 文件类型 image|voice|video|file
        :params filepath 要上传的文件路径
        """
        access_token = self._access_token
        if not access_token:
            logging.error("请配置access_token")
            return False
        url = "https://oapi.dingtalk.com/media/upload?access_token=%s" % access_token
        with open(filepath, "rb") as f:
            files = {"media": f}
            result = http.post(url=url, files=files, data={"type": type})
            res = result.json()
            if res["errcode"] == 0:
                return res
            else:
                logging.error(res["errmsg"])

    def send(self, data: dict):
        """
        发送除签名外的自定义消息结构体 https://open.dingtalk.com/document/orgapp-server/message-types-and-data-format
        :params data 自定义消息结构体
        """
        webhook = self._webhook
        if not webhook:
            logging.error("缺少webhook")
            return False
        timestamp, sign = self._get_sign()
        if not timestamp or not sign:
            return False
        url = webhook + "&timestamp=%s&sign=%s" % (timestamp, sign)
        result = http.post(
            url=url,
            json={**data},
            # data=data
            # data=json.dumps(data)
        )
        if result:
            res = result.json()
            if res["errcode"] == 0:
                logging.info("发送成功！")
                return True
            else:
                logging.info("发送失败")
                logging.error(res["errmsg"])
                return False

    def send_text(self, text: str):
        """
        发送文本消息
        :params text 消息内容
        """

        return self.send(
            data={
                "msgtype": "text",
                "text": {"content": text},
            }
        )

    def _send_media(self, type, media_id, **kw):
        """
        发送媒体
        :params type 媒体类型 image|voice|video|file
        :params media_id 媒体ID
        """
        data = {"msgtype": type}
        data[type] = {"media_id": media_id}
        if type == "voice":
            data["voice"]["duration"] = kw.get("duration")
        return self.send(data)

    def send_markdown(self, title, text):
        """
        发送Markdown消息
        :params title 标题
        :params text markdown结构体
        """
        return self.send(
            data={"msgtype": "markdown", "markdown": {"title": title, "text": text}}
        )

    def send_image(self, media_id: str):
        """
        发送图片消息
        :params media_id 媒体ID
        """
        return self._send_media("image", media_id)

    def send_voice(self, media_id: str, duration: str):
        """
        发送语音消息
        :params media_id 媒体ID
        :params duration 正整数，小于60，表示音频时长。
        """
        return self._send_media("voice", media_id, duration=duration)

    def send_file(self, media_id: str):
        """
        发送文件消息
        :params media_id 媒体ID
        """
        return self._send_media("file", media_id)

    def send_link(self, messageUrl, picUrl, title, text):
        """
        发送链接消息
        :params messageUrl 链接地址
        :params picUrl 链接的小图
        :params title 链接标题 100字内
        :params text 链接副标题 500字内
        """
        return self.send(
            data={
                "msgtype": "link",
                "link": {
                    "picUrl": picUrl,
                    "messageUrl": messageUrl,
                    "title": title,
                    "text": text,
                },
            }
        )

    def send_card(self, **kw):
        """
        发送卡片消息
        :params title 标题
        :params text 消息内容 必填
        :params single_title 查看详情(按钮文字) btns 二选一
        :params single_url 查看详情(链接) btns 二选一
        :params btn_orientation 按钮排列顺序。0|1
        :params btns 按钮 [{title:'',actionURL:''}]
        """
        title = kw.get("title", "")
        text = kw.get("text", "")
        single_title = kw.get("single_title", "")
        single_url = kw.get("single_url", "")
        btn_orientation = kw.get("btn_orientation", 0)
        btns = kw.get("btns", []) or []
        return self.send(
            data={
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "singleTitle": single_title,
                    "singleUrl": single_url,
                    "btnOrientation": btn_orientation,
                    "btns": btns,
                },
            }
        )

    def send_freecard(self, links: list):
        """
        发送卡片消息
        :params links [{ title:'',messageURL:'',picURL:''}]
        """
        return self.send(
            data={
                "msgtype": "feedCard",
                "feedCard": {"links": links},
            }
        )
